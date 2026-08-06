"""Which browser origins this API answers, and the guard on state-changing calls.

Two separate mechanisms live here, and they buy different things:

* the allow-list handed to Starlette's ``CORSMiddleware``, which decides whether a
  browser is permitted to READ our response; and
* :class:`WriteOriginGuard`, which runs before the route handler on
  POST/PUT/PATCH/DELETE and decides whether we EXECUTE the write at all.

CORS alone only ever does the first. The browser sends the request, we run the
handler, the database changes, and only then does the browser refuse to hand the
response body to the calling script. For a "simple" request whose response the
attacker never wanted to read, that is no protection whatsoever. The guard closes
that gap by refusing before the handler runs.

WHAT THIS DOES NOT BUY. Not protection from classic CSRF. Authentication here is
a Bearer token in the ``Authorization`` header and there are no auth cookies
anywhere in this system, so a cross-site request carries no ambient credentials
and never could act as the user. What it does buy is defence in depth: a token
lifted out of ``localStorage`` by an XSS on some other page cannot be replayed
against our writes from that page's origin, and an origin nobody vetted cannot
drive writes at all. It is a cheap second lock, not the first one.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable, Optional, Sequence

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# The real origins this deployment serves. In production nginx serves the web app
# and proxies /api/ to this API, so the browser calls us SAME-ORIGIN and CORS is
# not involved at all -- the entry below matters only for the tunnel hostname
# being used directly. Cross-origin genuinely happens in local development, where
# the vite dev server (5173) and the containerised web (8080, see
# podman-compose.yml) call a separately-bound API.
#
# NOT "*": a wildcard hands every page on the internet a read channel to this API
# and, before the guard below existed, a write channel too. New hostnames (a
# staging tunnel, say) belong in CORS_ALLOW_ORIGINS on that deployment, not here.
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "https://ev-flow.opensoft.id",          # production web + /api (same-origin behind nginx)
    "https://evflow-api-doc.opensoft.id",   # Swagger/ReDoc host -- see note below
    "https://ev-flow-staging.opensoft.id",  # staging web + /api, same tunnel
    "http://localhost:5173",                # vite dev server
    "http://127.0.0.1:5173",
    "http://localhost:8080",                # containerised web (nginx), podman-compose.yml
    "http://127.0.0.1:8080",
    "http://localhost:8081",                # containerised STAGING web on the VPS
    "http://127.0.0.1:8081",
    "http://localhost:8000",                # uvicorn direct, incl. its own /docs
    "http://127.0.0.1:8000",
)

# WHY THE DOCS HOST IS ON THE LIST. Swagger UI's "Try it out" is a browser, and it
# issues the real POST. A same-origin write still carries an Origin header (the
# Fetch spec sets it for every method except GET and HEAD), so leaving the docs
# hostname off would 403 every write attempted from the documentation -- which
# reads as "the API is broken", not "the origin is not allowed". Any hostname
# this deployment is reachable on must be listed, or writes from it stop.

WILDCARD = "*"

# Mirrors the verbs the app actually routes. OPTIONS is absent deliberately:
# CORSMiddleware answers preflight itself and does not need it listed.
ALLOWED_METHODS: tuple[str, ...] = ("GET", "POST", "PATCH", "DELETE")

# Only these get the origin check. GET/HEAD read public data, and OPTIONS *is*
# the preflight -- 403ing it would break the very handshake that tells the
# browser whether the write is allowed.
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Logging a method verbatim is the same hazard as logging the path: it reaches us
# from the request line. Mapping through a fixed table means only these literals
# can ever be written.
_METHOD_FOR_LOG = {m: m for m in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")}

# Called by a third party that signs its own requests. Xendit will never appear
# in any origin allow-list, and the control that actually protects this path is
# the constant-time XENDIT_CALLBACK_TOKEN comparison inside the handler.
ORIGIN_CHECK_EXEMPT_PATHS: tuple[str, ...] = ("/api/v1/webhooks/xendit",)

# Deliberately says nothing about which origins are allowed. Echoing the
# rejected origin, or listing the accepted ones, turns a 403 into a probe.
ORIGIN_REJECTED_DETAIL = "origin not allowed for state-changing requests"


class CorsMisconfigured(RuntimeError):
    """The CORS environment asks for a combination no browser will accept."""


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _normalise(origin: str) -> str:
    """An origin as the browser sends it: no trailing slash, no surrounding space.

    Operators write ``https://example.test/`` in env files all the time; a browser
    never sends the trailing slash, so without this the entry silently matches
    nothing.
    """
    return origin.strip().rstrip("/")


def allowed_origins() -> list[str]:
    """The configured allow-list, or the safe default when CORS_ALLOW_ORIGINS is unset.

    Read at call time (the pattern used by security.py, mailer.py and xendit.py)
    so a test or a redeploy can change it without reimporting this module.
    """
    raw = (os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        return list(DEFAULT_ALLOWED_ORIGINS)
    parsed = [_normalise(o) for o in raw.split(",")]
    origins = [o for o in parsed if o]
    # An env var set to only commas/whitespace is a typo, not a request to allow
    # nothing. Falling back beats silently locking every browser out.
    return origins or list(DEFAULT_ALLOWED_ORIGINS)


def allow_credentials(origins: Sequence[str]) -> bool:
    """Whether to send ``Access-Control-Allow-Credentials``, refusing the illegal pair.

    Defaults to FALSE, and nothing in this system needs it turned on: auth is a
    Bearer token in a header, there are no auth cookies, and a header is attached
    by our own code rather than by the browser's credential machinery.

    When an operator sets CORS_ALLOW_CREDENTIALS with the origin list left at
    "*", we RAISE instead of quietly dropping one half. The CORS spec forbids the
    combination and every browser rejects the response outright, so the
    configuration the operator thinks they wrote does not exist. Silently
    downgrading -- ignoring the credentials flag, or narrowing the wildcard --
    would ship an API that fails only inside a browser, with a console message
    that names CORS but not the setting that caused it. Failing at startup puts
    it in the deploy log, in front of the person who can fix it, before a single
    user sees it.
    """
    wanted = _flag("CORS_ALLOW_CREDENTIALS", False)
    if wanted and WILDCARD in origins:
        raise CorsMisconfigured(
            "CORS_ALLOW_CREDENTIALS is on while CORS_ALLOW_ORIGINS is '*'. Browsers "
            "reject that pair, so it can never work. List the exact origins instead."
        )
    return wanted


def is_exempt_path(path: str) -> bool:
    """True for paths whose caller is a third party, not a browser."""
    candidate = path.rstrip("/") or "/"
    return any(candidate == exempt.rstrip("/") for exempt in ORIGIN_CHECK_EXEMPT_PATHS)


def rejection_reason(method: str, path: str, origin: Optional[str],
                     allowed: Iterable[str]) -> Optional[str]:
    """Why this request must be refused before its handler runs, or None to proceed.

    Pure function of the request line and one header, so the policy can be tested
    without an HTTP round-trip.
    """
    if method.upper() not in STATE_CHANGING_METHODS:
        return None
    if is_exempt_path(path):
        return None
    if origin is None or not origin.strip():
        # No Origin at all: curl, server-to-server jobs, and every mobile client.
        # A browser ALWAYS sends one on a cross-origin write, so the case this
        # guard exists for is unaffected -- whereas rejecting here would break
        # real non-browser clients to close a hole they cannot open. Breaking
        # them is the worse outcome, so a missing Origin passes.
        return None
    allowed_set = {_normalise(o) for o in allowed}
    if WILDCARD in allowed_set:
        return None
    if _normalise(origin) in allowed_set:
        return None
    # Covers "null" too (sandboxed iframes, file:// pages), which is never on the
    # list and should not be.
    return ORIGIN_REJECTED_DETAIL


class WriteOriginGuard:
    """ASGI middleware: 403 a state-changing request from an unvetted browser origin.

    Written against the raw ASGI interface rather than Starlette's
    BaseHTTPMiddleware because it needs one request header and nothing else --
    never the request body, never the response. The plain form keeps it entirely
    out of the response path, which matters for the endpoints that stream or
    attach BackgroundTasks (``/api/v1/auth/forgot-password`` sends its email
    after the response).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        reason = rejection_reason(
            method=scope.get("method", ""),
            path=scope.get("path", ""),
            origin=_scope_origin(scope),
            allowed=allowed_origins(),
        )
        if reason is None:
            await self.app(scope, receive, send)
            return

        # Both the origin AND the path are attacker-controlled, and uvicorn
        # percent-DECODES the path into the scope, so a raw %0a arrives here as a
        # real newline. Logging the path bare let a caller forge whole log lines --
        # a request to /api/v1/x%0aINFO:audit:wallet%20credited... produced a
        # fabricated wallet-credit entry. %r escapes the newline, so a forged line
        # can no longer break out of this one.
        logging.warning("blocked %s %r: origin not on the CORS allow-list",
                        _METHOD_FOR_LOG.get(scope.get("method", ""), "?"),
                        scope.get("path", ""))
        await JSONResponse({"detail": reason}, status_code=403)(scope, receive, send)


def _scope_origin(scope: Scope) -> Optional[str]:
    for name, value in scope.get("headers") or ():
        if name == b"origin":
            # latin-1 is the ASGI spec's header encoding; it cannot raise.
            return value.decode("latin-1")
    return None
