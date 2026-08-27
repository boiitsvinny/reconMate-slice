import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

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


def _provider(payload=None, error=None):
    provider = GoogleGenAICommunicationIntelligenceProvider(
        api_key="test-key", model="gemini-3.7-flash", timeout_seconds=3,
        confidence_threshold=0.7,
    )
    provider.client = SimpleNamespace(interactions=FakeInteractions(payload, error))
    return provider


def test_provider_configuration_and_runtime_labels_are_explicit() -> None:
    assert get_provider("mock").runtime_mode == "MOCK / DEV MODE"
    with pytest.raises(ProviderConfigurationError, match="GEMINI_API_KEY"):
        get_provider("google", model="gemini-3.7-flash")
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


@pytest.mark.parametrize("payload", [
    "not-json",
    json.dumps({"candidates": [_candidate(fact_type="AUTHORITATIVE_RISK_SCORE")]}),
    json.dumps({"candidates": [_candidate(confidence=1.2)]}),
    json.dumps({"candidates": [_candidate(evidence_span="words not present in source")]}),
    json.dumps({"candidates": [_candidate(),], "risk_score": 0, "recommendation": "CLOSE_CASE"}),
])
def test_untrusted_or_authoritative_model_output_fails_closed(payload: str) -> None:
    with pytest.raises(ProviderError, match="invalid or ungrounded"):
        _provider(payload).analyze(MESSAGE, date(2026, 8, 26))


def test_timeout_is_safe_and_does_not_retry_or_write() -> None:
    interactions = FakeInteractions(error=httpx.ReadTimeout("timed out"))
    provider = _provider()
    provider.client = SimpleNamespace(interactions=interactions)
    with pytest.raises(ProviderError, match="timed out"):
        provider.analyze(MESSAGE, date(2026, 8, 26))
    assert len(interactions.calls) == 1


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
