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

# bcrypt hashes at most 72 BYTES of the secret and raises ValueError above that,
# so every entry point that accepts a password must cap it in BYTES (not
# characters: "ä" is one character but two UTF-8 bytes).
MAX_PASSWORD_BYTES = 72

# `iat` used to be int(time.time()), i.e. floored to a whole second, while
# `users.password_changed_at` is a microsecond-precision timestamptz. A token
# minted at 10:00:00.750, half a second AFTER a password change at 10:00:00.250,
# recorded iat=10:00:00 and so looked older than the change: `issued < changed`
# rejected it and the user was logged straight back out of the session the reset
# had just handed them.
#
# WHICH SIDE TO NORMALISE. Rounding either side onto a one-second grid (or adding
# a tolerance) "fixes" it only by opening a hole of that same size, through which
# a stolen pre-reset token survives the reset -- and that is the one property this
# check exists to provide. So neither side is blunted. Instead `iat` is given the
# precision it was always missing, and the comparison stays exact:
#
#   * iat is minted with microsecond precision (RFC 7519 NumericDate explicitly
#     permits a non-integer value), matching the resolution of the column it is
#     compared against;
#   * both timestamps are taken from the SAME clock (see users_repo.update_password),
#     so app/database clock skew cannot reject a token minted after the change.
#
# There is therefore no grace window at all: >= the change is accepted, < the
# change is rejected, to the microsecond. Nothing here is tunable, deliberately --
# every knob that could be added would only widen the hole.
#
# Tokens minted BEFORE this change still carry a whole-second iat and so read up
# to a second older than they really are. That errs towards rejection, which for
# a password reset is the safe direction, and it drains within one token lifetime.
TOKEN_IAT_PRECISION_DECIMALS = 6


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


def password_length_problem(plain: str) -> Optional[str]:
    """Why `plain` cannot be hashed, or None if it fits.

    Counts UTF-8 BYTES, which is what bcrypt limits. A 72-character password of
    accented or non-Latin text is well over 72 bytes and used to sail past a
    character-based check and then blow up inside bcrypt.
    """
    if len(plain.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return (f"password must be at most {MAX_PASSWORD_BYTES} bytes when encoded as UTF-8 "
                f"(accented and non-Latin characters take more than one byte each)")
    return None


def _truncate_to_max_bytes(plain: str) -> bytes:
    """The first `MAX_PASSWORD_BYTES` bytes of `plain`, never splitting a character."""
    raw = plain.encode("utf-8")
    if len(raw) <= MAX_PASSWORD_BYTES:
        return raw
    return raw[:MAX_PASSWORD_BYTES].decode("utf-8", "ignore").encode("utf-8")


def hash_password(plain: str) -> str:
    """Hash a password. Raises ValueError with a readable message when too long.

    Every HTTP boundary validates the byte length first, so this only fires for
    non-HTTP callers (the demo seeding script), which get a clear message instead
    of a bcrypt internal error.
    """
    problem = password_length_problem(plain)
    if problem:
        raise ValueError(problem)
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a candidate password. Never raises.

    The candidate is truncated to bcrypt's 72-byte limit rather than rejected.
    Older bcrypt releases truncated silently, so an account created before the
    byte cap existed may hold a hash of only the first 72 bytes of a longer
    password. Rejecting the full password outright would lock that account out
    permanently. Truncating reproduces exactly how the stored hash was produced
    and gives away nothing: the bytes past 72 never contributed to it.
    Registration and reset now refuse over-long passwords, so no NEW account can
    be created this way.
    """
    try:
        return bcrypt.checkpw(_truncate_to_max_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str) -> str:
    secret = _require_secret()
    now = time.time()
    # `iat` keeps sub-second precision so it can be compared exactly against
    # password_changed_at (see TOKEN_IAT_PRECISION_DECIMALS). `exp` stays the
    # whole-second integer it has always been -- its meaning is unchanged.
    payload = {
        "sub": str(user_id),
        "iat": round(now, TOKEN_IAT_PRECISION_DECIMALS),
        "exp": int(now) + _expire_minutes() * 60,
    }
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
    # password reset logs out every previously issued session. Exact, no grace
    # window: a token issued AT or AFTER the change is accepted, one issued
    # genuinely before it is rejected. See TOKEN_IAT_PRECISION_DECIMALS.
    changed = user.get("password_changed_at")
    issued = payload.get("iat")
    if changed is not None and issued is not None and issued < changed.timestamp():
        raise HTTPException(401, "session expired, please log in again")
    return user
