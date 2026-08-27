from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.config import get_settings
from app.intelligence.candidates import candidate_facts
from app.intelligence.provider import CommunicationIntelligenceProvider, MockCommunicationIntelligenceProvider, ProviderError, get_provider
from app.intelligence.schemas import CommunicationAnalysisResult
from app.models.domain import AIProcessingStatus, AnalysisReviewStatus, Communication, CommunicationAnalysis


def analyze_text(content: str, reference_date: date | None = None):
    settings = get_settings()
    try:
        provider = get_provider(
            settings.ai_provider,
            api_key=settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None,
            model=settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
            confidence_threshold=settings.ai_confidence_threshold,
        )
        return provider, provider.analyze(content, reference_date)
    except ProviderError:
        if not settings.ai_allow_mock_fallback or settings.ai_provider.lower() == "mock":
            raise
        fallback = MockCommunicationIntelligenceProvider()
        return fallback, fallback.analyze(content, reference_date)


def persist_analysis(
    communication: Communication,
    *,
    provider_override: CommunicationIntelligenceProvider | None = None,
) -> CommunicationAnalysis:
    if provider_override is None:
        provider, result = analyze_text(communication.content, communication.occurred_at.date())
    else:
        provider = provider_override
        result = provider.analyze(communication.content, communication.occurred_at.date())
    record = CommunicationAnalysis(communication=communication, provider=provider.name, model_version=provider.model_version,
        result=result.model_dump(mode="json"), confidence=Decimal(str(_confidence(result))),
        review_status=AnalysisReviewStatus.PENDING_REVIEW)
    communication.ai_processing_status = AIProcessingStatus.PROCESSED
    communication.ai_processing_metadata = {
        "latest_provider": provider.name,
        "runtime_mode": provider.runtime_mode,
        "review_required": result.requires_human_review,
    }
    return record


def analysis_candidates(communication: Communication, result: CommunicationAnalysisResult):
    return candidate_facts(communication.content, result)


def _confidence(result: CommunicationAnalysisResult) -> float:
    values = [item.confidence for item in result.payment_commitments]
    values += [result.dispute_signal.confidence, result.payment_completed_claim.confidence]
    return max(values, default=0.8)
