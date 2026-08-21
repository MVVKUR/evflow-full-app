"""Tests for the browser-origin policy: the CORS allow-list and the write guard.

The two are separate controls and are tested separately. CORS decides whether a
browser may READ a response; the guard decides whether we run the handler at all
for a state-changing request. Only the second is a security control worth the
name -- see api/cors_policy.py for why -- so most of what follows exercises it.

None of this is CSRF protection: auth is a Bearer token in a header and there are
no auth cookies anywhere, so a cross-site request never carried credentials in
the first place. It is defence in depth against a token stolen by XSS being
replayed from the page that stole it.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient   # noqa: E402

from api import cors_policy                 # noqa: E402
from api.main import app                    # noqa: E402

client = TestClient(app)

# Reachable without a database and without SMTP: an empty body fails Pydantic
# validation, which happens AFTER the guard and BEFORE anything else. So a 422
# proves the request got past the guard, and no side effect is possible either way.
GUARDED_ENDPOINT = "/api/v1/support/tickets"

HOSTILE_ORIGIN = "https://evil.example"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test states its own CORS env; none inherits the developer's shell."""
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOW_CREDENTIALS", raising=False)
    yield


# ============================================================ the allow-list

@pytest.mark.unit
def test_default_allow_list_is_not_a_wildcard():
    """The whole point of the change: no deployment defaults to open."""
    origins = cors_policy.allowed_origins()
    assert cors_policy.WILDCARD not in origins
    assert origins, "an empty default would lock every browser out"


@pytest.mark.unit
def test_default_allow_list_covers_production_and_local_development():
    origins = cors_policy.allowed_origins()
    assert "https://ev-flow.opensoft.id" in origins       # production tunnel hostname
    assert "http://localhost:5173" in origins             # vite dev server
    assert "http://127.0.0.1:5173" in origins
    assert "http://localhost:8080" in origins             # containerised web on loopback
    assert "http://127.0.0.1:8080" in origins


@pytest.mark.unit
def test_the_documentation_host_can_still_issue_writes():
    """Swagger's "Try it out" is a browser, and a same-origin POST sends an Origin.

    Leaving the docs hostname off the list would 403 every write attempted from
    the API documentation, which reads as a broken API rather than a policy.
    """
    origins = cors_policy.allowed_origins()
    assert "https://evflow-api-doc.opensoft.id" in origins
    assert "http://localhost:8000" in origins             # uvicorn serving its own /docs
    assert cors_policy.rejection_reason(
        "POST", "/api/v1/support/tickets",
        "https://evflow-api-doc.opensoft.id", origins) is None


@pytest.mark.unit
def test_env_replaces_the_default_entirely(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://staging.example, https://other.example")
    assert cors_policy.allowed_origins() == ["https://staging.example", "https://other.example"]


@pytest.mark.unit
def test_env_entries_are_normalised_to_what_a_browser_actually_sends(monkeypatch):
    """A trailing slash in an env file must not silently match nothing."""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", " https://staging.example/ ")
    assert cors_policy.allowed_origins() == ["https://staging.example"]


@pytest.mark.unit
@pytest.mark.parametrize("value", ["", "   ", ",", " , , "])
def test_blank_or_separator_only_env_falls_back_to_the_default(monkeypatch, value):
    """A typo'd env var is not a request to allow nothing."""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", value)
    assert cors_policy.allowed_origins() == list(cors_policy.DEFAULT_ALLOWED_ORIGINS)


@pytest.mark.unit
def test_wildcard_is_still_reachable_as_an_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    assert cors_policy.allowed_origins() == ["*"]


# ============================================ credentials + wildcard is refused

@pytest.mark.unit
def test_credentials_are_off_by_default():
    """Nothing in this system needs them: Bearer header, never a cookie."""
    assert cors_policy.allow_credentials(cors_policy.allowed_origins()) is False


@pytest.mark.unit
def test_credentials_with_a_wildcard_fails_loudly(monkeypatch):
    """The combination browsers reject must not boot, let alone deploy."""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    with pytest.raises(cors_policy.CorsMisconfigured) as exc:
        cors_policy.allow_credentials(cors_policy.allowed_origins())
    # The message must name both settings, since either one is the fix.
    assert "CORS_ALLOW_CREDENTIALS" in str(exc.value)
    assert "CORS_ALLOW_ORIGINS" in str(exc.value)


@pytest.mark.unit
def test_credentials_with_an_explicit_list_are_allowed(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://ev-flow.opensoft.id")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "1")
    assert cors_policy.allow_credentials(cors_policy.allowed_origins()) is True


@pytest.mark.unit
def test_wildcard_without_credentials_is_not_an_error(monkeypatch):
    """An operator may still open reads deliberately; only the pair is impossible."""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    assert cors_policy.allow_credentials(cors_policy.allowed_origins()) is False


@pytest.mark.unit
def test_the_running_app_never_pairs_credentials_with_a_wildcard():
    """Belt on the wiring itself, not just the helper."""
    cors = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert len(cors) == 1
    options = cors[0].kwargs
    if options.get("allow_credentials"):
        assert cors_policy.WILDCARD not in options["allow_origins"]


@pytest.mark.unit
def test_cors_preflight_allows_every_state_changing_route_verb():
    assert set(cors_policy.STATE_CHANGING_METHODS) <= set(cors_policy.ALLOWED_METHODS)


# ================================================= the guard, as a pure function

ALLOWED = ["https://ev-flow.opensoft.id", "http://localhost:5173"]


@pytest.mark.unit
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_state_changing_verb_is_guarded(method):
    assert cors_policy.rejection_reason(method, "/api/v1/anything", HOSTILE_ORIGIN, ALLOWED)


@pytest.mark.unit
@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_reads_and_preflight_are_not_guarded(method):
    """OPTIONS especially: 403ing preflight would break the handshake itself."""
    assert cors_policy.rejection_reason(method, "/api/v1/anything", HOSTILE_ORIGIN, ALLOWED) is None


@pytest.mark.unit
@pytest.mark.parametrize("origin", [None, "", "   "])
def test_a_missing_origin_is_allowed_through(origin):
    """Mobile apps, curl and server-to-server callers send no Origin at all.

    Breaking them would cost more than the hole it closes, and a browser always
    sends one on a cross-origin write, so the guarded case is unaffected.
    """
    assert cors_policy.rejection_reason("POST", "/api/v1/anything", origin, ALLOWED) is None


@pytest.mark.unit
def test_an_allowed_origin_passes():
    assert cors_policy.rejection_reason("POST", "/api/v1/anything",
                                        "https://ev-flow.opensoft.id", ALLOWED) is None


@pytest.mark.unit
def test_an_allowed_origin_passes_with_a_trailing_slash_in_the_config():
    assert cors_policy.rejection_reason("POST", "/api/v1/anything",
                                        "https://ev-flow.opensoft.id",
                                        ["https://ev-flow.opensoft.id/"]) is None


@pytest.mark.unit
@pytest.mark.parametrize("origin", [
    HOSTILE_ORIGIN,
    "null",                                     # sandboxed iframe / file:// page
    "http://ev-flow.opensoft.id",               # scheme must match
    "https://ev-flow.opensoft.id.evil.example",  # suffix, not the same origin
    "https://ev-flow.opensoft.id:8443",         # port is part of the origin
])
def test_an_unvetted_origin_is_rejected(origin):
    assert cors_policy.rejection_reason("POST", "/api/v1/anything", origin, ALLOWED) is not None


@pytest.mark.unit
def test_a_configured_wildcard_disables_the_guard():
    assert cors_policy.rejection_reason("POST", "/api/v1/anything", HOSTILE_ORIGIN, ["*"]) is None


@pytest.mark.unit
def test_the_xendit_webhook_is_exempt():
    """Xendit posts from its own infrastructure and signs with a callback token.

    It will never be on any origin allow-list, and the token comparison in the
    handler is the control that protects this path.
    """
    assert cors_policy.rejection_reason(
        "POST", "/api/v1/webhooks/xendit", HOSTILE_ORIGIN, ALLOWED) is None
    assert cors_policy.rejection_reason(
        "POST", "/api/v1/webhooks/xendit/", HOSTILE_ORIGIN, ALLOWED) is None


@pytest.mark.unit
def test_the_exemption_does_not_leak_to_neighbouring_paths():
    assert cors_policy.rejection_reason(
        "POST", "/api/v1/webhooks/xendit/other", HOSTILE_ORIGIN, ALLOWED) is not None
    assert cors_policy.rejection_reason(
        "POST", "/api/v1/webhooks", HOSTILE_ORIGIN, ALLOWED) is not None


@pytest.mark.unit
def test_the_rejection_message_names_no_origin():
    """A 403 that echoes the origin, or lists the allowed ones, is a probe."""
    reason = cors_policy.rejection_reason("POST", "/api/v1/anything", HOSTILE_ORIGIN, ALLOWED)
    assert HOSTILE_ORIGIN not in reason
    assert "ev-flow.opensoft.id" not in reason


# ================================================= the guard, through the app

@pytest.mark.integration
def test_a_write_from_an_unvetted_origin_is_refused_before_the_handler(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://ev-flow.opensoft.id")
    r = client.post(GUARDED_ENDPOINT, json={}, headers={"Origin": HOSTILE_ORIGIN})
    assert r.status_code == 403, r.text
    # 403, not the 422 the empty body would have produced: the request never
    # reached validation, let alone the handler.
    assert r.json()["detail"] == cors_policy.ORIGIN_REJECTED_DETAIL
    assert HOSTILE_ORIGIN not in r.text


@pytest.mark.integration
def test_a_write_from_an_allowed_origin_reaches_the_handler(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://ev-flow.opensoft.id")
    r = client.post(GUARDED_ENDPOINT, json={},
                    headers={"Origin": "https://ev-flow.opensoft.id"})
    assert r.status_code == 422, r.text


@pytest.mark.integration
def test_a_write_with_no_origin_header_reaches_the_handler(monkeypatch):
    """The mobile-client case. TestClient sends no Origin, same as a native app."""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://ev-flow.opensoft.id")
    r = client.post(GUARDED_ENDPOINT, json={})
    assert r.status_code == 422, r.text


@pytest.mark.integration
def test_a_read_from_an_unvetted_origin_still_works(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://ev-flow.opensoft.id")
    r = client.get("/health", headers={"Origin": HOSTILE_ORIGIN})
    assert r.status_code == 200, r.text


@pytest.mark.integration
def test_the_xendit_webhook_answers_a_third_party_with_no_allowed_origin(monkeypatch):
    """Not 403. The callback token check is what decides this request."""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://ev-flow.opensoft.id")
    monkeypatch.delenv("XENDIT_CALLBACK_TOKEN", raising=False)
    r = client.post("/api/v1/webhooks/xendit", json={"id": "inv-1", "status": "PAID"},
                    headers={"Origin": "https://xendit.example"})
    assert r.status_code != 403
    assert r.status_code == 503, r.text          # "webhook not configured", the handler's answer


@pytest.mark.integration
def test_the_guard_reads_its_allow_list_per_request(monkeypatch):
    """Config is read at call time, the pattern the rest of the codebase uses."""
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", HOSTILE_ORIGIN)
    r = client.post(GUARDED_ENDPOINT, json={}, headers={"Origin": HOSTILE_ORIGIN})
    assert r.status_code == 422, r.text          # now on the list, so it gets through


# ============================================= the misconfiguration cannot boot

@pytest.mark.integration
def test_importing_the_app_with_credentials_and_a_wildcard_fails_at_startup():
    """"Fail loudly at startup" means the container does not come up.

    Checked in a fresh interpreter because api.main evaluates the policy at
    import, which has already happened in this process.
    """
    import subprocess
    import sys

    env_setup = (
        "import os;"
        "os.environ['CORS_ALLOW_ORIGINS']='*';"
        "os.environ['CORS_ALLOW_CREDENTIALS']='true';"
        "import api.main"
    )
    proc = subprocess.run([sys.executable, "-c", env_setup],
                          capture_output=True, text=True)

    assert proc.returncode != 0, "a wildcard + credentials deployment must not start"
    assert "CorsMisconfigured" in proc.stderr
    assert "CORS_ALLOW_CREDENTIALS" in proc.stderr


@pytest.mark.integration
def test_importing_the_app_with_a_wildcard_alone_still_starts():
    """The wildcard is a bad default, not a forbidden explicit choice."""
    import subprocess
    import sys

    env_setup = (
        "import os;"
        "os.environ['CORS_ALLOW_ORIGINS']='*';"
        "import api.main;"
        "print('started')"
    )
    proc = subprocess.run([sys.executable, "-c", env_setup],
                          capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr
    assert "started" in proc.stdout
