"""Transactional email (P2) — SMTP if configured, console fallback in dev.

Used for email verification and password-reset links. Fail-soft: a send error
never breaks signup; in dev the link is printed to the server log so you can
copy it. Returns True if actually sent over SMTP.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

settings = get_settings()


def send(to: str, subject: str, body: str) -> bool:
    if not settings.smtp_host:
        # Dev fallback — surface the content so links are usable without SMTP.
        print(f"\n[mailer:dev] To: {to}\nSubject: {subject}\n{body}\n")
        return False
    try:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        # Port 465 = implicit SSL (use SMTP_SSL, no starttls). Port 587/25 =
        # plain connection upgraded with STARTTLS. Picking the wrong one is the
        # classic "email silently never sends" bug (e.g. Zoho/Gmail on 465).
        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        with server as s:
            if settings.smtp_port != 465:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[mailer:error] {e}")
        return False


def send_verification(to: str, link: str) -> bool:
    return send(to, "Verify your K-GPT account",
                f"Welcome to K-GPT!\n\nConfirm your email to start chatting:\n{link}\n\n"
                "This link expires in 24 hours. If you didn't sign up, ignore this.")


def send_otp(to: str, code: str, ttl_minutes: int = 10) -> bool:
    return send(to, f"Your K-GPT verification code: {code}",
                f"Welcome to K-GPT!\n\nYour email verification code is:\n\n    {code}\n\n"
                f"Enter it on the verification screen to activate your account. "
                f"This code expires in {ttl_minutes} minutes.\n\n"
                "Can't find this email? Please check your Spam / Junk folder too.\n\n"
                "If you didn't sign up, you can safely ignore this email.")


def send_reset(to: str, link: str) -> bool:
    return send(to, "Reset your K-GPT password",
                f"We received a request to reset your K-GPT password.\n\n{link}\n\n"
                "This link expires in 24 hours. If you didn't ask for this, ignore it.")
