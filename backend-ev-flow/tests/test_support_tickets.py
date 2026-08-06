"""Tests for POST /api/v1/support/tickets, the Help Desk email endpoint.

Three things decide whether this endpoint is safe to expose:

* it is reachable WITHOUT a token (someone locked out is exactly who needs it),
  which makes it an open mail relay unless it is rate limited;
* every accepted request costs one outbound email, so the request bounds are the
  control, not a nicety; and
* it talks to a third party (SMTP), whose errors must never reach the caller --
  and neither must the caller's own message, which would otherwise come back in
  a 422 body and land in every log between here and the browser.

No test in this file opens a socket or needs a database: mailer.send_email is
replaced, and the signed-in case goes through FastAPI's dependency override
rather than a real token.
"""
from __future__ import annotations

import logging

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient   # noqa: E402

from api import mailer, models, rate_limit, security   # noqa: E402
from api.main import app                               # noqa: E402

client = TestClient(app)

ENDPOINT = "/api/v1/support/tickets"
SUPPORT_INBOX = "help@evflow.test"

SMTP_ENV_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM",
                 "SMTP_SSL", "SMTP_STARTTLS", "SUPPORT_EMAIL")

VALID_TICKET = {
    "subject": "Charging session stuck at starting",
    "message": "I started a session at pln_spklu-1 twenty minutes ago and it never began.",
    "reply_to": "budi@example.com",
}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """No inherited SMTP config, no carried-over rate-limit budget, no overrides."""
    for name in SMTP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    rate_limit.reset()
    yield
    rate_limit.reset()
    app.dependency_overrides.clear()


@pytest.fixture
def sent(monkeypatch):
    """Capture what would have been emailed, without an SMTP connection."""
    from api import main
    captured: list[dict] = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SUPPORT_EMAIL", SUPPORT_INBOX)
    monkeypatch.setattr(main.mailer, "send_email", lambda **kw: captured.append(kw))
    return captured


def _as_user(user: dict) -> None:
    """Pretend the caller presented a valid token for `user`, without a database."""
    app.dependency_overrides[security.optional_current_user] = lambda: user


# ==================================================== the happy path

@pytest.mark.integration
def test_an_anonymous_ticket_is_emailed_to_the_support_inbox(sent):
    r = client.post(ENDPOINT, json=VALID_TICKET)

    assert r.status_code == 202, r.text          # accepted for delivery; nothing is stored
    body = r.json()
    assert body["ticket_id"]
    assert body["message"]

    assert len(sent) == 1
    mail = sent[0]
    assert mail["to"] == SUPPORT_INBOX
    assert VALID_TICKET["subject"] in mail["subject"]
    assert VALID_TICKET["message"] in mail["text_body"]
    assert mail["reply_to"] == VALID_TICKET["reply_to"]
    assert "anonymous" in mail["text_body"]


@pytest.mark.integration
def test_the_ticket_id_is_reported_and_travels_with_the_email(sent):
    r = client.post(ENDPOINT, json=VALID_TICKET)
    ticket_id = r.json()["ticket_id"]
    assert ticket_id in sent[0]["text_body"], "support must be able to match a follow-up"


@pytest.mark.integration
def test_a_signed_in_ticket_carries_the_username_and_user_id(sent):
    _as_user({"id": "user-42", "username": "budi"})

    r = client.post(ENDPOINT, json=VALID_TICKET)

    assert r.status_code == 202, r.text
    text = sent[0]["text_body"]
    assert "budi" in text
    assert "user-42" in text
    assert "anonymous" not in text


@pytest.mark.integration
def test_a_signed_in_ticket_falls_back_to_the_email_when_there_is_no_username(sent):
    """Google sign-ups have an email and no username."""
    _as_user({"id": "user-43", "username": None, "email": "google-user@example.com"})

    client.post(ENDPOINT, json=VALID_TICKET)

    assert "google-user@example.com" in sent[0]["text_body"]


@pytest.mark.integration
def test_reply_to_is_optional(sent):
    payload = {k: v for k, v in VALID_TICKET.items() if k != "reply_to"}
    r = client.post(ENDPOINT, json=payload)

    assert r.status_code == 202, r.text
    assert sent[0]["reply_to"] is None
    assert "not supplied" in sent[0]["text_body"]


# ==================================================== destination resolution

@pytest.mark.integration
def test_support_email_wins_over_the_from_address(sent, monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "no-reply@evflow.test")
    client.post(ENDPOINT, json=VALID_TICKET)
    assert sent[0]["to"] == SUPPORT_INBOX


@pytest.mark.integration
def test_the_destination_falls_back_to_smtp_from(sent, monkeypatch):
    monkeypatch.delenv("SUPPORT_EMAIL", raising=False)
    monkeypatch.setenv("SMTP_FROM", "no-reply@evflow.test")

    r = client.post(ENDPOINT, json=VALID_TICKET)

    assert r.status_code == 202, r.text
    assert sent[0]["to"] == "no-reply@evflow.test"


@pytest.mark.integration
def test_the_destination_falls_back_to_smtp_user_when_the_login_is_the_address(sent, monkeypatch):
    monkeypatch.delenv("SUPPORT_EMAIL", raising=False)
    monkeypatch.setenv("SMTP_USER", "mailer@evflow.test")

    r = client.post(ENDPOINT, json=VALID_TICKET)

    assert r.status_code == 202, r.text
    assert sent[0]["to"] == "mailer@evflow.test"


# ==================================================== failure paths

@pytest.mark.integration
def test_unconfigured_smtp_returns_503_and_does_not_pretend_to_have_sent(monkeypatch):
    from api import main
    calls: list = []
    monkeypatch.setattr(main.mailer, "send_email", lambda **kw: calls.append(kw))
    # SMTP_HOST is unset by the autouse fixture.

    r = client.post(ENDPOINT, json=VALID_TICKET)

    assert r.status_code == 503, r.text
    assert calls == [], "no delivery may be attempted when SMTP is not configured"


@pytest.mark.integration
def test_the_503_names_no_smtp_setting_and_echoes_no_message(monkeypatch):
    r = client.post(ENDPOINT, json=VALID_TICKET)
    detail = r.json()["detail"]
    assert VALID_TICKET["message"] not in detail
    for leak in ("SMTP", "smtp", "SUPPORT_EMAIL"):
        assert leak not in detail


@pytest.mark.integration
def test_a_configured_destination_without_smtp_is_still_503(monkeypatch):
    """SUPPORT_EMAIL alone sends nothing; the transport has to exist too."""
    monkeypatch.setenv("SUPPORT_EMAIL", SUPPORT_INBOX)
    r = client.post(ENDPOINT, json=VALID_TICKET)
    assert r.status_code == 503, r.text


@pytest.mark.integration
def test_an_smtp_failure_is_502_and_leaks_neither_the_provider_nor_the_message(sent, monkeypatch, caplog):
    from api import main

    provider_detail = "535 5.7.8 auth failed for mailer@smtp.internal.test"

    def _boom(**kw):
        raise RuntimeError(provider_detail)

    monkeypatch.setattr(main.mailer, "send_email", _boom)

    with caplog.at_level(logging.ERROR):
        r = client.post(ENDPOINT, json=VALID_TICKET)

    assert r.status_code == 502, r.text
    detail = r.json()["detail"]
    assert provider_detail not in detail
    assert "535" not in detail
    assert "smtp.internal.test" not in detail
    assert VALID_TICKET["message"] not in detail
    # ...but an operator can still find it, with the ticket id to tie it back.
    assert provider_detail in caplog.text


@pytest.mark.integration
def test_a_mailer_not_configured_race_is_also_handled(sent, monkeypatch):
    """is_configured() passed, then SMTP_HOST went away before the send."""
    from api import main
    monkeypatch.setattr(main.mailer, "send_email",
                        lambda **kw: (_ for _ in ()).throw(mailer.MailerNotConfigured("gone")))

    r = client.post(ENDPOINT, json=VALID_TICKET)

    assert r.status_code == 502, r.text
    assert "gone" not in r.text


# ==================================================== request bounds

@pytest.mark.integration
@pytest.mark.parametrize("payload", [
    {},
    {"subject": "hi"},                                            # message missing
    {"message": "a real problem description here"},               # subject missing
    {"subject": "ab", "message": "a real problem description"},   # subject too short
    {"subject": "a real subject", "message": "too short"},        # message too short
])
def test_incomplete_or_undersized_tickets_are_rejected(sent, payload):
    r = client.post(ENDPOINT, json=payload)
    assert r.status_code == 422, r.text
    assert sent == []


@pytest.mark.integration
def test_an_oversized_subject_is_rejected(sent):
    payload = {**VALID_TICKET, "subject": "x" * (models.SUPPORT_SUBJECT_MAX_CHARS + 1)}
    r = client.post(ENDPOINT, json=payload)
    assert r.status_code == 422, r.text
    assert sent == []


@pytest.mark.integration
def test_an_oversized_message_is_rejected_without_coming_back_in_the_response(sent):
    """The 422 must not mail the ticket body back to the caller.

    FastAPI's default validation handler echoes the rejected input in
    detail[].input. For a 5000-character support message that means the whole
    thing travels back through the response body and into every log on the way.
    """
    marker = "SECRET-TICKET-BODY-MARKER"
    payload = {**VALID_TICKET,
               "message": marker + "y" * models.SUPPORT_MESSAGE_MAX_CHARS}

    r = client.post(ENDPOINT, json=payload)

    assert r.status_code == 422, r.text
    assert marker not in r.text
    assert sent == []


@pytest.mark.integration
@pytest.mark.parametrize("bad", ["not-an-address", "no-at-sign.example", "budi@nodot", "@example.com"])
def test_an_unusable_reply_address_is_rejected(sent, bad):
    r = client.post(ENDPOINT, json={**VALID_TICKET, "reply_to": bad})
    assert r.status_code == 422, r.text
    assert sent == []


@pytest.mark.integration
@pytest.mark.parametrize("field", ["subject", "reply_to"])
def test_a_line_break_in_a_header_field_is_rejected(sent, field):
    """SMTP header injection: a CR/LF ends our header and starts the caller's."""
    injection = "legit\r\nBcc: victim@example.com"
    r = client.post(ENDPOINT, json={**VALID_TICKET, field: injection})
    assert r.status_code == 422, r.text
    assert sent == []


@pytest.mark.integration
def test_line_breaks_in_the_message_body_are_fine(sent):
    """Only headers are injectable. A multi-line bug report is normal."""
    payload = {**VALID_TICKET, "message": "step one\nstep two\nstep three, at length"}
    r = client.post(ENDPOINT, json=payload)
    assert r.status_code == 202, r.text
    assert "step two" in sent[0]["text_body"]


# ==================================================== rate limiting

@pytest.mark.integration
def test_one_caller_is_cut_off_after_the_per_ip_budget(sent):
    limit = rate_limit.SUPPORT_TICKET_RATE_LIMIT_REQUESTS
    for i in range(limit):
        assert client.post(ENDPOINT, json=VALID_TICKET).status_code == 202, f"request {i}"

    r = client.post(ENDPOINT, json=VALID_TICKET)

    assert r.status_code == 429, r.text
    assert len(sent) == limit, "the refused request must not have been emailed"


@pytest.mark.integration
def test_the_deployment_wide_budget_stops_many_callers_adding_up(sent, monkeypatch):
    """Per-IP alone is trivially sidestepped from a handful of addresses."""
    monkeypatch.setattr(rate_limit, "SUPPORT_TICKET_GLOBAL_RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(rate_limit, "SUPPORT_TICKET_RATE_LIMIT_REQUESTS", 100)

    statuses = []
    for n in range(4):
        # A distinct client address per call, so only the global budget can bite.
        c = TestClient(app, client=(f"10.0.0.{n}", 5000 + n))
        statuses.append(c.post(ENDPOINT, json=VALID_TICKET).status_code)

    assert statuses == [202, 202, 202, 429], statuses
    assert len(sent) == 3


@pytest.mark.integration
def test_the_429_does_not_echo_the_message(sent):
    for _ in range(rate_limit.SUPPORT_TICKET_RATE_LIMIT_REQUESTS):
        client.post(ENDPOINT, json=VALID_TICKET)
    r = client.post(ENDPOINT, json=VALID_TICKET)
    assert r.status_code == 429
    assert VALID_TICKET["message"] not in r.text


@pytest.mark.integration
def test_the_rate_limit_log_line_carries_no_ticket_content(sent, caplog):
    with caplog.at_level(logging.WARNING):
        for _ in range(rate_limit.SUPPORT_TICKET_RATE_LIMIT_REQUESTS + 1):
            client.post(ENDPOINT, json=VALID_TICKET)
    assert "support ticket rate limit hit" in caplog.text
    assert VALID_TICKET["message"] not in caplog.text
    assert VALID_TICKET["reply_to"] not in caplog.text


# ==================================================== optional authentication

@pytest.mark.unit
def test_optional_current_user_is_none_without_a_header():
    assert security.optional_current_user(None) is None


@pytest.mark.unit
def test_optional_current_user_is_none_for_a_token_it_cannot_use(monkeypatch):
    """An expired session must not stop someone writing to support."""
    monkeypatch.setenv("JWT_SECRET", "unit-test-jwt-secret-0123456789abcdef")
    assert security.optional_current_user("Bearer not-a-real-token") is None
    assert security.optional_current_user("Basic anything") is None


@pytest.mark.integration
def test_a_garbage_token_still_gets_a_ticket_through_as_anonymous(sent, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-jwt-secret-0123456789abcdef")

    r = client.post(ENDPOINT, json=VALID_TICKET,
                    headers={"Authorization": "Bearer expired.rubbish.token"})

    assert r.status_code == 202, r.text
    assert "anonymous" in sent[0]["text_body"]


# ==================================================== models + mailer units

@pytest.mark.unit
def test_the_request_model_trims_a_reply_address():
    ticket = models.SupportTicketRequest(**{**VALID_TICKET, "reply_to": "  budi@example.com  "})
    assert ticket.reply_to == "budi@example.com"


@pytest.mark.unit
def test_a_blank_reply_address_becomes_none():
    ticket = models.SupportTicketRequest(**{**VALID_TICKET, "reply_to": "   "})
    assert ticket.reply_to is None


@pytest.mark.unit
def test_mailer_refuses_a_header_carrying_a_line_break():
    for name, value in (("subject", "a\r\nBcc: x@y.test"), ("to", "a@b.test\nBcc: x@y.test"),
                        ("reply_to", "a@b.test\r\nBcc: x@y.test")):
        with pytest.raises(ValueError):
            mailer._header_safe(name, value)


@pytest.mark.unit
def test_mailer_sets_reply_to_on_the_outgoing_message(monkeypatch):
    captured: list = []

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context=None):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            captured.append(msg)

    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    mailer.send_email("help@evflow.test", "subject", "body", reply_to="budi@example.com")

    assert captured[0]["Reply-To"] == "budi@example.com"


# ==================================================== published contract

@pytest.mark.integration
def test_the_endpoint_is_documented_in_the_openapi_schema():
    spec = client.get("/openapi.json").json()
    op = spec["paths"][ENDPOINT]["post"]
    assert op["tags"] == ["support"]
    assert {"429", "502", "503"} <= set(op["responses"])

    schema = spec["components"]["schemas"]["SupportTicketRequest"]["properties"]
    assert schema["subject"]["maxLength"] == models.SUPPORT_SUBJECT_MAX_CHARS
    assert schema["message"]["maxLength"] == models.SUPPORT_MESSAGE_MAX_CHARS
    # Swagger has to explain each field, since this form is the whole contract.
    assert schema["subject"]["description"]
    assert schema["message"]["description"]
