"""Charging-session persistence with real wallet debit/credit (Epic 4.0).

Money moves against the authenticated user's wallet:
  - start_session  debits the deposit (atomic balance check, fails if too low)
  - settle_session credits the unused-kWh refund (atomic + idempotent)

Both run in one transaction with the session-row write so the ledger and the
wallet can never drift.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import text

from . import connectors_repo  # must not import charging_repo back (would be circular)
from . import pricing
from .db import engine

logger = logging.getLogger(__name__)

_COLS = ("id, station_id, station_name, connector_type, power_kw, energy_kwh, "
         "base_rate_idr, admin_fee_idr, deposit_idr, delivered_kwh, "
         "actual_cost_idr, refund_idr, status, created_at, completed_at, connector_id")


class InsufficientBalance(Exception):
    """Wallet balance is below the deposit required to start a session."""


def _row(r) -> Optional[dict]:
    if r is None:
        return None
    d = dict(r)
    d["id"] = str(d["id"])
    if d.get("connector_id") is not None:
        d["connector_id"] = str(d["connector_id"])
    return d


def _occupy_connector(c, session_id: str, station_id: str, connector_type: Optional[str]) -> None:
    """Best-effort: claim an available connector for the session.

    Runs in a SAVEPOINT inside the money transaction so ANY failure here rolls
    back only the connector claim, never the wallet debit or session insert.
    A station with no connector rows (or none available) simply leaves
    connector_id NULL — charging is never blocked on connector inventory.
    """
    nested = None
    try:
        nested = c.begin_nested()
        cid = connectors_repo.occupy(c, station_id, connector_type)
        if cid is not None:
            c.execute(text("UPDATE charging_sessions SET connector_id = :cid WHERE id = :id"),
                      {"cid": cid, "id": session_id})
        nested.commit()
    except Exception:
        if nested is not None and nested.is_active:
            nested.rollback()
        logger.warning("connector occupy failed for station %s (session %s); continuing without one",
                       station_id, session_id, exc_info=True)


def _release_connector(c, connector_id) -> None:
    """Best-effort: free the session's connector on settle. Same SAVEPOINT
    isolation as _occupy_connector — a failure never breaks the refund."""
    if connector_id is None:
        return
    nested = None
    try:
        nested = c.begin_nested()
        connectors_repo.release(c, str(connector_id))
        nested.commit()
    except Exception:
        if nested is not None and nested.is_active:
            nested.rollback()
        logger.warning("connector release failed for connector %s; continuing", connector_id, exc_info=True)


def _ensure_wallet(c, user_id: str) -> int:
    balance = c.execute(text("SELECT balance_idr FROM wallet WHERE user_id = :uid"), {"uid": user_id}).scalar()
    if balance is not None:
        return int(balance)
    return int(c.execute(text("""
        INSERT INTO wallet (id, user_id, balance_idr)
        VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM wallet), :uid, 0)
        RETURNING balance_idr
    """), {"uid": user_id}).scalar_one())


def _wallet_balance(c, user_id: str) -> int:
    return _ensure_wallet(c, user_id)


def start_session(*, user_id: str, station_id: str, energy_kwh: float, station_name: Optional[str] = None,
                  connector_type: Optional[str] = None, power_kw: Optional[float] = None) -> dict:
    """Open a session and debit the deposit from the wallet, atomically.

    Raises InsufficientBalance (no state change) if the wallet can't cover the
    deposit. The conditional UPDATE makes the balance check race-free.
    """
    q = pricing.quote(energy_kwh)
    deposit = q["total_due_idr"]
    session_id = str(uuid.uuid4())
    with engine.begin() as c:
        _ensure_wallet(c, user_id)
        debited = c.execute(text("""
            UPDATE wallet SET balance_idr = balance_idr - :amt, updated_at = now()
            WHERE user_id = :uid AND balance_idr >= :amt
            RETURNING balance_idr
        """), {"uid": user_id, "amt": deposit}).first()
        if debited is None:
            raise InsufficientBalance(
                f"deposit {deposit} exceeds wallet balance {_wallet_balance(c, user_id)}")
        c.execute(text(f"""
            INSERT INTO charging_sessions
              (id, user_id, station_id, station_name, connector_type, power_kw, energy_kwh,
               base_rate_idr, admin_fee_idr, deposit_idr, status)
            VALUES
              (:id, :uid, :sid, :sname, :ctype, :pkw, :ekwh, :rate, :fee, :dep, 'active')
        """), {"id": session_id, "uid": user_id, "sid": station_id, "sname": station_name,
               "ctype": connector_type, "pkw": power_kw, "ekwh": energy_kwh,
               "rate": q["base_rate_idr"], "fee": q["admin_fee_idr"], "dep": deposit})
        _occupy_connector(c, session_id, station_id, connector_type)
        session = _row(c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id"),
                                 {"id": session_id}).mappings().first())
        session["wallet_balance_idr"] = int(debited[0])
    return session


def settle_session(user_id: str, session_id: str, delivered_kwh: float) -> Optional[dict]:
    """Finalize a session: bill for delivered energy, refund the rest. Idempotent.

    First settle computes cost/refund, credits the wallet, and marks the session
    completed. A repeat call finds no 'active' row and returns the already-stored
    settlement without crediting again. Returns None if the session is unknown.
    """
    with engine.begin() as c:
        existing = c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id AND user_id = :uid"),
                             {"id": session_id, "uid": user_id}).mappings().first()
        if existing is None:
            return None
        if existing["status"] != "active":  # already settled -> return stored result, no double-credit
            session = _row(existing)
            session["wallet_balance_idr"] = _wallet_balance(c, user_id)
            return session

        s = pricing.settlement(float(existing["energy_kwh"]), delivered_kwh)
        updated = c.execute(text("""
            UPDATE charging_sessions
            SET status = 'completed', delivered_kwh = :dk, actual_cost_idr = :ac,
                refund_idr = :rf, completed_at = now()
            WHERE id = :id AND user_id = :uid AND status = 'active'
            RETURNING refund_idr
        """), {"id": session_id, "uid": user_id, "dk": s["delivered_kwh"], "ac": s["actual_cost_idr"],
               "rf": s["refund_idr"]}).first()
        if updated is None:  # lost a race to a concurrent settle; re-read, don't re-credit
            session = _row(c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id AND user_id = :uid"),
                                     {"id": session_id, "uid": user_id}).mappings().first())
            session["wallet_balance_idr"] = _wallet_balance(c, user_id)
            return session

        _release_connector(c, existing["connector_id"])  # best-effort, never blocks the refund
        new_balance = c.execute(text("""
            UPDATE wallet SET balance_idr = balance_idr + :amt, updated_at = now()
            WHERE user_id = :uid RETURNING balance_idr
        """), {"uid": user_id, "amt": int(s["refund_idr"])}).scalar_one()
        session = _row(c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id AND user_id = :uid"),
                                 {"id": session_id, "uid": user_id}).mappings().first())
        session["wallet_balance_idr"] = int(new_balance)
    return session


def get_session(user_id: str, session_id: str) -> Optional[dict]:
    with engine.connect() as c:
        session = _row(c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id AND user_id = :uid"),
                                 {"id": session_id, "uid": user_id}).mappings().first())
        if session is None:
            return None
        session["wallet_balance_idr"] = _wallet_balance(c, user_id)
    return session


def list_sessions(user_id: str, limit: int = 20) -> list[dict]:
    with engine.connect() as c:
        balance = _wallet_balance(c, user_id)
        rows = c.execute(text(f"SELECT {_COLS} FROM charging_sessions "
                              f"WHERE user_id = :uid ORDER BY created_at DESC LIMIT :lim"), {"uid": user_id, "lim": limit}).mappings().all()
    return [{**_row(r), "wallet_balance_idr": balance} for r in rows]
