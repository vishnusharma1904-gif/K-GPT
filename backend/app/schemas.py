"""Pydantic request/response models."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


# --- Auth -------------------------------------------------------------------
class SignupReq(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ForgotReq(BaseModel):
    email: EmailStr


class ResetReq(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class VerifyReq(BaseModel):
    token: str


# --- Chat -------------------------------------------------------------------
class ChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    persona: str = "kgpt"
    use_memory: bool = True
    premium: bool = False
    web_search: bool = False        # P33
    category: str | None = None     # P21 model picker override
    project_id: str | None = None   # P20 / P30
    images: list[str] | None = None  # P34 vision: data URLs or https image URLs
    model: str | None = None         # P21 explicit model pick (paid/admin only)


class NewSessionReq(BaseModel):
    title: str = "New chat"
    persona: str = "kgpt"
    project_id: str | None = None


class SessionPatch(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None
    project_id: str | None = None


class FeedbackReq(BaseModel):
    message_id: str
    feedback: int = Field(ge=-1, le=1)   # -1 down, 0 clear, +1 up


# --- Memory -----------------------------------------------------------------
class MemoryReq(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    source: str | None = None
    kind: str = "note"
    project_id: str | None = None


# --- Projects (P20 / P30) ---------------------------------------------------
class ProjectReq(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: str | None = Field(default=None, max_length=4000)
    color: str = "brand"


class ProjectPatch(BaseModel):
    name: str | None = None
    instructions: str | None = None
    color: str | None = None
    archived: bool | None = None


# --- Preferences (P25 / P31 / P40) ------------------------------------------
class PrefsReq(BaseModel):
    response_style: str | None = None        # concise|balanced|detailed|formal
    custom_instructions: str | None = Field(default=None, max_length=2000)
    exam_mode: bool | None = None
    memory_enabled: bool | None = None
    web_search_enabled: bool | None = None


# --- Billing ----------------------------------------------------------------
class CreateOrderResp(BaseModel):
    order_id: str
    amount: int
    currency: str = "INR"
    key_id: str


class CreateOrderReq(BaseModel):
    plan: str = "semester"
    coupon: str | None = None


class VerifyPaymentReq(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
