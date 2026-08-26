"""Small provider contract with explicit demo and optional Razorpay test adapters."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from app.core.config import get_settings


class PaymentProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreatedPaymentRequest:
    reference: str
    status: str
    url: str | None


class PaymentRequestProvider(Protocol):
    name: str
    mode: str

    def create_payment_request(self, *, request_id: UUID, amount: Decimal, customer_name: str, invoice_number: str, purpose: str) -> CreatedPaymentRequest: ...


class ProviderDemoPaymentRequestProvider:
    name = "PROVIDER_DEMO"
    mode = "DEMO"

    def create_payment_request(self, *, request_id: UUID, amount: Decimal, customer_name: str, invoice_number: str, purpose: str) -> CreatedPaymentRequest:
        del amount, customer_name, invoice_number, purpose
        reference = f"demo_payreq_{request_id.hex}"
        return CreatedPaymentRequest(reference=reference, status="ACTIVE", url=None)


class RazorpayTestPaymentRequestProvider:
    name = "RAZORPAY"
    mode = "TEST"

    def __init__(self, key_id: str, key_secret: str) -> None:
        if not key_id.startswith("rzp_test_"):
            raise PaymentProviderError("Only Razorpay test-mode credentials are accepted.")
        self._auth = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()

    def create_payment_request(self, *, request_id: UUID, amount: Decimal, customer_name: str, invoice_number: str, purpose: str) -> CreatedPaymentRequest:
        payload = json.dumps({
            "amount": int(amount * 100), "currency": "INR", "accept_partial": True,
            "reference_id": f"rm_{request_id.hex[:32]}", "description": purpose,
            "customer": {"name": customer_name}, "notify": {"sms": False, "email": False},
            "reminder_enable": False, "notes": {"reconmate_request_id": str(request_id), "invoice_number": invoice_number},
        }).encode()
        request = Request("https://api.razorpay.com/v1/payment_links/", data=payload, method="POST", headers={
            "Authorization": f"Basic {self._auth}", "Content-Type": "application/json",
        })
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed official HTTPS endpoint
                body = json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise PaymentProviderError("Razorpay test-mode payment request creation failed.") from exc
        reference = body.get("id")
        if not isinstance(reference, str):
            raise PaymentProviderError("Razorpay returned an invalid payment-link response.")
        return CreatedPaymentRequest(reference=reference, status=str(body.get("status", "issued")).upper(), url=body.get("short_url"))


def get_payment_request_provider() -> PaymentRequestProvider:
    settings = get_settings()
    mode = settings.payment_provider_mode.casefold()
    if mode == "razorpay_test":
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise PaymentProviderError("Razorpay test mode requires backend-only test credentials.")
        return RazorpayTestPaymentRequestProvider(settings.razorpay_key_id, settings.razorpay_key_secret)
    if mode == "provider_demo":
        return ProviderDemoPaymentRequestProvider()
    raise PaymentProviderError("PAYMENT_PROVIDER_MODE must be provider_demo or razorpay_test.")
