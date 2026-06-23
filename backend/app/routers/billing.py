"""Razorpay billing — orders, verify, webhook, plans, coupons, receipts (P15-P18).

Lifecycle: create_order (plan + optional coupon) -> client pays -> verify
(signature) OR webhook (server-to-server, idempotent) -> activate access with an
expiry derived from the plan duration. A receipt number + GST split are recorded
for finance. If Razorpay keys aren't set the endpoints 503 so the rest of the app
runs (admins grant access manually).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.security import current_user
from app.db import supabase_client as db
from app.schemas import CreateOrderReq, CreateOrderResp, VerifyPaymentReq

settings = get_settings()
router = APIRouter(prefix="/api/billing", tags=["billing"])


def _client():
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Online payments not configured. Ask admin to grant access.")
    import razorpay
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def _now():
    return datetime.now(timezone.utc)


def _gst_split(total_paise: int) -> int:
    """Return the GST portion (paise) of a GST-inclusive total."""
    g = settings.gst_percent
    return round(total_paise * g / (100 + g)) if g else 0


def _receipt_no() -> str:
    return f"KGPT-{settings.current_semester}-{secrets.token_hex(4).upper()}"


def _resolve_amount(plan_code: str, coupon_code: str | None) -> tuple[dict, int, str | None]:
    plan = db.get_plan(plan_code) or {"code": "semester",
                                      "price_inr": settings.semester_fee_inr * 100,
                                      "duration_days": 183, "tier": "normal",
                                      "name": "Semester Access"}
    amount = int(plan["price_inr"])
    applied = None
    if coupon_code:
        c = db.get_coupon(coupon_code)
        if c and (c.get("max_redemptions") is None
                  or (c.get("redeemed") or 0) < c["max_redemptions"]):
            amount = max(100, round(amount * (100 - int(c["percent_off"])) / 100))
            applied = coupon_code.upper()
    return plan, amount, applied


def _activate(user_id: str, plan: dict) -> str:
    expires = (_now() + timedelta(days=int(plan["duration_days"]))).isoformat()
    patch = {"sub_status": "active", "sub_expires_at": expires, "plan": plan["code"]}
    ptier = plan.get("tier") or "normal"
    if ptier != "normal":
        patch.update({"tier": ptier, "tier_override": True})
    db.update_user(user_id, patch)
    return expires


@router.get("/config")
async def config():
    return {
        "fee_inr": settings.semester_fee_inr,
        "semester": settings.current_semester,
        "online_enabled": bool(settings.razorpay_key_id),
        "key_id": settings.razorpay_key_id,
        "gst_percent": settings.gst_percent,
        "plans": db.list_plans() if settings.supabase_url else [],
    }


@router.get("/plans")
async def plans():
    return db.list_plans()


@router.post("/order", response_model=CreateOrderResp)
async def create_order(req: CreateOrderReq, claims: dict = Depends(current_user)):
    client = _client()
    plan, amount, applied = _resolve_amount(req.plan, req.coupon)
    order = client.order.create({"amount": amount, "currency": "INR",
                                 "notes": {"user_id": claims["user_id"], "plan": plan["code"],
                                           "semester": settings.current_semester}})
    db.create_payment({
        "user_id": claims["user_id"], "rzp_order_id": order["id"],
        "amount_inr": amount, "gst_inr": _gst_split(amount),
        "status": "created", "semester": settings.current_semester,
        "plan": plan["code"], "coupon": applied, "receipt_no": _receipt_no(),
    })
    return CreateOrderResp(order_id=order["id"], amount=amount,
                           key_id=settings.razorpay_key_id)


@router.post("/verify")
async def verify(req: VerifyPaymentReq, claims: dict = Depends(current_user)):
    body = f"{req.razorpay_order_id}|{req.razorpay_payment_id}".encode()
    expected = hmac.new(settings.razorpay_key_secret.encode(), body,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, req.razorpay_signature):
        db.update_payment(req.razorpay_order_id, {"status": "failed"})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment verification failed.")

    # Idempotency: if the webhook already activated this payment, don't double-apply.
    if db.get_payment_by_payment_id(req.razorpay_payment_id):
        u = db.get_user(claims["user_id"])
        return {"ok": True, "sub_status": u.get("sub_status"),
                "expires_at": u.get("sub_expires_at")}

    pay = db.update_payment  # alias
    plan_code = "semester"
    try:
        rows = db.list_payments(claims["user_id"])
        match = next((r for r in rows if r.get("rzp_order_id") == req.razorpay_order_id), None)
        plan_code = (match or {}).get("plan") or "semester"
        if match and match.get("coupon"):
            db.redeem_coupon(match["coupon"])
    except Exception:
        pass
    plan = db.get_plan(plan_code) or {"code": plan_code, "duration_days": 183, "tier": "normal"}
    expires = _activate(claims["user_id"], plan)
    pay(req.razorpay_order_id, {"status": "paid", "rzp_payment_id": req.razorpay_payment_id,
                                "expires_at": expires})
    return {"ok": True, "sub_status": "active", "expires_at": expires}


@router.post("/webhook")
async def webhook(request: Request):
    """Razorpay server-to-server webhook. Idempotent on rzp_payment_id."""
    raw = await request.body()
    sig = request.headers.get("x-razorpay-signature", "")
    secret = settings.razorpay_webhook_secret or settings.razorpay_key_secret
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature.")

    import json
    event = json.loads(raw or b"{}")
    entity = (event.get("payload", {}).get("payment", {}).get("entity", {}))
    payment_id = entity.get("id")
    order_id = entity.get("order_id")
    notes = entity.get("notes", {}) or {}
    if event.get("event") not in ("payment.captured", "order.paid") or not payment_id:
        return {"ok": True, "ignored": True}

    if db.get_payment_by_payment_id(payment_id):
        return {"ok": True, "duplicate": True}     # already processed

    user_id = notes.get("user_id")
    plan_code = notes.get("plan") or "semester"
    if user_id:
        plan = db.get_plan(plan_code) or {"code": plan_code, "duration_days": 183, "tier": "normal"}
        expires = _activate(user_id, plan)
        if order_id:
            db.update_payment(order_id, {"status": "paid", "rzp_payment_id": payment_id,
                                         "expires_at": expires, "webhook_seen": True})
    return {"ok": True}
