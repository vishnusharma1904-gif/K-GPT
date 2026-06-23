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
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
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


def send_reset(to: str, link: str) -> bool:
    return send(to, "Reset your K-GPT password",
                f"We received a request to reset your K-GPT password.\n\n{link}\n\n"
                "This link expires in 24 hours. If you didn't ask for this, ignore it.")
