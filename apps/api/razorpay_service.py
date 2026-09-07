"""Server-only Razorpay client. Never import this from frontend code."""

from __future__ import annotations

import hashlib
import hmac
import logging

from apps.api.errors import ApiError
from cropmandi.config import get_settings

logger = logging.getLogger(__name__)
ALLOWED_CURRENCY = "INR"


def razorpay_credentials() -> tuple[str, str]:
    settings = get_settings()
    key_id = (settings.razorpay_key_id or "").strip()
    key_secret = (settings.razorpay_key_secret or "").strip()
    if not key_id or not key_secret:
        raise ApiError(
            503,
            "payments_not_configured",
            "Razorpay test keys are not configured on the server",
        )
    return key_id, key_secret


def webhook_secret() -> str:
    secret = (get_settings().razorpay_webhook_secret or "").strip()
    if not secret:
        raise ApiError(
            503,
            "payments_not_configured",
            "Razorpay webhook secret is not configured on the server",
        )
    return secret


def _client():
    key_id, key_secret = razorpay_credentials()
    try:
        import razorpay
    except ImportError as exc:
        raise ApiError(
            503,
            "payments_not_configured",
            "Razorpay test checkout is unavailable because a server dependency is missing",
        ) from exc
    return razorpay.Client(auth=(key_id, key_secret))


def create_order(amount_paise: int, currency: str, receipt: str, notes: dict) -> dict:
    if amount_paise <= 0:
        raise ApiError(400, "invalid_amount", "amount must be greater than 0")
    if currency != ALLOWED_CURRENCY:
        raise ApiError(400, "invalid_currency", "Only INR is supported")
    try:
        client = _client()
        return client.order.create(
            {
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt,
                "notes": notes,
                "payment_capture": 1,
            }
        )
    except ApiError:
        raise
    except Exception:
        logger.warning("razorpay_order_failed")
        raise ApiError(
            502,
            "razorpay_order_failed",
            "Unable to create payment order.",
        ) from None


def fetch_payment(payment_id: str) -> dict | None:
    try:
        client = _client()
        return client.payment.fetch(payment_id)
    except ApiError:
        raise
    except Exception:
        logger.warning("razorpay_payment_fetch_failed")
        return None


def fetch_order(order_id: str) -> dict | None:
    try:
        client = _client()
        return client.order.fetch(order_id)
    except ApiError:
        raise
    except Exception:
        logger.warning("razorpay_order_fetch_failed")
        return None


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    _, secret = razorpay_credentials()
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip())


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    secret = webhook_secret()
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip())
