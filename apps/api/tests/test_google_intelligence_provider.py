import json
from datetime import date
import logging
from types import SimpleNamespace

import httpx
import pytest
from google import genai
from google.genai import types as genai_types

from app.intelligence import provider as provider_module
from app.intelligence.evaluation import (
    run_communication_extraction_evaluation,
    run_live_communication_extraction_evaluation,
)
from app.intelligence.provider import (
    CommunicationIntelligenceProvider,
    GoogleGenAICommunicationIntelligenceProvider,
    ProviderConfigurationError,
    ProviderError,
    get_provider,
)
from app.intelligence.service import analyze_text
from app.intelligence.schemas import CommunicationAnalysisResult, Intent


MESSAGE = "We raised a dispute because the invoice quantity is wrong."
SECRET = "test-key-do-not-log"


def _candidate(**overrides):
    value = {
        "candidate_id": "model-id",
        "fact_type": "ACTIVE_DISPUTE",
        "confidence": 0.93,
        "evidence_span": "raised a dispute",
        "proposed_data": {"status": "DISPUTED"},
        "persistence_eligible": True,
        "defer_reason": None,
        "operator_confirmation_required": True,
    }
    value.update(overrides)
    return value


class FakeInteractions:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(output_text=self.payload)


class FakeProviderFailure(Exception):
    def __init__(self, message: str, *, status_code=None, code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.body = body


def _failure_log(caplog) -> dict:
    record = next(record for record in reversed(caplog.records) if "gemini_provider_failure" in record.message)
    return json.loads(record.message)


def _self_test_log(caplog) -> dict:
    record = next(record for record in reversed(caplog.records) if "gemini_provider_self_test" in record.message)
    return json.loads(record.message)


def _provider(payload=None, error=None, api_key="test-key"):
    provider = GoogleGenAICommunicationIntelligenceProvider(
        api_key=api_key, model="gemini-3.7-flash", timeout_seconds=3,
        confidence_threshold=0.7,
    )
    provider.client = SimpleNamespace(interactions=FakeInteractions(payload, error))
    return provider


def test_provider_configuration_and_runtime_labels_are_explicit(caplog) -> None:
    assert get_provider("mock").runtime_mode == "MOCK / DEV MODE"
    with caplog.at_level(logging.ERROR, logger="app.intelligence.provider"):
        with pytest.raises(ProviderConfigurationError, match="GEMINI_API_KEY"):
            get_provider("google", model="gemini-3.7-flash")
    missing_key_log = _failure_log(caplog)
    assert missing_key_log["failure_category"] == "missing_key"
    assert missing_key_log["provider"] == "google"
    assert missing_key_log["model"] == "gemini-3.7-flash"
    live = get_provider("google", api_key="test-key", model="gemini-3.7-flash")
    assert live.runtime_mode == "LIVE MODEL" and live.model_version == "gemini-3.7-flash"


def test_live_provider_uses_read_only_structured_response_and_minimal_context() -> None:
    provider = _provider(json.dumps({"candidates": [_candidate()]}))
    result = provider.analyze(MESSAGE, date(2026, 8, 26))
    assert result.candidates[0].fact_type.value == "ACTIVE_DISPUTE"
    call = provider.client.interactions.calls[0]
    assert call["store"] is False
    assert call["response_format"]["mime_type"] == "application/json"
    assert call["response_format"]["schema"] == provider_module._EXTRACTION_SCHEMA
    assert call["model"] == "gemini-3.7-flash" and call["timeout"] == 3
    assert MESSAGE in call["input"] and "portfolio" not in call["input"].lower()
    assert "tools" not in call and "previous_interaction_id" not in call


def test_installed_sdk_serializes_current_interactions_structured_output_shape() -> None:
    captured = {}
    payload = json.dumps({"candidates": [_candidate(proposed_data={
        "amount": None,
        "currency": None,
        "promised_date": None,
        "conditional": None,
        "reason": None,
        "status": "DISPUTED",
        "requires_payment_verification": None,
    })]})

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "interaction-test",
            "object": "interaction",
            "status": "completed",
            "model": "gemini-3.7-flash",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": payload}]}],
        })

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = genai.Client(
        api_key="test-key",
        http_options=genai_types.HttpOptions(
            base_url="https://gemini-serialization.test",
            httpx_client=http_client,
            retry_options=genai_types.HttpRetryOptions(attempts=1),
        ),
    )
    provider = _provider()
    provider.client = client
    try:
        result = provider.analyze(MESSAGE, date(2026, 8, 26))
    finally:
        client.close()

    assert result.candidates[0].fact_type.value == "ACTIVE_DISPUTE"
    body = captured["body"]
    assert set(body) == {"model", "input", "response_format", "generation_config", "store"}
    assert body["model"] == "gemini-3.7-flash"
    assert body["store"] is False
    assert body["generation_config"] == {"max_output_tokens": 1200}
    assert body["response_format"]["type"] == "text"
    assert body["response_format"]["mime_type"] == "application/json"
    serialized_schema = body["response_format"]["schema"]
    assert serialized_schema == provider_module._EXTRACTION_SCHEMA
    assert "additionalProperties" not in json.dumps(serialized_schema)
    assert not any(key in json.dumps(serialized_schema) for key in ("$defs", "$ref", "oneOf", "anyOf", "const"))
    assert "response_mime_type" not in body


def test_real_bad_request_metadata_is_sanitized_and_minimal_probe_is_comparable(caplog) -> None:
    provider_module._MINIMAL_SELF_TEST_ATTEMPTED = False
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        if len(captured) == 1:
            return httpx.Response(400, json={"error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": f"raw message contains {SECRET} and {MESSAGE}",
                "details": [{
                    "@type": "type.googleapis.com/google.rpc.BadRequest",
                    "fieldViolations": [{
                        "field": "response_format.schema.properties.candidates",
                        "description": f"Unsupported schema field; key={SECRET}; source={MESSAGE}",
                    }],
                }],
            }})
        return httpx.Response(200, json={
            "id": "minimal-test",
            "object": "interaction",
            "status": "completed",
            "model": "gemini-3.7-flash",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": '{"result":"ok"}'}]}],
        })

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = genai.Client(
        api_key=SECRET,
        http_options=genai_types.HttpOptions(
            base_url="https://gemini-error.test",
            httpx_client=http_client,
            retry_options=genai_types.HttpRetryOptions(attempts=1),
        ),
    )
    provider = _provider(api_key=SECRET)
    provider.client = client
    try:
        with caplog.at_level(logging.INFO, logger="app.intelligence.provider"):
            with pytest.raises(ProviderError, match="provider is unavailable"):
                provider.analyze(MESSAGE, date(2026, 8, 26))
    finally:
        client.close()

    failure = _failure_log(caplog)
    assert failure["exception_type"] == "BadRequestError"
    assert failure["google_error_status"] == "INVALID_ARGUMENT"
    assert failure["google_error_code"] == 400
    assert failure["field_violation_path"] == "response_format.schema.properties.candidates"
    assert "Unsupported schema field" in failure["field_violation_description"]
    assert SECRET not in json.dumps(failure) and MESSAGE not in json.dumps(failure)
    probe = _self_test_log(caplog)
    assert probe["outcome"] == "passed"
    assert probe["same_model_and_request_options_as_reconmate"] is True
    assert probe["input_mode"] == "fixed_non_customer_probe"
    assert len(captured) == 2
    reconmate, minimal = captured
    assert set(reconmate) == set(minimal) == {"model", "input", "response_format", "generation_config", "store"}
    assert reconmate["model"] == minimal["model"] == "gemini-3.7-flash"
    assert reconmate["generation_config"] == minimal["generation_config"]
    assert reconmate["store"] == minimal["store"] is False
    assert reconmate["response_format"]["schema"] == provider_module._EXTRACTION_SCHEMA
    assert minimal["response_format"]["schema"] == provider_module._MINIMAL_SELF_TEST_SCHEMA


@pytest.mark.parametrize("payload", [
    "not-json",
    json.dumps({"candidates": [_candidate(fact_type="AUTHORITATIVE_RISK_SCORE")]}),
    json.dumps({"candidates": [_candidate(confidence=1.2)]}),
    json.dumps({"candidates": [_candidate(evidence_span="words not present in source")]}),
    json.dumps({"candidates": [_candidate(),], "risk_score": 0, "recommendation": "CLOSE_CASE"}),
    json.dumps({"candidates": [_candidate(proposed_data={"status": "DISPUTED", "risk_score": "100"})]}),
])
def test_untrusted_or_authoritative_model_output_fails_closed(payload: str) -> None:
    with pytest.raises(ProviderError, match="invalid or ungrounded"):
        _provider(payload).analyze(MESSAGE, date(2026, 8, 26))


def test_timeout_is_safe_and_does_not_retry_or_write(caplog) -> None:
    interactions = FakeInteractions(error=httpx.ReadTimeout("timed out"))
    provider = _provider()
    provider.client = SimpleNamespace(interactions=interactions)
    with caplog.at_level(logging.ERROR, logger="app.intelligence.provider"):
        with pytest.raises(ProviderError, match="timed out"):
            provider.analyze(MESSAGE, date(2026, 8, 26))
    assert len(interactions.calls) == 1
    event = _failure_log(caplog)
    assert event["failure_category"] == "timeout"
    assert event["exception_type"] == "ReadTimeout"
    assert isinstance(event["elapsed_ms"], int)


@pytest.mark.parametrize(("status_code", "code", "expected"), [
    (401, "UNAUTHENTICATED", "invalid_key/auth"),
    (403, "PERMISSION_DENIED", "invalid_key/auth"),
    (404, "NOT_FOUND", "model_not_found"),
    (429, "RESOURCE_EXHAUSTED", "quota_or_rate_limit"),
    (400, "INVALID_ARGUMENT", "request_or_schema_error"),
])
def test_provider_http_failures_are_classified_and_public_error_stays_generic(
    caplog, status_code: int, code: str, expected: str,
) -> None:
    failure = FakeProviderFailure("provider details", status_code=status_code, code=code)
    with caplog.at_level(logging.ERROR, logger="app.intelligence.provider"):
        with pytest.raises(ProviderError) as raised:
            _provider(error=failure).analyze(MESSAGE, date(2026, 8, 26))
    assert str(raised.value) == "The live model provider is unavailable; no fact was written."
    event = _failure_log(caplog)
    assert event["failure_category"] == expected
    assert event["http_status"] == status_code
    assert event["provider_error_code"] == code


def test_provider_log_is_allowlisted_and_never_leaks_secret_prompt_or_raw_error(caplog) -> None:
    failure = FakeProviderFailure(
        f"Authorization: Bearer {SECRET}; key={SECRET}; customer={MESSAGE}",
        status_code=401,
        code=f"AUTH_{SECRET}",
        body={"error": {"message": f"raw response contains {SECRET} and {MESSAGE}"}},
    )
    with caplog.at_level(logging.ERROR, logger="app.intelligence.provider"):
        with pytest.raises(ProviderError):
            _provider(error=failure, api_key=SECRET).analyze(MESSAGE, date(2026, 8, 26))
    rendered = json.dumps(_failure_log(caplog))
    assert SECRET not in rendered
    assert MESSAGE not in rendered
    assert "Authorization" not in rendered and "Bearer" not in rendered


@pytest.mark.parametrize(("payload", "expected"), [
    ("not-json", "malformed_provider_response"),
    (json.dumps({"candidates": [_candidate(fact_type="AUTHORITATIVE_RISK_SCORE")]}), "local_validation_failure"),
])
def test_malformed_and_local_schema_failures_are_distinguished(caplog, payload: str, expected: str) -> None:
    with caplog.at_level(logging.ERROR, logger="app.intelligence.provider"):
        with pytest.raises(ProviderError, match="invalid or ungrounded"):
            _provider(payload).analyze(MESSAGE, date(2026, 8, 26))
    event = _failure_log(caplog)
    assert event["failure_category"] == expected
    assert event["http_status"] is None


def test_sdk_or_network_failure_is_contained_without_fallback() -> None:
    interactions = FakeInteractions(error=RuntimeError("generated SDK failure"))
    provider = _provider()
    provider.client = SimpleNamespace(interactions=interactions)
    with pytest.raises(ProviderError, match="provider is unavailable"):
        provider.analyze(MESSAGE, date(2026, 8, 26))
    assert len(interactions.calls) == 1


def test_low_confidence_defers_and_duplicates_are_normalized() -> None:
    payload = json.dumps({"candidates": [
        _candidate(confidence=0.55),
        _candidate(candidate_id="duplicate", confidence=0.62, evidence_span="invoice quantity is wrong"),
    ]})
    candidates = _provider(payload).analyze(MESSAGE, date(2026, 8, 26)).candidates
    assert len(candidates) == 1
    assert candidates[0].confidence == 0.62
    assert candidates[0].persistence_eligible is False
    assert candidates[0].defer_reason == "Confidence is below the configured operator-acceptance threshold."


def test_conflicting_same_type_candidates_defer_for_manual_review() -> None:
    message = "We will pay INR 10,000 on 2026-08-29, or INR 20,000 on 2026-08-30."
    first = _candidate(
        fact_type="PAYMENT_PROMISE", evidence_span="INR 10,000 on 2026-08-29",
        proposed_data={"amount": "10000", "currency": "INR", "promised_date": "2026-08-29", "conditional": False},
    )
    second = _candidate(
        fact_type="PAYMENT_PROMISE", confidence=0.91, evidence_span="INR 20,000 on 2026-08-30",
        proposed_data={"amount": "20000", "currency": "INR", "promised_date": "2026-08-30", "conditional": False},
    )
    candidate = _provider(json.dumps({"candidates": [first, second]})).analyze(message, date(2026, 8, 26)).candidates[0]
    assert candidate.persistence_eligible is False
    assert candidate.defer_reason == "Conflicting candidates of the same type require manual review."


def test_multiple_signal_extraction_preserves_supported_types() -> None:
    message = "The invoice is disputed, but we will pay INR 10,000 on 2026-08-29."
    promise = _candidate(
        fact_type="PAYMENT_PROMISE", confidence=0.91,
        evidence_span="will pay INR 10,000 on 2026-08-29",
        proposed_data={"amount": "10000", "currency": "INR", "promised_date": "2026-08-29", "conditional": False},
    )
    result = _provider(json.dumps({"candidates": [_candidate(evidence_span="invoice is disputed"), promise]})).analyze(message, date(2026, 8, 26))
    assert {item.fact_type.value for item in result.candidates} == {"ACTIVE_DISPUTE", "PAYMENT_PROMISE"}


def test_no_silent_live_to_mock_fallback(monkeypatch) -> None:
    settings = SimpleNamespace(
        ai_provider="google", gemini_api_key=None, ai_model="gemini-3.7-flash",
        ai_timeout_seconds=3, ai_confidence_threshold=0.7, ai_allow_mock_fallback=False,
    )
    monkeypatch.setattr("app.intelligence.service.get_settings", lambda: settings)
    with pytest.raises(ProviderConfigurationError):
        analyze_text(MESSAGE)
    settings.ai_allow_mock_fallback = True
    provider, _ = analyze_text(MESSAGE)
    assert provider.runtime_mode == "MOCK / DEV MODE"


class EvaluationProvider(CommunicationIntelligenceProvider):
    name = "google"
    model_version = "evaluation-double"
    runtime_mode = "LIVE MODEL"

    def analyze(self, content: str, reference_date: date | None = None) -> CommunicationAnalysisResult:
        return get_provider("mock").analyze(content, reference_date)


def test_evaluation_runner_separates_mock_live_and_missing_credentials() -> None:
    mock_result = run_communication_extraction_evaluation()
    live_result = run_communication_extraction_evaluation(EvaluationProvider())
    unavailable = run_live_communication_extraction_evaluation(api_key=None, model="gemini-3.7-flash")
    assert mock_result["runtime_mode"] == "MOCK / DEV MODE"
    assert live_result["runtime_mode"] == "LIVE MODEL" and live_result["exact"] == 30
    assert unavailable["executed"] is False
    assert unavailable["reason"] == "Live-model evaluation not executed because no configured credentials were available."
