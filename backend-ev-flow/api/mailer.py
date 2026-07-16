"""Transactional email over SMTP.

Env is read at call time (same pattern as security.py / google_oauth.py) so tests
can monkeypatch without reimporting. Works with any SMTP provider — Gmail app
password, SendGrid, Amazon SES, Mailgun, Brevo, etc.

Env vars:
  SMTP_HOST      e.g. smtp.gmail.com          (unset => email disabled)
  SMTP_PORT      default 587 (STARTTLS); use 465 for implicit TLS
  SMTP_USER      SMTP username / login
  SMTP_PASSWORD  SMTP password / app password / API key
  SMTP_FROM      From address (defaults to SMTP_USER)
  SMTP_SSL       "true" to force implicit TLS (auto-on when port == 465)
  SMTP_STARTTLS  "false" to disable STARTTLS (default true)
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional


class MailerNotConfigured(RuntimeError):
    """SMTP_HOST is not set, so no email can be sent."""


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def is_configured() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def send_email(to: str, subject: str, text_body: str, html_body: Optional[str] = None) -> None:
    host = os.getenv("SMTP_HOST", "")
    if not host:
        raise MailerNotConfigured("SMTP_HOST is not set")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM") or user or "no-reply@localhost"
    use_ssl = _flag("SMTP_SSL", port == 465)
    starttls = _flag("SMTP_STARTTLS", not use_ssl)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
            if user:
                server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if starttls:
                server.starttls(context=context)
            if user:
                server.login(user, password)
            server.send_message(msg)
