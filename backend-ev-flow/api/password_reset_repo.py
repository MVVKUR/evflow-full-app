"""Password-reset token persistence (Epic: account recovery).

Tokens are single-use and time-limited. Only the SHA-256 hash of the token is
stored; the raw token lives only in the emailed reset link. SQL via the shared
engine, same style as users_repo/wallet_repo.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from typing import Optional

from sqlalchemy import text

from .db import engine


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _ttl_minutes() -> int:
    return int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "60"))


def create_token(user_id: str) -> str:
    """Mint a reset token for the user, store its hash, and return the RAW token.

    Any prior tokens for the user are removed first, so only the newest link is
    valid (supersedes older requests) and the table can't grow per-user."""
    raw = secrets.token_urlsafe(32)
    token_id = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(text("DELETE FROM password_reset_tokens WHERE user_id = :uid"), {"uid": user_id})
        c.execute(text("""
            INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at)
            VALUES (:id, :uid, :th, now() + make_interval(mins => :ttl))
        """), {"id": token_id, "uid": user_id, "th": _hash(raw), "ttl": _ttl_minutes()})
    return raw


def consume_token(raw_token: str) -> Optional[str]:
    """Atomically validate+burn a token. Returns the user_id, or None if the token
    is unknown, already used, or expired. The conditional UPDATE makes it single-use
    even under concurrent requests."""
    if not raw_token:
        return None
    with engine.begin() as c:
        row = c.execute(text("""
            UPDATE password_reset_tokens
            SET used_at = now()
            WHERE token_hash = :th AND used_at IS NULL AND expires_at > now()
            RETURNING user_id
        """), {"th": _hash(raw_token)}).first()
    return str(row[0]) if row else None
