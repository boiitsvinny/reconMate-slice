from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.recommendations.schemas import RecommendedAction


class CreateActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_recommended_action: RecommendedAction | None = None
    operator_note: str | None = Field(default=None, max_length=4000)


class OperatorDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator_id: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=4000)
    operator_note: str | None = Field(default=None, max_length=4000)


class RecoveryActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    case_id: str
    action_type: str
    recommended_action: str | None
    status: str
    approval_status: str
    human_approval_required: bool
    recommendation_context: dict[str, Any] | None
    reason: str | None
    decision_by: str | None
    decision_reason: str | None
    decision_at: datetime | None
    executed_at: datetime | None
    executed_by: str | None
    operator_note: str | None
    created_at: datetime | None
