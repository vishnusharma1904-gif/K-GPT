"""Pydantic request/response models."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


# --- Auth -------------------------------------------------------------------
class SignupReq(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    # Student (default) or faculty. Faculty self-sign-up is admin-gated: the
    # account is created but BLOCKED (no session) until an admin approves it.
    role: str = "student"
    # Faculty-only, required at sign-up: department + contact mobile number.
    department: str | None = Field(default=None, max_length=64)
    mobile: str | None = Field(default=None, max_length=20)


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


class VerifyOtpReq(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


class ResendOtpReq(BaseModel):
    email: EmailStr


class AuthResp(BaseModel):
    """Unified signup/login response. When otp_required is True the caller must
    collect the emailed OTP and call /verify-otp; no access_token is issued yet.
    When approval_pending is True the account is a faculty account awaiting admin
    approval — email may be verified but no access_token is issued until approved."""
    otp_required: bool = False
    approval_pending: bool = False
    email: EmailStr | None = None
    access_token: str | None = None
    token_type: str = "bearer"
    user: dict | None = None


# --- Chat -------------------------------------------------------------------
class ChatReq(BaseModel):
    message: str = Field(min_length=0, max_length=8000)
    session_id: str | None = None
    persona: str = "kgpt"
    use_memory: bool = True
    premium: bool = False
    web_search: bool = False        # P33
    category: str | None = None     # P21 model picker override
    project_id: str | None = None   # P20 / P30
    images: list[str] | None = None  # P34 vision: data URLs or https image URLs
    model: str | None = None         # P21 explicit model pick (paid/admin only)
    strict: bool = False             # KB-only: answer solely from retrieved documents
    # Filename of a file the user just attached in the composer. Its content is
    # force-injected into context (no similarity threshold) so "summarise/convert
    # this file" works even when the query doesn't match the document text.
    attached_source: str | None = Field(default=None, max_length=300)


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
    # Student classification (cohort: course / branch / year / semester / section)
    full_name: str | None = Field(default=None, max_length=80)
    roll_no: str | None = Field(default=None, max_length=32)
    course: str | None = Field(default=None, max_length=32)
    branch: str | None = Field(default=None, max_length=48)
    admission_year: int | None = Field(default=None, ge=2000, le=2100)
    year: int | None = Field(default=None, ge=1, le=5)
    semester: int | None = Field(default=None, ge=1, le=10)
    section: str | None = Field(default=None, max_length=8)
    # Faculty classification (department + contact mobile)
    department: str | None = Field(default=None, max_length=64)
    mobile: str | None = Field(default=None, max_length=20)


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
