"""Wallet + top-up persistence scoped to the authenticated user."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from .db import engine


def get_wallet(user_id: str) -> dict:
    with engine.begin() as c:
        r = c.execute(text("SELECT balance_idr, updated_at FROM wallet WHERE user_id = :uid"), {"uid": user_id}).mappings().first()
        if r is None:
            r = c.execute(text("""
                INSERT INTO wallet (id, user_id, balance_idr)
                VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM wallet), :uid, 0)
                RETURNING balance_idr, updated_at
            """), {"uid": user_id}).mappings().first()
    return {"balance_idr": int(r["balance_idr"]), "updated_at": r["updated_at"]}


def create_topup(user_id: str, amount_idr: int, external_id: str, invoice_id: str, invoice_url: str,
                 topup_id: str | None = None) -> dict:
    topup_id = topup_id or str(uuid.uuid4())
    get_wallet(user_id)
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO topups (id, user_id, external_id, xendit_invoice_id, amount_idr, status, invoice_url)
            VALUES (:id, :uid, :ext, :inv, :amt, 'pending', :url)
        """), {"id": topup_id, "uid": user_id, "ext": external_id, "inv": invoice_id, "amt": amount_idr, "url": invoice_url})
    return {"topup_id": topup_id, "amount_idr": amount_idr, "status": "pending", "invoice_url": invoice_url}


def mark_paid_and_credit(invoice_id: str) -> bool:
    """Flip a pending topup to paid and credit the wallet, atomically. Idempotent.

    Returns True if it credited, False if no pending topup matched (already paid or unknown).
    """
    with engine.begin() as c:
        row = c.execute(text("""
            UPDATE topups SET status = 'paid', paid_at = now()
            WHERE xendit_invoice_id = :inv AND status = 'pending'
            RETURNING amount_idr, user_id
        """), {"inv": invoice_id}).first()
        if row is None:
            return False
        c.execute(text("UPDATE wallet SET balance_idr = balance_idr + :amt, updated_at = now() WHERE user_id = :uid"),
                  {"amt": int(row[0]), "uid": str(row[1])})
    return True


def get_topup(topup_id: str, user_id: str) -> dict | None:
    with engine.connect() as c:
        r = c.execute(text("""
            SELECT id, external_id, xendit_invoice_id, amount_idr, status, invoice_url, created_at, paid_at
            FROM topups WHERE id = :id AND user_id = :uid
        """), {"id": topup_id, "uid": user_id}).mappings().first()
    return None if r is None else {**dict(r), "id": str(r["id"])}


def list_topups(user_id: str, limit: int = 20) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT id, external_id, xendit_invoice_id, amount_idr, status, invoice_url, created_at, paid_at
            FROM topups WHERE user_id = :uid ORDER BY created_at DESC LIMIT :lim
        """), {"uid": user_id, "lim": limit}).mappings().all()
    return [{**dict(r), "id": str(r["id"])} for r in rows]
