"""
Razorpay Standard Checkout API.

DEMO IDENTITY (not production authentication):
The static login page is not wired to this backend. Create-order, verify,
status, and history calls are bound to a single seeded demo farmer.
Clients cannot choose a user_id. Replace ensure_demo_user() with real auth later.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api import razorpay_service
from apps.api.errors import ApiError
from cropmandi.db.models import Payment, PaymentWebhookEvent, User

logger = logging.getLogger(__name__)

DEMO_USER_CODE = "cropmandi_demo_farmer"
DEMO_USER_NAME = "CropMandi demo farmer"
DEMO_AMOUNT_INR = 100
ALLOWED_CURRENCY = "INR"
SUCCESS_STATUSES = {"AUTHORIZED", "CAPTURED"}
TERMINAL_FAILURE = {"FAILED", "CANCELLED", "EXPIRED"}

router = APIRouter()


class CreateOrderBody(BaseModel):
    crop: str = Field(min_length=1)
    quantity: float | int | str
    amount: float | None = None
    currency: str | None = None
    listing_id: str | None = None


class VerifyBody(BaseModel):
    razorpay_order_id: str = Field(min_length=1)
    razorpay_payment_id: str = Field(min_length=1)
    razorpay_signature: str = Field(min_length=1)


def rupees_to_paise(amount: float) -> int:
    try:
        paise = int((Decimal(str(amount)) * Decimal("100")).quantize(Decimal("1")))
    except (InvalidOperation, ValueError) as exc:
        raise ApiError(400, "invalid_amount", "amount must be a number") from exc
    if paise <= 0:
        raise ApiError(400, "invalid_amount", "amount must be greater than 0")
    return paise


def payable_paise() -> int:
    return rupees_to_paise(DEMO_AMOUNT_INR)


def ensure_demo_user(session: Session) -> User:
    user = session.query(User).filter_by(code=DEMO_USER_CODE).one_or_none()
    if user is None:
        user = User(code=DEMO_USER_CODE, display_name=DEMO_USER_NAME, is_demo=True)
        session.add(user)
        session.flush()
    return user


def _payment_public(row: Payment) -> dict:
    return {
        "id": row.id,
        "razorpay_order_id": row.razorpay_order_id,
        "razorpay_payment_id": row.razorpay_payment_id,
        "amount_paise": row.amount_paise,
        "currency": row.currency,
        "crop": row.crop,
        "quantity": row.quantity,
        "listing_id": row.listing_id,
        "status": row.status,
        "signature_verified": bool(row.signature_verified),
        "webhook_verified": bool(row.webhook_verified),
        "demo_identity": True,
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def apply_status(
    row: Payment,
    new_status: str,
    payment_id: str | None = None,
    *,
    signature_verified: bool | None = None,
    webhook_verified: bool | None = None,
    failure_reason: str | None = None,
) -> None:
    new_status = (new_status or "").upper()
    current = (row.status or "").upper()
    if current in SUCCESS_STATUSES and new_status in TERMINAL_FAILURE:
        return
    if current in SUCCESS_STATUSES and new_status in SUCCESS_STATUSES:
        if payment_id and not row.razorpay_payment_id:
            row.razorpay_payment_id = payment_id
        if signature_verified:
            row.signature_verified = True
        if webhook_verified:
            row.webhook_verified = True
        if row.paid_at is None:
            row.paid_at = _now()
        return
    row.status = new_status
    if payment_id:
        row.razorpay_payment_id = payment_id
    if signature_verified:
        row.signature_verified = True
    if webhook_verified:
        row.webhook_verified = True
    if failure_reason:
        row.failure_reason = failure_reason[:255]
    if new_status in SUCCESS_STATUSES and row.paid_at is None:
        row.paid_at = _now()


def _validate_create_body(body: CreateOrderBody) -> tuple[int, str]:
    crop = body.crop.strip()
    if not crop:
        raise ApiError(400, "invalid_crop", "crop is required")
    currency = (body.currency or ALLOWED_CURRENCY).strip().upper()
    if currency != ALLOWED_CURRENCY:
        raise ApiError(400, "invalid_currency", "Only INR is supported")
    expected = payable_paise()
    if body.amount is not None:
        if rupees_to_paise(body.amount) != expected:
            raise ApiError(400, "invalid_amount", "amount does not match the payable total")
    return expected, crop


def create_order(session: Session, body: CreateOrderBody) -> dict:
    paise, crop = _validate_create_body(body)
    user = ensure_demo_user(session)
    receipt = uuid.uuid4().hex[:40]
    notes = {
        "crop": crop,
        "quantity": str(body.quantity),
        "listing_id": body.listing_id or "",
        "demo_user": DEMO_USER_CODE,
    }
    order = razorpay_service.create_order(
        amount_paise=paise,
        currency=ALLOWED_CURRENCY,
        receipt=receipt,
        notes=notes,
    )
    order_id = order.get("id")
    if not order_id:
        raise ApiError(502, "razorpay_order_failed", "Unable to create payment order.")
    row = Payment(
        user_id=user.id,
        receipt=receipt,
        razorpay_order_id=str(order_id),
        amount_paise=int(order.get("amount") or paise),
        currency=str(order.get("currency") or ALLOWED_CURRENCY),
        crop=crop,
        quantity=str(body.quantity),
        listing_id=(body.listing_id or None),
        status="CREATED",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    key_id, _secret = razorpay_service.razorpay_credentials()
    return {
        "success": True,
        "key_id": key_id,
        "order_id": row.razorpay_order_id,
        "amount": row.amount_paise,
        "currency": row.currency,
        "demo_identity": DEMO_USER_CODE,
    }


def verify_order(session: Session, body: VerifyBody) -> dict:
    user = ensure_demo_user(session)
    row = (
        session.query(Payment)
        .filter_by(razorpay_order_id=body.razorpay_order_id, user_id=user.id)
        .one_or_none()
    )
    if row is None:
        raise ApiError(404, "order_not_found", "No payment order for the demo identity")
    stored_order_id = row.razorpay_order_id
    if stored_order_id != body.razorpay_order_id:
        logger.warning("payment_order_id_mismatch")
        raise ApiError(400, "invalid_order", "Payment verification failed.")

    if row.status in SUCCESS_STATUSES and row.signature_verified:
        if row.razorpay_payment_id and row.razorpay_payment_id != body.razorpay_payment_id:
            raise ApiError(409, "duplicate_payment", "This order is already paid")
        return {"success": True, "verified": True, "payment": _payment_public(row)}

    if not razorpay_service.verify_payment_signature(
        stored_order_id,
        body.razorpay_payment_id,
        body.razorpay_signature,
    ):
        logger.warning("invalid_payment_signature order_ref=%s", row.id)
        raise ApiError(400, "invalid_signature", "Payment verification failed.")

    remote = razorpay_service.fetch_payment(body.razorpay_payment_id)
    if remote:
        remote_order = str(remote.get("order_id") or "")
        if remote_order and remote_order != stored_order_id:
            logger.warning("payment_remote_order_mismatch order_ref=%s", row.id)
            raise ApiError(400, "invalid_order", "Payment verification failed.")
        remote_status = str(remote.get("status") or "").lower()
        if remote_status in {"failed", "cancelled"}:
            apply_status(row, "FAILED", body.razorpay_payment_id, failure_reason="gateway_failed")
            session.commit()
            raise ApiError(400, "payment_failed", "Payment failed. Please try again.")
        if remote_status == "authorized":
            apply_status(
                row,
                "AUTHORIZED",
                body.razorpay_payment_id,
                signature_verified=True,
            )
        else:
            apply_status(
                row,
                "CAPTURED",
                body.razorpay_payment_id,
                signature_verified=True,
            )
    else:
        apply_status(
            row,
            "CAPTURED",
            body.razorpay_payment_id,
            signature_verified=True,
        )
    session.commit()
    session.refresh(row)
    return {"success": True, "verified": True, "payment": _payment_public(row)}


def list_history(session: Session) -> dict:
    user = ensure_demo_user(session)
    rows = (
        session.query(Payment)
        .filter_by(user_id=user.id)
        .order_by(Payment.id.desc())
        .all()
    )
    return {
        "demo_identity": DEMO_USER_CODE,
        "authentication": "demo_identity_not_production",
        "count": len(rows),
        "payments": [_payment_public(row) for row in rows],
    }


def payment_status(session: Session, order_id: str) -> dict:
    user = ensure_demo_user(session)
    row = (
        session.query(Payment)
        .filter_by(razorpay_order_id=order_id, user_id=user.id)
        .one_or_none()
    )
    if row is None:
        raise ApiError(404, "order_not_found", "No payment order for the demo identity")
    return {"success": True, "payment": _payment_public(row)}


def mark_cancelled(session: Session, order_id: str) -> dict:
    user = ensure_demo_user(session)
    row = (
        session.query(Payment)
        .filter_by(razorpay_order_id=order_id, user_id=user.id)
        .one_or_none()
    )
    if row is None:
        raise ApiError(404, "order_not_found", "No payment order for the demo identity")
    if row.status in SUCCESS_STATUSES:
        return {"success": True, "payment": _payment_public(row), "already_paid": True}
    apply_status(row, "CANCELLED", failure_reason="checkout_dismissed")
    session.commit()
    session.refresh(row)
    return {"success": True, "payment": _payment_public(row)}


def _event_id(payload: dict, signature: str) -> str:
    raw_id = payload.get("id") or payload.get("event_id")
    if raw_id:
        return str(raw_id)
    digest = hashlib.sha256(f"{signature}:{payload.get('event')}".encode("utf-8")).hexdigest()
    return f"sig-{digest}"


def process_webhook(session: Session, body: bytes, signature: str) -> dict:
    if not razorpay_service.verify_webhook_signature(body, signature):
        logger.warning("invalid_webhook_signature")
        raise ApiError(400, "invalid_webhook_signature", "Webhook signature is invalid")
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ApiError(400, "invalid_webhook", "Webhook body is not JSON") from exc
    if not isinstance(payload, dict):
        raise ApiError(400, "invalid_webhook", "Webhook body is not JSON")

    event = str(payload.get("event") or "")
    event_id = _event_id(payload, signature)
    existing = session.query(PaymentWebhookEvent).filter_by(event_id=event_id).one_or_none()
    if existing is not None:
        return {"accepted": True, "updated": False, "duplicate": True, "event": event}

    nested = payload.get("payload") or {}
    if not isinstance(nested, dict):
        nested = {}
    payment_entity = (nested.get("payment") or {}).get("entity") or {}
    order_entity = (nested.get("order") or {}).get("entity") or {}
    order_id = payment_entity.get("order_id") or order_entity.get("id")
    payment_id = payment_entity.get("id")

    session.add(
        PaymentWebhookEvent(
            event_id=event_id,
            event_type=event or "unknown",
            razorpay_order_id=str(order_id) if order_id else None,
        )
    )
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return {"accepted": True, "updated": False, "duplicate": True, "event": event}

    if not order_id:
        session.commit()
        return {"accepted": True, "updated": False, "event": event}

    row = session.query(Payment).filter_by(razorpay_order_id=str(order_id)).one_or_none()
    if row is None:
        session.commit()
        return {"accepted": True, "updated": False, "event": event}

    if event in ("payment.captured", "order.paid"):
        apply_status(row, "CAPTURED", payment_id, webhook_verified=True)
    elif event == "payment.authorized":
        apply_status(row, "AUTHORIZED", payment_id, webhook_verified=True)
    elif event == "payment.failed":
        apply_status(row, "FAILED", payment_id, webhook_verified=True, failure_reason="webhook_failed")
    elif event in ("order.expired",):
        apply_status(row, "EXPIRED", webhook_verified=True, failure_reason="order_expired")
    else:
        session.commit()
        return {"accepted": True, "updated": False, "event": event}

    session.commit()
    return {"accepted": True, "updated": True, "status": row.status, "event": event}


def _db_from_request(request: Request) -> Session:
    return request.app.state.session_factory()


@router.post("/create-order")
def create_order_route(body: CreateOrderBody, request: Request):
    session = _db_from_request(request)
    try:
        return create_order(session, body)
    finally:
        session.close()


@router.post("/verify")
def verify_order_route(body: VerifyBody, request: Request):
    session = _db_from_request(request)
    try:
        return verify_order(session, body)
    finally:
        session.close()


@router.get("/history")
def history_route(request: Request):
    session = _db_from_request(request)
    try:
        return list_history(session)
    finally:
        session.close()


@router.get("/status/{order_id}")
def status_route(order_id: str, request: Request):
    session = _db_from_request(request)
    try:
        return payment_status(session, order_id)
    finally:
        session.close()


@router.post("/cancel")
def cancel_route(body: dict, request: Request):
    order_id = str((body or {}).get("razorpay_order_id") or "").strip()
    if not order_id:
        raise ApiError(400, "invalid_order", "order id is required")
    session = _db_from_request(request)
    try:
        return mark_cancelled(session, order_id)
    finally:
        session.close()


@router.post("/webhook")
async def webhook_route(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
):
    body = await request.body()
    if not x_razorpay_signature:
        raise ApiError(400, "missing_webhook_signature", "X-Razorpay-Signature is required")
    session = _db_from_request(request)
    try:
        return process_webhook(session, body, x_razorpay_signature)
    finally:
        session.close()
