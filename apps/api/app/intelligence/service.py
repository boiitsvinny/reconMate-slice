from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.config import get_settings
from app.intelligence.provider import get_provider
from app.intelligence.schemas import CommunicationAnalysisResult
from app.models.domain import AIProcessingStatus, AnalysisReviewStatus, Communication, CommunicationAnalysis


def analyze_text(content: str, reference_date: date | None = None):
    provider = get_provider(get_settings().ai_provider)
    return provider, provider.analyze(content, reference_date)


def persist_analysis(communication: Communication) -> CommunicationAnalysis:
    provider, result = analyze_text(communication.content, communication.occurred_at.date())
    record = CommunicationAnalysis(communication=communication, provider=provider.name, model_version=provider.model_version,
        result=result.model_dump(mode="json"), confidence=Decimal(str(_confidence(result))),
        review_status=AnalysisReviewStatus.PENDING_REVIEW if result.requires_human_review else AnalysisReviewStatus.NOT_REQUIRED)
    communication.ai_processing_status = AIProcessingStatus.PROCESSED
    communication.ai_processing_metadata = {"latest_provider": provider.name, "review_required": result.requires_human_review}
    return record


def _confidence(result: CommunicationAnalysisResult) -> float:
    values = [item.confidence for item in result.payment_commitments]
    values += [result.dispute_signal.confidence, result.payment_completed_claim.confidence]
    return max(values, default=0.8)
