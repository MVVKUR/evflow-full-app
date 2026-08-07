"""Authentication / accounts / transactional-email coverage.

Domain under test:
  api/security.py            password hashing, JWT, OAuth state, current_user
  api/users_repo.py          user lookup + password rotation
  api/password_reset_repo.py single-use, time-limited reset tokens
  api/mailer.py              SMTP transport selection and send path
  api/google_oauth.py        auth URL + code exchange error handling
  api/main.py                /api/v1/auth/* and /api/v1/users/me

No test in this file opens a socket: the SMTP transport is a fake injected into
``mailer.smtplib`` and every httpx call is replaced with an in-process double.

Tests marked ``xfail`` document behaviour the system SHOULD have. They are not
assertions of the current (defective) behaviour -- see the report accompanying
this file.
"""
from __future__ import annotations

import ssl
import time
import uuid

import pytest

from tests.conftest import requires_db

pytest.importorskip("bcrypt")
pytest.importorskip("jwt")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import httpx  # noqa: E402
import jwt as pyjwt  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import google_oauth, mailer, security  # noqa: E402

# Both >= security.MIN_SECRET_LENGTH and neither starts with a placeholder prefix.
TEST_SECRET = "auth-coverage-jwt-secret-0123456789abcdef"
OTHER_SECRET = "an-entirely-unrelated-signing-key-9876543210"

SMTP_ENV_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
                 "SMTP_FROM", "SMTP_SSL", "SMTP_STARTTLS")


# ============================================================ fakes / fixtures

class _FakeSMTPBase:
    """Stand-in for smtplib.SMTP / SMTP_SSL. Records calls, never opens a socket."""

    kind = "?"
    log: list = []

    def __init__(self, host, port, context=None, timeout=None):
        self.record = {"kind": self.kind, "host": host, "port": port,
                       "ctor_context": context, "timeout": timeout,
                       "starttls_context": None, "login": None, "message": None,
                       "calls": [], "exited": False}
        type(self).log.append(self.record)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.record["exited"] = True
        return False

    def starttls(self, context=None):
        self.record["starttls_context"] = context
        self.record["calls"].append("starttls")

    def login(self, user, password):
        self.record["login"] = (user, password)
        self.record["calls"].append("login")

    def send_message(self, msg):
        self.record["message"] = msg
        self.record["calls"].append("send_message")


@pytest.fixture
def smtp_log(monkeypatch):
    """Inject the fake SMTP transports and clear all SMTP_* env for the test."""
    for name in SMTP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    log: list = []
    plain = type("_FakeSMTP", (_FakeSMTPBase,), {"kind": "plain", "log": log})
    secure = type("_FakeSMTPSSL", (_FakeSMTPBase,), {"kind": "ssl", "log": log})
    monkeypatch.setattr(mailer.smtplib, "SMTP", plain)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", secure)
    return log


class _Resp:
    """Minimal httpx.Response double."""

    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


def _client(monkeypatch, **env) -> TestClient:
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("FRONTEND_URL", "https://frontend.test")
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "60")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from api import main
    return TestClient(main.app)


def _uname() -> str:
    return "cov-" + uuid.uuid4().hex[:10]


def _register(client, username=None, password="s3cret123", email=None, **extra):
    username = username or _uname()
    body = {"username": username, "password": password}
    if email is not None:
        body["email"] = email
    body.update(extra)
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    return username, password, r.json()


# ============================================================== mailer.py unit

@pytest.mark.unit
def test_is_configured_follows_smtp_host(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert mailer.is_configured() is False
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    assert mailer.is_configured() is True


@pytest.mark.unit
def test_send_email_without_smtp_host_raises_and_opens_no_connection(smtp_log):
    with pytest.raises(mailer.MailerNotConfigured):
        mailer.send_email("a@b.test", "s", "body")
    assert smtp_log == [], "no transport may be constructed when SMTP is unconfigured"


@pytest.mark.unit
def test_send_email_starttls_path_logs_in_and_sends(smtp_log, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_USER", "mailer@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")

    mailer.send_email("driver@example.test", "Reset your EVFlow password", "plain text")

    assert len(smtp_log) == 1
    rec = smtp_log[0]
    assert rec["kind"] == "plain"                      # not implicit TLS
    assert (rec["host"], rec["port"]) == ("smtp.example.test", 587)
    assert rec["timeout"] == 20                        # never hang a worker forever
    # STARTTLS must be negotiated BEFORE the password is put on the wire.
    assert rec["calls"] == ["starttls", "login", "send_message"]
    assert isinstance(rec["starttls_context"], ssl.SSLContext)
    assert rec["starttls_context"].verify_mode == ssl.CERT_REQUIRED
    assert rec["starttls_context"].check_hostname is True
    assert rec["login"] == ("mailer@example.test", "app-password")
    assert rec["exited"] is True                       # connection closed

    msg = rec["message"]
    assert msg["To"] == "driver@example.test"
    assert msg["Subject"] == "Reset your EVFlow password"
    assert msg["From"] == "mailer@example.test"        # defaults to SMTP_USER
    assert "plain text" in msg.get_content()


@pytest.mark.unit
def test_port_465_selects_implicit_tls(smtp_log, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")

    mailer.send_email("a@b.test", "s", "body")

    rec = smtp_log[0]
    assert rec["kind"] == "ssl"
    assert rec["port"] == 465
    assert isinstance(rec["ctor_context"], ssl.SSLContext)
    assert "starttls" not in rec["calls"], "STARTTLS is meaningless on an implicit-TLS socket"
    assert rec["calls"] == ["login", "send_message"]


@pytest.mark.unit
def test_smtp_ssl_flag_forces_implicit_tls_on_a_non_465_port(smtp_log, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "2465")
    monkeypatch.setenv("SMTP_SSL", "true")

    mailer.send_email("a@b.test", "s", "body")

    assert smtp_log[0]["kind"] == "ssl"
    assert smtp_log[0]["port"] == 2465


@pytest.mark.unit
def test_starttls_can_be_disabled_but_mail_is_still_sent(smtp_log, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")

    mailer.send_email("a@b.test", "s", "body")

    rec = smtp_log[0]
    assert rec["kind"] == "plain"
    assert rec["calls"] == ["login", "send_message"]


@pytest.mark.unit
def test_anonymous_relay_skips_login_and_uses_fallback_from(smtp_log, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "relay.internal.test")

    mailer.send_email("a@b.test", "s", "body")

    rec = smtp_log[0]
    assert rec["login"] is None, "must not call LOGIN with an empty username"
    assert rec["calls"] == ["starttls", "send_message"]
    assert rec["message"]["From"] == "no-reply@localhost"


@pytest.mark.unit
def test_smtp_from_overrides_smtp_user(smtp_log, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_USER", "api-key-user")
    monkeypatch.setenv("SMTP_PASSWORD", "k")
    monkeypatch.setenv("SMTP_FROM", "EVFlow <no-reply@evflow.test>")

    mailer.send_email("a@b.test", "s", "body")

    assert smtp_log[0]["message"]["From"] == "EVFlow <no-reply@evflow.test>"


@pytest.mark.unit
def test_html_body_produces_multipart_alternative(smtp_log, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")

    mailer.send_email("a@b.test", "s", "text fallback", html_body="<p>rich</p>")

    msg = smtp_log[0]["message"]
    assert msg.get_content_type() == "multipart/alternative"
    subtypes = [p.get_content_subtype() for p in msg.iter_parts()]
    assert subtypes == ["plain", "html"], "text/plain must come first for non-HTML clients"
    bodies = [p.get_content() for p in msg.iter_parts()]
    assert "text fallback" in bodies[0]
    assert "<p>rich</p>" in bodies[1]


@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("TRUE", True), (" Yes ", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("", False), ("maybe", False),
])
def test_flag_parses_truthy_env_values(monkeypatch, raw, expected):
    monkeypatch.setenv("SMTP_SSL", raw)
    assert mailer._flag("SMTP_SSL", not expected) is expected


@pytest.mark.unit
def test_flag_falls_back_to_default_when_unset(monkeypatch):
    monkeypatch.delenv("SMTP_SSL", raising=False)
    assert mailer._flag("SMTP_SSL", True) is True
    assert mailer._flag("SMTP_SSL", False) is False


# ======================================================= security.py unit

@pytest.mark.unit
@pytest.mark.parametrize("stored", ["", "not-a-bcrypt-hash", "$2b$12$tooshort"])
def test_verify_password_returns_false_for_a_corrupt_stored_hash(stored):
    # A damaged password_hash column must fail the login, never raise a 500.
    assert security.verify_password("s3cret123", stored) is False


@pytest.mark.unit
def test_hash_password_is_salted_and_verifies_only_the_right_password():
    a = security.hash_password("s3cret123")
    b = security.hash_password("s3cret123")
    assert a != b, "bcrypt must salt: two hashes of the same password differ"
    assert security.verify_password("s3cret123", a)
    assert security.verify_password("s3cret123", b)
    assert not security.verify_password("s3cret1234", a)
    assert not security.verify_password("", a)


# --------------------------------------------- the 72-BYTE bcrypt password cap

@pytest.mark.unit
@pytest.mark.parametrize("plain,fits", [
    ("a" * 71, True),
    ("a" * 72, True),
    ("a" * 73, False),
    ("é" * 36, True),           # 72 bytes exactly
    ("é" * 37, False),          # 74 bytes: only 37 CHARACTERS, still over
    ("pässwörd-ñ" * 6, False),  # 60 characters, 78 bytes
    ("🔋" * 18, True),           # 72 bytes
    ("🔋" * 19, False),          # 76 bytes
])
def test_password_length_is_measured_in_utf8_bytes_not_characters(plain, fits):
    assert (security.password_length_problem(plain) is None) is fits
    if not fits:
        assert "bytes" in security.password_length_problem(plain)


@pytest.mark.unit
def test_hash_password_refuses_an_over_long_secret_with_a_readable_message():
    """Non-HTTP callers (the seeding script) get a clear error, not a bcrypt one."""
    with pytest.raises(ValueError) as e:
        security.hash_password("é" * 40)
    assert "72 bytes" in str(e.value)
    # ...and the boundary value still hashes.
    assert security.verify_password("é" * 36, security.hash_password("é" * 36))


@pytest.mark.unit
def test_verify_password_never_raises_and_still_accepts_a_legacy_long_password():
    """An account whose hash predates the cap must not be locked out.

    Older bcrypt truncated silently, so such a hash covers only the first 72
    bytes. verify_password truncates the candidate the same way instead of
    refusing it outright (which would be a permanent lockout) or raising
    (which would be a 500 on /auth/login).
    """
    import bcrypt
    legacy_hash = bcrypt.hashpw(("a" * 200).encode()[:72], bcrypt.gensalt()).decode()

    assert security.verify_password("a" * 200, legacy_hash) is True
    assert security.verify_password("a" * 72, legacy_hash) is True
    # Truncation must not turn every long string into a master key.
    assert security.verify_password("b" * 200, legacy_hash) is False


def _auth(token: str) -> str:
    return f"Bearer {token}"


@pytest.fixture
def fake_user(monkeypatch):
    """Make security.current_user resolve one in-memory user, no DB needed."""
    from api import users_repo
    state = {"user": {"id": "u-1", "username": "budi", "password_changed_at": None}}

    def _get_by_id(user_id):
        u = state["user"]
        return u if (u and u["id"] == user_id) else None

    monkeypatch.setattr(users_repo, "get_by_id", _get_by_id)
    return state


@pytest.mark.unit
def test_current_user_accepts_a_well_formed_token(monkeypatch, fake_user):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    token = security.create_access_token("u-1")
    assert security.current_user(_auth(token))["username"] == "budi"


@pytest.mark.unit
@pytest.mark.parametrize("header", [
    None,                       # missing header entirely
    "",                         # empty header
    "abc.def.ghi",              # raw token, no scheme
    "Bearer",                   # scheme with no token and no space
    "Basic dXNlcjpwYXNz",       # wrong scheme
    "bearer abc.def.ghi",       # lowercase scheme -- RFC 6750 is case-insensitive
    "Token abc.def.ghi",
])
def test_current_user_rejects_missing_or_malformed_authorization_header(
        monkeypatch, fake_user, header):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    with pytest.raises(HTTPException) as e:
        security.current_user(header)
    assert e.value.status_code == 401


@pytest.mark.unit
def test_current_user_rejects_a_token_signed_with_the_wrong_secret(monkeypatch, fake_user):
    forged = pyjwt.encode({"sub": "u-1", "iat": int(time.time()),
                           "exp": int(time.time()) + 3600},
                          OTHER_SECRET, algorithm="HS256")
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    with pytest.raises(HTTPException) as e:
        security.current_user(_auth(forged))
    assert e.value.status_code == 401
    assert e.value.detail == "invalid or expired token"


@pytest.mark.unit
def test_current_user_rejects_an_expired_token(monkeypatch, fake_user):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "-1")   # minted already-expired
    expired = security.create_access_token("u-1")
    with pytest.raises(HTTPException) as e:
        security.current_user(_auth(expired))
    assert e.value.status_code == 401


@pytest.mark.unit
def test_current_user_rejects_an_alg_none_token(monkeypatch, fake_user):
    """The classic JWT downgrade: an unsigned token must never authenticate."""
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    unsigned = pyjwt.encode({"sub": "u-1", "iat": int(time.time()),
                             "exp": int(time.time()) + 3600},
                            key=None, algorithm="none")
    with pytest.raises(HTTPException) as e:
        security.current_user(_auth(unsigned))
    assert e.value.status_code == 401


@pytest.mark.unit
@pytest.mark.parametrize("weak", ["", "too-short", "change-me-to-a-real-secret-value-abc"])
def test_current_user_fails_closed_when_the_server_secret_is_weak(
        monkeypatch, fake_user, weak):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    good = security.create_access_token("u-1")
    monkeypatch.setenv("JWT_SECRET", weak)
    with pytest.raises(HTTPException) as e:
        security.current_user(_auth(good))
    assert e.value.status_code == 401


@pytest.mark.unit
def test_current_user_rejects_a_token_for_a_deleted_user(monkeypatch, fake_user):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    token = security.create_access_token("u-1")
    fake_user["user"] = None                      # account removed after issuance
    with pytest.raises(HTTPException) as e:
        security.current_user(_auth(token))
    assert e.value.status_code == 401
    assert e.value.detail == "user not found"


@pytest.mark.unit
def test_current_user_rejects_a_token_minted_before_the_password_changed(
        monkeypatch, fake_user):
    from datetime import datetime, timedelta, timezone  # noqa: F401
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    token = security.create_access_token("u-1")
    fake_user["user"]["password_changed_at"] = datetime.now(timezone.utc) + timedelta(seconds=30)

    with pytest.raises(HTTPException) as e:
        security.current_user(_auth(token))
    assert e.value.status_code == 401
    assert e.value.detail == "session expired, please log in again"

    # ...and a token comfortably newer than the change is still good.
    fake_user["user"]["password_changed_at"] = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert security.current_user(_auth(token))["id"] == "u-1"


@pytest.mark.unit
def test_a_token_minted_just_after_a_password_change_is_accepted(monkeypatch, fake_user):
    """FIXED: `iat` now carries sub-second precision, so the comparison is exact.

    Was: iat was int(time.time()), floored to a whole second, and compared
    against a microsecond timestamptz. The token the reset flow itself issues
    looked older than the change for the rest of that second, so the user was
    logged straight back out ("session expired").
    """
    from datetime import datetime, timezone
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    second = float(int(time.time()))
    # Password changed at .25s into the second; the user logs in 0.5s LATER.
    fake_user["user"]["password_changed_at"] = datetime.fromtimestamp(second + 0.25, timezone.utc)
    monkeypatch.setattr(security.time, "time", lambda: second + 0.75)

    token = security.create_access_token("u-1")   # iat floors to `second`

    assert security.current_user(_auth(token))["id"] == "u-1"


@pytest.mark.unit
@pytest.mark.parametrize("offset_s", [-0.001, -0.05, -0.999, -1.0, -60.0, -86400.0])
def test_a_token_minted_before_the_change_is_still_rejected(monkeypatch, fake_user, offset_s):
    """The security property, pinned at the millisecond.

    Fixing the false rejection must NOT be done by widening the window: a token
    minted even one millisecond before the password change has to die, or a
    reset stops logging out a stolen session. Without this, "accept a token
    minted after the change" would also be satisfied by deleting the check.
    """
    from datetime import datetime, timezone
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    # Anchored in the recent PAST: PyJWT itself refuses a token whose iat is in
    # the future, so the mint clock must never be moved forward of the real one.
    minted_at = time.time() - 1.0

    monkeypatch.setattr(security.time, "time", lambda: minted_at)
    stolen = security.create_access_token("u-1")
    # The password changed |offset_s| AFTER the stolen token was minted.
    fake_user["user"]["password_changed_at"] = datetime.fromtimestamp(
        minted_at - offset_s, timezone.utc)

    with pytest.raises(HTTPException) as e:
        security.current_user(_auth(stolen))
    assert (e.value.status_code, e.value.detail) == (401, "session expired, please log in again")


@pytest.mark.unit
@pytest.mark.parametrize("offset_s", [0.0, 0.001, 0.05, 0.999, 1.0, 60.0])
def test_a_token_minted_at_or_after_the_change_is_accepted(monkeypatch, fake_user, offset_s):
    """The other half of the same boundary: no false rejection anywhere above it."""
    from datetime import datetime, timezone
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    minted_at = time.time() - 1.0          # never ahead of the real clock

    monkeypatch.setattr(security.time, "time", lambda: minted_at)
    fresh = security.create_access_token("u-1")
    # The password changed `offset_s` BEFORE this token was minted.
    fake_user["user"]["password_changed_at"] = datetime.fromtimestamp(
        minted_at - offset_s, timezone.utc)

    assert security.current_user(_auth(fresh))["id"] == "u-1"


@pytest.mark.unit
def test_iat_keeps_sub_second_precision_and_exp_stays_a_whole_second(monkeypatch):
    """`iat` gained precision; `exp` deliberately did not change shape."""
    import jwt
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "60")
    minted_at = 1_700_000_000.123456
    monkeypatch.setattr(security.time, "time", lambda: minted_at)

    # Claim SHAPE is what is under test here, so the time-based checks that would
    # (correctly) reject this fabricated 2023 instant are switched off.
    payload = jwt.decode(security.create_access_token("u-1"), TEST_SECRET,
                         algorithms=["HS256"],
                         options={"verify_exp": False, "verify_iat": False})

    assert payload["iat"] == pytest.approx(minted_at, abs=1e-6)
    assert payload["iat"] != int(payload["iat"]), "the fraction is the whole point"
    assert payload["exp"] == int(minted_at) + 3600
    assert isinstance(payload["exp"], int)


@pytest.mark.unit
def test_a_legacy_whole_second_token_errs_towards_rejection(monkeypatch, fake_user):
    """Tokens minted before this fix still floor; that must fail SAFE, not open."""
    from datetime import datetime, timezone
    import jwt
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    second = float(int(time.time()))

    legacy = jwt.encode({"sub": "u-1", "iat": int(second), "exp": int(second) + 3600},
                        TEST_SECRET, algorithm="HS256")
    fake_user["user"]["password_changed_at"] = datetime.fromtimestamp(second + 0.5, timezone.utc)

    with pytest.raises(HTTPException) as e:
        security.current_user(_auth(legacy))
    assert e.value.status_code == 401


@pytest.mark.unit
def test_password_change_check_is_skipped_when_the_column_is_null(monkeypatch, fake_user):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    fake_user["user"]["password_changed_at"] = None
    token = security.create_access_token("u-1")
    assert security.current_user(_auth(token))["id"] == "u-1"


# --------------------------------------------------- OAuth state (CSRF) unit

@pytest.mark.unit
def test_state_signed_with_another_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", OTHER_SECRET)
    foreign = security.sign_state()
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    assert security.verify_state(foreign) is False


@pytest.mark.unit
def test_state_with_a_swapped_nonce_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    _, ts_a, sig_a = security.sign_state().split(".")
    nonce_b, _, _ = security.sign_state().split(".")
    # Splicing another session's nonce onto this signature must not verify.
    assert security.verify_state(f"{nonce_b}.{ts_a}.{sig_a}") is False


@pytest.mark.unit
def test_future_dated_state_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    now = time.time()
    monkeypatch.setattr(security.time, "time", lambda: now + 3600)
    from_the_future = security.sign_state()
    monkeypatch.setattr(security.time, "time", lambda: now)
    assert security.verify_state(from_the_future) is False


@pytest.mark.unit
def test_state_at_the_exact_max_age_boundary_is_still_accepted(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    now = float(int(time.time()))
    monkeypatch.setattr(security.time, "time", lambda: now - security.STATE_MAX_AGE_SECONDS)
    edge = security.sign_state()
    monkeypatch.setattr(security.time, "time", lambda: now)
    assert security.verify_state(edge) is True


@pytest.mark.unit
def test_state_has_extra_segments_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    assert security.verify_state(security.sign_state() + ".extra") is False
    assert security.verify_state("") is False


# ==================================================== google_oauth.py unit

@pytest.mark.unit
def test_build_auth_url_carries_state_and_forces_account_choice(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://api.test/cb")
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    state = security.sign_state()

    url = google_oauth.build_auth_url(state)

    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == google_oauth.AUTH_URL
    assert q["state"] == [state]
    assert q["redirect_uri"] == ["https://api.test/cb"]
    assert q["response_type"] == ["code"]
    assert q["prompt"] == ["select_account"]
    assert "client_secret" not in q, "the client secret must never reach the browser"


@pytest.mark.unit
def test_exchange_code_wraps_a_token_endpoint_error(monkeypatch):
    monkeypatch.setattr(google_oauth.httpx, "post",
                        lambda url, **kw: _Resp(400, text="invalid_grant"))
    with pytest.raises(google_oauth.GoogleOAuthError) as e:
        google_oauth.exchange_code("stale-code")
    assert "400" in str(e.value)
    assert "invalid_grant" in str(e.value)


@pytest.mark.unit
def test_exchange_code_wraps_a_userinfo_error(monkeypatch):
    monkeypatch.setattr(google_oauth.httpx, "post",
                        lambda url, **kw: _Resp(200, {"access_token": "at"}))
    monkeypatch.setattr(google_oauth.httpx, "get",
                        lambda url, **kw: _Resp(401, text="bad token"))
    with pytest.raises(google_oauth.GoogleOAuthError) as e:
        google_oauth.exchange_code("code")
    assert "userinfo" in str(e.value)
    assert "401" in str(e.value)


@pytest.mark.unit
def test_exchange_code_wraps_a_transport_failure(monkeypatch):
    def _boom(url, **kw):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(google_oauth.httpx, "post", _boom)
    with pytest.raises(google_oauth.GoogleOAuthError) as e:
        google_oauth.exchange_code("code")
    assert "google request failed" in str(e.value)
    assert isinstance(e.value.__cause__, httpx.HTTPError)


@pytest.mark.unit
def test_exchange_code_tolerates_a_profile_without_email_or_name(monkeypatch):
    monkeypatch.setattr(google_oauth.httpx, "post",
                        lambda url, **kw: _Resp(200, {"access_token": "at"}))
    monkeypatch.setattr(google_oauth.httpx, "get",
                        lambda url, **kw: _Resp(200, {"sub": "g-9"}))
    assert google_oauth.exchange_code("code") == {"sub": "g-9", "email": None, "name": None}


@pytest.mark.unit
def test_exchange_code_sends_the_access_token_as_a_bearer_header(monkeypatch):
    seen = {}
    monkeypatch.setattr(google_oauth.httpx, "post",
                        lambda url, **kw: _Resp(200, {"access_token": "at-42"}))

    def _get(url, **kw):
        seen.update(url=url, headers=kw.get("headers"))
        return _Resp(200, {"sub": "g-1", "email": "a@b.test", "name": "A"})

    monkeypatch.setattr(google_oauth.httpx, "get", _get)
    google_oauth.exchange_code("code")
    assert seen["url"] == google_oauth.USERINFO_URL
    assert seen["headers"]["Authorization"] == "Bearer at-42"


@pytest.mark.unit
@pytest.mark.xfail(reason="BUG: a 2xx token response missing 'access_token' raises a bare "
                          "KeyError instead of GoogleOAuthError, so main.google_callback's "
                          "`except GoogleOAuthError` misses it and the user gets a 500.")
def test_exchange_code_wraps_a_malformed_token_response(monkeypatch):
    monkeypatch.setattr(google_oauth.httpx, "post",
                        lambda url, **kw: _Resp(200, {"error": "unsupported"}))
    with pytest.raises(google_oauth.GoogleOAuthError):
        google_oauth.exchange_code("code")


# ==================================================== users_repo (DB-backed)

@requires_db
@pytest.mark.integration
def test_get_by_email_is_case_insensitive_and_username_lookup_is_not(monkeypatch):
    from api import users_repo
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    uname = _uname()
    email = f"{uname}@Example.Test"
    created = users_repo.create_user(username=uname, password_hash="x", email=email)

    assert users_repo.get_by_email(email.lower())["id"] == created["id"]
    assert users_repo.get_by_email(email.upper())["id"] == created["id"]
    assert users_repo.get_by_email(f"nobody-{uuid.uuid4().hex}@example.test") is None

    assert users_repo.get_by_username(uname)["id"] == created["id"]
    assert users_repo.get_by_username(uname.upper()) is None


@requires_db
@pytest.mark.integration
def test_get_by_username_or_email_falls_back_to_email():
    from api import users_repo
    uname = _uname()
    email = f"{uname}@example.test"
    created = users_repo.create_user(username=uname, password_hash="x", email=email)

    assert users_repo.get_by_username_or_email(uname)["id"] == created["id"]
    assert users_repo.get_by_username_or_email(email)["id"] == created["id"]
    assert users_repo.get_by_username_or_email("no-such-" + uuid.uuid4().hex) is None


@requires_db
@pytest.mark.integration
def test_update_password_rotates_the_hash_and_stamps_password_changed_at():
    from api import users_repo
    created = users_repo.create_user(
        username=_uname(), password_hash=security.hash_password("s3cret123"))
    assert created["password_changed_at"] is None

    users_repo.update_password(created["id"], security.hash_password("n3ws3cret"))

    after = users_repo.get_by_id(created["id"])
    assert after["password_changed_at"] is not None
    assert security.verify_password("n3ws3cret", after["password_hash"])
    assert not security.verify_password("s3cret123", after["password_hash"])


@requires_db
@pytest.mark.integration
def test_get_by_id_returns_none_for_an_unknown_uuid():
    from api import users_repo
    assert users_repo.get_by_id(str(uuid.uuid4())) is None
    assert users_repo.get_by_google_sub("no-such-sub-" + uuid.uuid4().hex) is None


# ============================================ password_reset_repo (DB-backed)

@requires_db
@pytest.mark.integration
def test_reset_token_is_opaque_and_only_its_hash_is_persisted(monkeypatch):
    import hashlib
    from sqlalchemy import text
    from api import password_reset_repo, users_repo
    from api.db import engine

    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "60")
    user = users_repo.create_user(username=_uname(), password_hash="x")
    raw = password_reset_repo.create_token(user["id"])

    assert len(raw) >= 32
    with engine.connect() as c:
        rows = c.execute(text("SELECT token_hash, used_at FROM password_reset_tokens "
                              "WHERE user_id = :u"), {"u": user["id"]}).all()
    assert len(rows) == 1
    assert rows[0][0] == hashlib.sha256(raw.encode()).hexdigest()
    assert rows[0][0] != raw, "the raw token must never be stored"
    assert rows[0][1] is None


@requires_db
@pytest.mark.integration
def test_reset_token_is_single_use(monkeypatch):
    from api import password_reset_repo, users_repo
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "60")
    user = users_repo.create_user(username=_uname(), password_hash="x")
    raw = password_reset_repo.create_token(user["id"])

    assert password_reset_repo.consume_token(raw) == user["id"]
    assert password_reset_repo.consume_token(raw) is None, "a burnt token must not work twice"
    assert password_reset_repo.consume_token(raw) is None


@requires_db
@pytest.mark.integration
def test_a_new_reset_request_invalidates_the_previous_link(monkeypatch):
    from api import password_reset_repo, users_repo
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "60")
    user = users_repo.create_user(username=_uname(), password_hash="x")

    first = password_reset_repo.create_token(user["id"])
    second = password_reset_repo.create_token(user["id"])

    assert first != second
    assert password_reset_repo.consume_token(first) is None, "superseded link must be dead"
    assert password_reset_repo.consume_token(second) == user["id"]


@requires_db
@pytest.mark.integration
def test_expired_reset_token_is_refused(monkeypatch):
    from api import password_reset_repo, users_repo
    user = users_repo.create_user(username=_uname(), password_hash="x")

    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "-5")   # already in the past
    stale = password_reset_repo.create_token(user["id"])
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "60")

    assert password_reset_repo.consume_token(stale) is None


@requires_db
@pytest.mark.integration
def test_unknown_empty_and_garbage_reset_tokens_are_refused():
    from api import password_reset_repo
    assert password_reset_repo.consume_token("") is None
    assert password_reset_repo.consume_token(None) is None
    assert password_reset_repo.consume_token("not-a-real-token") is None
    assert password_reset_repo.consume_token("../../etc/passwd") is None


@requires_db
@pytest.mark.integration
def test_one_users_token_cannot_be_burnt_by_creating_another_users_token(monkeypatch):
    from api import password_reset_repo, users_repo
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "60")
    a = users_repo.create_user(username=_uname(), password_hash="x")
    b = users_repo.create_user(username=_uname(), password_hash="x")

    token_a = password_reset_repo.create_token(a["id"])
    password_reset_repo.create_token(b["id"])          # must not touch a's row

    assert password_reset_repo.consume_token(token_a) == a["id"]


# ============================================ /api/v1/auth/* (DB-backed HTTP)

@requires_db
@pytest.mark.integration
def test_register_rejects_a_duplicate_username(monkeypatch):
    with _client(monkeypatch) as c:
        uname, _, _ = _register(c, email=f"{_uname()}@example.test")
        dup = c.post("/api/v1/auth/register",
                     json={"username": uname, "password": "different1"})
        assert dup.status_code == 409
        assert "taken" in dup.json()["detail"].lower()
        # The rejected attempt must not have overwritten the original password.
        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "s3cret123"}).status_code == 200
        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "different1"}).status_code == 401


@requires_db
@pytest.mark.integration
def test_login_failures_are_indistinguishable_and_never_leak_the_hash(monkeypatch):
    with _client(monkeypatch) as c:
        uname, _, _ = _register(c)

        wrong = c.post("/api/v1/auth/login", json={"username": uname, "password": "wrongpass1"})
        unknown = c.post("/api/v1/auth/login",
                         json={"username": "ghost-" + uuid.uuid4().hex, "password": "wrongpass1"})

        assert wrong.status_code == unknown.status_code == 401
        # Same body for "bad password" and "no such user": no account enumeration.
        assert wrong.json() == unknown.json()
        assert "hash" not in wrong.text.lower()
        assert "$2b$" not in wrong.text


@requires_db
@pytest.mark.integration
def test_register_accepts_a_password_of_exactly_72_bytes(monkeypatch):
    """The cap must refuse 73 bytes without also refusing 72."""
    with _client(monkeypatch) as c:
        uname = _uname()
        # 36 two-byte characters == 72 bytes == the bcrypt limit exactly.
        pw = "é" * 36
        assert c.post("/api/v1/auth/register",
                      json={"username": uname, "password": pw}).status_code == 201
        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": pw}).status_code == 200


@requires_db
@pytest.mark.integration
def test_a_long_password_at_login_is_a_401_never_a_422_or_a_500(monkeypatch):
    """Login must NOT grow a length cap: it would lock out legacy accounts.

    An over-long password at the login boundary is simply a failed credential
    (401), not a validation error and never a 500 out of bcrypt.
    """
    from api import main
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    with TestClient(main.app, raise_server_exceptions=False) as c:
        uname, _, _ = _register(c)
        r = c.post("/api/v1/auth/login", json={"username": uname, "password": "z" * 400})
        assert r.status_code == 401, f"got {r.status_code}: {r.text}"


@requires_db
@pytest.mark.integration
def test_login_still_works_for_an_account_whose_hash_predates_the_byte_cap(monkeypatch):
    """A pre-existing over-long password must keep working after this change."""
    import bcrypt
    from api import users_repo
    with _client(monkeypatch) as c:
        uname = _uname()
        _register(c, username=uname)
        # Simulate the old silently-truncating bcrypt: hash only the first 72 bytes.
        legacy = bcrypt.hashpw(("L0ng-" + "q" * 300).encode()[:72], bcrypt.gensalt()).decode()
        users_repo.update_password(users_repo.get_by_username(uname)["id"], legacy)

        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "L0ng-" + "q" * 300}).status_code == 200


@requires_db
@pytest.mark.integration
def test_login_accepts_email_case_insensitively_and_trims_whitespace(monkeypatch):
    with _client(monkeypatch) as c:
        uname = _uname()
        email = f"{uname}@Example.Test"
        _register(c, username=uname, email=email)

        assert c.post("/api/v1/auth/login",
                      json={"username": email.upper(), "password": "s3cret123"}).status_code == 200
        assert c.post("/api/v1/auth/login",
                      json={"username": f"  {uname}  ", "password": "s3cret123"}).status_code == 200


@requires_db
@pytest.mark.integration
def test_login_is_refused_for_a_google_only_account(monkeypatch):
    from api import users_repo
    with _client(monkeypatch) as c:
        uname = _uname()
        users_repo.create_user(username=uname, google_sub="g-" + uuid.uuid4().hex,
                               email=f"{uname}@example.test")
        # No password_hash: any password must fail rather than crash bcrypt.
        r = c.post("/api/v1/auth/login", json={"username": uname, "password": "anything1"})
        assert r.status_code == 401


@requires_db
@pytest.mark.integration
def test_users_me_rejects_bad_tokens_over_http(monkeypatch):
    with _client(monkeypatch) as c:
        _, _, body = _register(c)
        good = body["access_token"]
        assert c.get("/api/v1/users/me",
                     headers={"Authorization": f"Bearer {good}"}).status_code == 200

        forged = pyjwt.encode({"sub": body["user"]["id"], "iat": int(time.time()),
                               "exp": int(time.time()) + 3600},
                              OTHER_SECRET, algorithm="HS256")
        cases = {
            "no header": {},
            "no scheme": {"Authorization": good},
            "wrong scheme": {"Authorization": f"Basic {good}"},
            "garbage token": {"Authorization": "Bearer not.a.jwt"},
            "wrong secret": {"Authorization": f"Bearer {forged}"},
            "unknown user": {"Authorization": "Bearer " + pyjwt.encode(
                {"sub": str(uuid.uuid4()), "iat": int(time.time()),
                 "exp": int(time.time()) + 3600}, TEST_SECRET, algorithm="HS256")},
        }
        for label, headers in cases.items():
            r = c.get("/api/v1/users/me", headers=headers)
            assert r.status_code == 401, f"{label} should be rejected, got {r.status_code}"


@requires_db
@pytest.mark.integration
def test_expired_token_is_rejected_over_http(monkeypatch):
    with _client(monkeypatch) as c:
        _, _, body = _register(c)
        expired = pyjwt.encode({"sub": body["user"]["id"], "iat": int(time.time()) - 7200,
                                "exp": int(time.time()) - 60},
                               TEST_SECRET, algorithm="HS256")
        r = c.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401


@requires_db
@pytest.mark.integration
def test_patch_me_completes_the_profile_and_refuses_a_taken_username(monkeypatch):
    with _client(monkeypatch) as c:
        _, _, victim = _register(c)
        uname, _, body = _register(c)
        auth = {"Authorization": f"Bearer {body['access_token']}"}

        conflict = c.patch("/api/v1/users/me", headers=auth,
                           json={"username": victim["user"]["username"]})
        assert conflict.status_code == 409
        assert c.get("/api/v1/users/me", headers=auth).json()["username"] == uname

        # Renaming to the caller's own current username is a no-op, not a 409.
        assert c.patch("/api/v1/users/me", headers=auth,
                       json={"username": uname}).status_code == 200

        # A rename to a free username goes through and the old one is released.
        renamed = _uname()
        assert c.patch("/api/v1/users/me", headers=auth,
                       json={"username": renamed}).json()["username"] == renamed
        assert c.post("/api/v1/auth/login",
                      json={"username": renamed, "password": "s3cret123"}).status_code == 200
        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "s3cret123"}).status_code == 401

        done = c.patch("/api/v1/users/me", headers=auth, json={
            "ev_model_id": "hyundai-ioniq-5", "main_connector_type": "CCS2",
            "location_consent": True})
        assert done.status_code == 200
        assert done.json()["profile_completed"] is True


# ================================== forgot / reset password end-to-end (DB)

@pytest.fixture
def captured_mail(monkeypatch):
    """Replace mailer.send_email in main's namespace and record what was sent."""
    from api import main
    sent: list = []
    monkeypatch.setattr(main.mailer, "send_email",
                        lambda **kw: sent.append(kw))
    return sent


def _token_from_link(sent: list) -> str:
    assert len(sent) == 1, f"expected exactly one email, got {len(sent)}"
    body = sent[0]["text_body"]
    assert "https://frontend.test/reset-password?token=" in body
    return body.split("?token=", 1)[1].split()[0]


@requires_db
@pytest.mark.integration
def test_full_reset_flow_emails_a_working_single_use_link(monkeypatch, captured_mail):
    with _client(monkeypatch) as c:
        uname = _uname()
        email = f"{uname}@example.test"
        _register(c, username=uname, email=email)

        r = c.post("/api/v1/auth/forgot-password", json={"email": email.upper()})
        assert r.status_code == 200
        assert "sent" in r.json()["message"].lower()

        assert captured_mail[0]["to"] == email.lower()
        assert "<a href=" in captured_mail[0]["html_body"]
        token = _token_from_link(captured_mail)
        assert "s3cret123" not in captured_mail[0]["text_body"], "never mail a password"

        ok = c.post("/api/v1/auth/reset-password",
                    json={"token": token, "new_password": "n3wp4ssword"})
        assert ok.status_code == 200

        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "n3wp4ssword"}).status_code == 200
        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "s3cret123"}).status_code == 401

        replay = c.post("/api/v1/auth/reset-password",
                        json={"token": token, "new_password": "third-p4ssword"})
        assert replay.status_code == 400, "the reset link must be single-use"
        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "third-p4ssword"}).status_code == 401


@requires_db
@pytest.mark.integration
def test_password_reset_logs_out_every_previously_issued_token(monkeypatch, captured_mail):
    with _client(monkeypatch) as c:
        uname = _uname()
        email = f"{uname}@example.test"
        _, _, body = _register(c, username=uname, email=email)
        old_auth = {"Authorization": f"Bearer {body['access_token']}"}
        assert c.get("/api/v1/users/me", headers=old_auth).status_code == 200

        c.post("/api/v1/auth/forgot-password", json={"email": email})
        token = _token_from_link(captured_mail)
        assert c.post("/api/v1/auth/reset-password",
                      json={"token": token, "new_password": "n3wp4ssword"}).status_code == 200

        stale = c.get("/api/v1/users/me", headers=old_auth)
        assert stale.status_code == 401, "a stolen pre-reset token must stop working"
        assert stale.json()["detail"] == "session expired, please log in again"

        # ...and the new credentials mint a token that ACTUALLY WORKS, in the
        # same wall-clock second as the reset. This used to be unassertable (the
        # brand-new token was rejected too, for the rest of that second, by the
        # iat-truncation defect); it is now deterministic, so the full
        # reset -> log in -> use the app flow is pinned end to end here.
        relogin = c.post("/api/v1/auth/login",
                         json={"username": uname, "password": "n3wp4ssword"})
        assert relogin.status_code == 200
        assert security.decode_access_token(relogin.json()["access_token"]) == body["user"]["id"]

        fresh_auth = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
        me = c.get("/api/v1/users/me", headers=fresh_auth)
        assert me.status_code == 200, f"the session the reset just handed out was refused: {me.text}"
        assert me.json()["id"] == body["user"]["id"]


@requires_db
@pytest.mark.integration
def test_reset_password_refuses_garbage_expired_and_empty_tokens(monkeypatch, captured_mail):
    with _client(monkeypatch) as c:
        uname = _uname()
        email = f"{uname}@example.test"
        _register(c, username=uname, email=email)

        for bad in ["", "not-a-real-token", "a" * 200, "'; DROP TABLE users; --"]:
            r = c.post("/api/v1/auth/reset-password",
                       json={"token": bad, "new_password": "n3wp4ssword"})
            assert r.status_code == 400, f"token {bad!r} should be refused"

        # An expired link is refused too, and the old password keeps working.
        monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "-5")
        c.post("/api/v1/auth/forgot-password", json={"email": email})
        expired = _token_from_link(captured_mail)
        monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "60")

        r = c.post("/api/v1/auth/reset-password",
                   json={"token": expired, "new_password": "n3wp4ssword"})
        assert r.status_code == 400
        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "s3cret123"}).status_code == 200


@requires_db
@pytest.mark.integration
def test_reset_password_enforces_the_minimum_length(monkeypatch, captured_mail):
    with _client(monkeypatch) as c:
        uname = _uname()
        email = f"{uname}@example.test"
        _register(c, username=uname, email=email)
        c.post("/api/v1/auth/forgot-password", json={"email": email})
        token = _token_from_link(captured_mail)

        assert c.post("/api/v1/auth/reset-password",
                      json={"token": token, "new_password": "short"}).status_code == 422
        # The rejected attempt must not have consumed the token.
        assert c.post("/api/v1/auth/reset-password",
                      json={"token": token, "new_password": "n3wp4ssword"}).status_code == 200


@requires_db
@pytest.mark.integration
def test_forgot_password_rejects_a_value_that_is_not_an_email(monkeypatch, captured_mail):
    with _client(monkeypatch) as c:
        r = c.post("/api/v1/auth/forgot-password", json={"email": "not-an-email"})
        assert r.status_code == 422
        assert captured_mail == []


@requires_db
@pytest.mark.integration
def test_forgot_password_still_succeeds_when_smtp_is_not_configured(monkeypatch):
    """SMTP_HOST unset: no mail leaves the box, but the request must not fail."""
    from api import password_reset_repo
    for name in SMTP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    plain = type("_FakeSMTP", (_FakeSMTPBase,), {"kind": "plain", "log": []})
    monkeypatch.setattr(mailer.smtplib, "SMTP", plain)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", plain)

    with _client(monkeypatch) as c:
        uname = _uname()
        email = f"{uname}@example.test"
        _register(c, username=uname, email=email)

        r = c.post("/api/v1/auth/forgot-password", json={"email": email})
        assert r.status_code == 200
        assert plain.log == [], "MailerNotConfigured must be swallowed, not dialled out"

    # The token was still minted, so the failure mode is "no email", not "no token".
    from api import users_repo
    user = users_repo.get_by_email(email)
    from sqlalchemy import text
    from api.db import engine
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM password_reset_tokens WHERE user_id = :u"),
                         {"u": user["id"]}).scalar()
    assert n == 1


@requires_db
@pytest.mark.integration
def test_forgot_password_still_succeeds_when_the_smtp_server_errors(monkeypatch):
    import smtplib as real_smtplib
    from api import main

    def _boom(**kw):
        raise real_smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(main.mailer, "send_email", _boom)
    with _client(monkeypatch) as c:
        uname = _uname()
        email = f"{uname}@example.test"
        _register(c, username=uname, email=email)
        r = c.post("/api/v1/auth/forgot-password", json={"email": email})
        assert r.status_code == 200
        assert "sent" in r.json()["message"].lower()


# ================================================== Google callback (DB HTTP)

@requires_db
@pytest.mark.integration
def test_google_callback_rejects_a_tampered_or_expired_state(monkeypatch):
    from api import google_oauth as go
    monkeypatch.setattr(go, "exchange_code",
                        lambda code: pytest.fail("must not exchange on a bad state"))
    with _client(monkeypatch) as c:
        good = security.sign_state()
        nonce, ts, sig = good.split(".")
        bad_states = [
            "garbage",
            good + "x",                                   # signature tampered
            f"{nonce}.{int(ts) + 600}.{sig}",             # timestamp tampered
            f"{nonce}.{int(ts) - 100000}.{sig}",          # stale
        ]
        for st in bad_states:
            r = c.get(f"/api/v1/auth/google/callback?code=abc&state={st}",
                      follow_redirects=False)
            assert r.status_code == 400, f"state {st!r} should be refused"


@requires_db
@pytest.mark.integration
def test_google_callback_returns_502_when_google_fails(monkeypatch):
    from api import google_oauth as go

    def _boom(code):
        raise go.GoogleOAuthError("token 400: invalid_grant")

    monkeypatch.setattr(go, "exchange_code", _boom)
    with _client(monkeypatch) as c:
        r = c.get(f"/api/v1/auth/google/callback?code=abc&state={security.sign_state()}",
                  follow_redirects=False)
        assert r.status_code == 502


@requires_db
@pytest.mark.integration
def test_google_login_redirects_with_a_verifiable_state(monkeypatch):
    from urllib.parse import parse_qs, urlparse
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://api.test/cb")
    with _client(monkeypatch) as c:
        r = c.get("/api/v1/auth/google/login", follow_redirects=False)
        assert r.status_code in (302, 307)
        q = parse_qs(urlparse(r.headers["location"]).query)
        assert security.verify_state(q["state"][0]) is True


@requires_db
@pytest.mark.integration
def test_google_callback_is_idempotent_for_a_returning_user(monkeypatch):
    from api import google_oauth as go, users_repo
    sub = "g-" + uuid.uuid4().hex
    monkeypatch.setattr(go, "exchange_code",
                        lambda code: {"sub": sub, "email": f"{sub}@example.test", "name": "G"})
    with _client(monkeypatch) as c:
        first = c.get(f"/api/v1/auth/google/callback?code=a&state={security.sign_state()}",
                      follow_redirects=False)
        second = c.get(f"/api/v1/auth/google/callback?code=b&state={security.sign_state()}",
                       follow_redirects=False)
    assert first.status_code in (302, 307) and second.status_code in (302, 307)
    user = users_repo.get_by_google_sub(sub)
    assert user is not None
    # Second sign-in must reuse the account, and the fragment token must authenticate it.
    token = second.headers["location"].split("#token=", 1)[1]
    assert security.decode_access_token(token) == user["id"]


# =========================================================== documented BUGS
# The tests below assert what the system SHOULD do. They are xfail, not
# assertions of current behaviour, so the defects are recorded without the
# suite locking them in.

@requires_db
@pytest.mark.integration
def test_register_with_a_very_long_password_is_a_clean_422_not_a_500(monkeypatch):
    """FIXED: the byte cap is enforced at the boundary, so bcrypt never sees it."""
    from api import main
    with TestClient(main.app, raise_server_exceptions=False) as c:
        monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
        r = c.post("/api/v1/auth/register",
                   json={"username": _uname(), "password": "a" * 100})
        assert r.status_code == 422, f"got {r.status_code}"
        assert ["body", "password"] in [d["loc"] for d in r.json()["detail"]]


@requires_db
@pytest.mark.integration
def test_reset_password_with_a_multibyte_password_is_not_a_500(monkeypatch, captured_mail):
    """FIXED: the cap counts UTF-8 BYTES, so 60 accented characters are refused."""
    from api import main
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("FRONTEND_URL", "https://frontend.test")
    monkeypatch.setenv("PASSWORD_RESET_TTL_MINUTES", "60")
    with TestClient(main.app, raise_server_exceptions=False) as c:
        uname = _uname()
        email = f"{uname}@example.test"
        _register(c, username=uname, email=email)
        c.post("/api/v1/auth/forgot-password", json={"email": email})
        token = _token_from_link(captured_mail)

        r = c.post("/api/v1/auth/reset-password",
                   json={"token": token, "new_password": "pässwörd-ñ" * 6})  # 60 chars, >72 bytes
        assert r.status_code == 422, f"got {r.status_code}"
        assert ["body", "new_password"] in [d["loc"] for d in r.json()["detail"]]
        # The old password must still work: a refused reset changes nothing.
        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "s3cret123"}).status_code == 200


@requires_db
@pytest.mark.integration
@pytest.mark.xfail(reason="BUG (accepted tradeoff in code, still an OWASP finding): "
                          "/auth/forgot-password answers 404 for an unregistered address, "
                          "turning it into a free account-enumeration oracle.")
def test_forgot_password_does_not_disclose_whether_an_email_is_registered(
        monkeypatch, captured_mail):
    with _client(monkeypatch) as c:
        uname = _uname()
        known = f"{uname}@example.test"
        _register(c, username=uname, email=known)

        hit = c.post("/api/v1/auth/forgot-password", json={"email": known})
        miss = c.post("/api/v1/auth/forgot-password",
                      json={"email": f"nobody-{uuid.uuid4().hex}@example.test"})

        assert (hit.status_code, hit.json()) == (miss.status_code, miss.json())
        assert len(captured_mail) == 1, "only the registered address may receive mail"


@requires_db
@pytest.mark.integration
@pytest.mark.xfail(reason="BUG: /auth/forgot-password answers 400 'This account uses Google "
                          "sign-in' for a Google-only account, disclosing both that the "
                          "address is registered and which identity provider it uses.")
def test_forgot_password_does_not_disclose_the_identity_provider(monkeypatch, captured_mail):
    from api import users_repo
    with _client(monkeypatch) as c:
        uname = _uname()
        google_email = f"{uname}@example.test"
        users_repo.create_user(username=uname, google_sub="g-" + uuid.uuid4().hex,
                               email=google_email)
        other = _uname()
        _register(c, username=other, email=f"{other}@example.test")

        google_resp = c.post("/api/v1/auth/forgot-password", json={"email": google_email})
        normal_resp = c.post("/api/v1/auth/forgot-password",
                             json={"email": f"{other}@example.test"})
        assert google_resp.status_code == normal_resp.status_code


@requires_db
@pytest.mark.integration
@pytest.mark.xfail(reason="BUG: users.email has no UNIQUE constraint and /auth/register does "
                          "not check it, so two accounts can share an address. "
                          "get_by_email then resolves the reset to an arbitrary one of them.")
def test_two_accounts_cannot_share_an_email_address(monkeypatch):
    with _client(monkeypatch) as c:
        email = f"shared-{uuid.uuid4().hex}@example.test"
        first = c.post("/api/v1/auth/register",
                       json={"username": _uname(), "password": "s3cret123", "email": email})
        assert first.status_code == 201
        second = c.post("/api/v1/auth/register",
                        json={"username": _uname(), "password": "s3cret123", "email": email})
        assert second.status_code == 409, f"duplicate email should be refused, got {second.status_code}"


@requires_db
@pytest.mark.integration
@pytest.mark.xfail(reason="BUG: register's duplicate-username check is a read-then-write race. "
                          "When the row appears between the SELECT and the INSERT the unique "
                          "violation escapes as an unhandled 500 instead of a 409.")
def test_register_returns_409_when_the_username_race_is_lost(monkeypatch):
    from api import main, users_repo
    with TestClient(main.app, raise_server_exceptions=False) as c:
        monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
        uname, _, _ = _register(c)
        # Simulate the window: the pre-check sees nothing, the INSERT hits the constraint.
        monkeypatch.setattr(users_repo, "get_by_username", lambda u: None)
        r = c.post("/api/v1/auth/register", json={"username": uname, "password": "s3cret123"})
        assert r.status_code == 409, f"expected 409, got {r.status_code}"


@requires_db
@pytest.mark.integration
def test_repeated_failed_logins_are_eventually_throttled(monkeypatch):
    """The shipped budget is 60 failures per 5 minutes, per caller and overall.

    The number is patched down rather than sent in full because every failed
    login against an existing account costs a real bcrypt(cost 12) verify here --
    60 of them is ~20 seconds of test time to prove something the budget-shaped
    tests in tests/test_rate_limits_auth.py already prove at the constant's real
    value. What this test adds is that it holds end to end, against the database.
    """
    from api import rate_limit
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 5)
    with _client(monkeypatch) as c:
        uname, _, _ = _register(c)
        codes = [c.post("/api/v1/auth/login",
                        json={"username": uname, "password": f"wrong{i:04d}"}).status_code
                 for i in range(8)]
        assert codes[:5] == [401] * 5, "the budget must be spendable before it bites"
        assert codes[5:] == [429] * 3
        # A correct password is charged nothing, so the account is not locked out
        # by its owner's own successful sign-ins -- but it IS shed while the
        # failure budget is spent, which is the deliberate trade.
        assert c.post("/api/v1/auth/login",
                      json={"username": uname, "password": "s3cret123"}).status_code == 429


@requires_db
@pytest.mark.integration
def test_repeated_forgot_password_requests_are_eventually_throttled(monkeypatch, captured_mail):
    """Three reset mails per hour per address; the rest are shed."""
    with _client(monkeypatch) as c:
        uname = _uname()
        email = f"{uname}@example.test"
        _register(c, username=uname, email=email)
        codes = [c.post("/api/v1/auth/forgot-password", json={"email": email}).status_code
                 for _ in range(30)]
        assert 429 in codes, "30 reset mails to one address should trip a limiter"
