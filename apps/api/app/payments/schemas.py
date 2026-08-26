from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreatePaymentRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator_id: str = Field(min_length=1, max_length=255)
    requested_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    purpose: str = Field(default="Operator-approved invoice payment request", min_length=1, max_length=255)
    operator_confirmed: Literal[True]


class DemoPaymentEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=100)
    provider_reference: str = Field(min_length=1, max_length=100)
    payment_reference: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    payment_date: date
    event_type: Literal["payment_request.paid", "payment_request.partially_paid"]


class ExternalPaymentRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    case_id: str
    customer_id: str
    invoice_id: str
    provider: str
    provider_mode: str
    provider_reference: str | None
    provider_url: str | None
    requested_amount: Decimal
    paid_amount: Decimal
    status: str
    purpose: str
    operator_id: str
    failure_reason: str | None
    created_at: datetime | None


class ProviderEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duplicate: bool
    provider_event_id: str
    payment_id: str
    payment_request_id: str
    evidence: dict[str, Any]


class ProviderModeResponse(BaseModel):
    provider: str
    mode: str
    label: str
