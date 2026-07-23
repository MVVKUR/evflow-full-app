"""Password hashing, JWT, Google CSRF state, and the current_user dependency.

Env is read at call time so tests can monkeypatch it without reimporting.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

import bcrypt
import jwt
from fastapi import Header, HTTPException


# Minimum key strength for HS256: a short or placeholder secret makes tokens
# and OAuth state trivially forgeable. Checked lazily (at call time, never at
# import time) so tests and dev tooling can still `import api.main`.
MIN_SECRET_LENGTH = 32
_PLACEHOLDER_PREFIXES = ("change", "your-")

# Google OAuth `state` values older than this are rejected (replay window).
STATE_MAX_AGE_SECONDS = 600


def _secret() -> str:
    return os.getenv("JWT_SECRET", "")


def _secret_problem(secret: str) -> Optional[str]:
    """Why `secret` is unusable for signing, or None if it is strong enough."""
    if not secret:
        return "JWT_SECRET is not set"
    if len(secret) < MIN_SECRET_LENGTH:
        return f"JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters"
    if secret.lower().startswith(_PLACEHOLDER_PREFIXES):
        return "JWT_SECRET looks like an unchanged placeholder value"
    return None


def _require_secret() -> str:
    """Return the JWT secret, or raise RuntimeError if it is missing/weak."""
    secret = _secret()
    problem = _secret_problem(secret)
    if problem:
        raise RuntimeError(problem)
    return secret


def _expire_minutes() -> int:
    return int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str) -> str:
    secret = _require_secret()
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + _expire_minutes() * 60}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str) -> str:
    # _require_secret raises RuntimeError on a missing/weak key so a token can
    # never be accepted against an empty or placeholder secret.
    return jwt.decode(token, _require_secret(), algorithms=["HS256"])["sub"]


def sign_state() -> str:
    """Signed OAuth state: nonce.timestamp.HMAC(nonce.timestamp)."""
    secret = _require_secret()
    nonce = secrets.token_urlsafe(16)
    msg = f"{nonce}.{int(time.time())}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}.{sig}"


def verify_state(state: Optional[str]) -> bool:
    secret = _secret()
    if _secret_problem(secret):  # fail closed: a weak key would make state trivially forgeable
        return False
    parts = (state or "").split(".")
    if len(parts) != 3:
        return False
    nonce, ts, sig = parts
    try:
        issued = int(ts)
    except ValueError:
        return False
    expected = hmac.new(secret.encode(), f"{nonce}.{ts}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    age = int(time.time()) - issued
    return 0 <= age <= STATE_MAX_AGE_SECONDS


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    secret = _secret()
    if _secret_problem(secret):  # fail closed: a missing/weak key would accept forged tokens
        raise HTTPException(401, "invalid or expired token")
    try:
        payload = jwt.decode(authorization.split(" ", 1)[1], secret, algorithms=["HS256"])
        user_id = payload["sub"]
    except Exception:
        raise HTTPException(401, "invalid or expired token")
    from . import users_repo
    user = users_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(401, "user not found")
    # Tokens minted before the last password change are no longer valid, so a
    # password reset logs out every previously issued session.
    changed = user.get("password_changed_at")
    issued = payload.get("iat")
    if changed is not None and issued is not None and issued < changed.timestamp():
        raise HTTPException(401, "session expired, please log in again")
    return user
