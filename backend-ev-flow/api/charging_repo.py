"""Charging-session persistence with real wallet debit/credit (Epic 4.0).

Money moves against the single shared wallet (id=1):
  - start_session  debits the deposit (atomic balance check, fails if too low)
  - settle_session credits the unused-kWh refund (atomic + idempotent)

Both run in one transaction with the session-row write so the ledger and the
wallet can never drift.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text

from . import pricing
from .db import engine

_COLS = ("id, station_id, station_name, connector_type, power_kw, energy_kwh, "
         "base_rate_idr, admin_fee_idr, deposit_idr, delivered_kwh, "
         "actual_cost_idr, refund_idr, status, created_at, completed_at")


class InsufficientBalance(Exception):
    """Wallet balance is below the deposit required to start a session."""


def _row(r) -> Optional[dict]:
    if r is None:
        return None
    d = dict(r)
    d["id"] = str(d["id"])
    return d


def _wallet_balance(c) -> int:
    return int(c.execute(text("SELECT balance_idr FROM wallet WHERE id = 1")).scalar_one())


def start_session(*, station_id: str, energy_kwh: float, station_name: Optional[str] = None,
                  connector_type: Optional[str] = None, power_kw: Optional[float] = None) -> dict:
    """Open a session and debit the deposit from the wallet, atomically.

    Raises InsufficientBalance (no state change) if the wallet can't cover the
    deposit. The conditional UPDATE makes the balance check race-free.
    """
    q = pricing.quote(energy_kwh)
    deposit = q["total_due_idr"]
    session_id = str(uuid.uuid4())
    with engine.begin() as c:
        debited = c.execute(text("""
            UPDATE wallet SET balance_idr = balance_idr - :amt, updated_at = now()
            WHERE id = 1 AND balance_idr >= :amt
            RETURNING balance_idr
        """), {"amt": deposit}).first()
        if debited is None:
            raise InsufficientBalance(
                f"deposit {deposit} exceeds wallet balance {_wallet_balance(c)}")
        c.execute(text(f"""
            INSERT INTO charging_sessions
              (id, station_id, station_name, connector_type, power_kw, energy_kwh,
               base_rate_idr, admin_fee_idr, deposit_idr, status)
            VALUES
              (:id, :sid, :sname, :ctype, :pkw, :ekwh, :rate, :fee, :dep, 'active')
        """), {"id": session_id, "sid": station_id, "sname": station_name,
               "ctype": connector_type, "pkw": power_kw, "ekwh": energy_kwh,
               "rate": q["base_rate_idr"], "fee": q["admin_fee_idr"], "dep": deposit})
        session = _row(c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id"),
                                 {"id": session_id}).mappings().first())
        session["wallet_balance_idr"] = int(debited[0])
    return session


def settle_session(session_id: str, delivered_kwh: float) -> Optional[dict]:
    """Finalize a session: bill for delivered energy, refund the rest. Idempotent.

    First settle computes cost/refund, credits the wallet, and marks the session
    completed. A repeat call finds no 'active' row and returns the already-stored
    settlement without crediting again. Returns None if the session is unknown.
    """
    with engine.begin() as c:
        existing = c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id"),
                             {"id": session_id}).mappings().first()
        if existing is None:
            return None
        if existing["status"] != "active":  # already settled -> return stored result, no double-credit
            session = _row(existing)
            session["wallet_balance_idr"] = _wallet_balance(c)
            return session

        s = pricing.settlement(float(existing["energy_kwh"]), delivered_kwh)
        updated = c.execute(text("""
            UPDATE charging_sessions
            SET status = 'completed', delivered_kwh = :dk, actual_cost_idr = :ac,
                refund_idr = :rf, completed_at = now()
            WHERE id = :id AND status = 'active'
            RETURNING refund_idr
        """), {"id": session_id, "dk": s["delivered_kwh"], "ac": s["actual_cost_idr"],
               "rf": s["refund_idr"]}).first()
        if updated is None:  # lost a race to a concurrent settle; re-read, don't re-credit
            session = _row(c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id"),
                                     {"id": session_id}).mappings().first())
            session["wallet_balance_idr"] = _wallet_balance(c)
            return session

        new_balance = c.execute(text("""
            UPDATE wallet SET balance_idr = balance_idr + :amt, updated_at = now()
            WHERE id = 1 RETURNING balance_idr
        """), {"amt": int(s["refund_idr"])}).scalar_one()
        session = _row(c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id"),
                                 {"id": session_id}).mappings().first())
        session["wallet_balance_idr"] = int(new_balance)
    return session


def get_session(session_id: str) -> Optional[dict]:
    with engine.connect() as c:
        session = _row(c.execute(text(f"SELECT {_COLS} FROM charging_sessions WHERE id = :id"),
                                 {"id": session_id}).mappings().first())
        if session is None:
            return None
        session["wallet_balance_idr"] = _wallet_balance(c)
    return session


def list_sessions(limit: int = 20) -> list[dict]:
    with engine.connect() as c:
        balance = _wallet_balance(c)
        rows = c.execute(text(f"SELECT {_COLS} FROM charging_sessions "
                              f"ORDER BY created_at DESC LIMIT :lim"), {"lim": limit}).mappings().all()
    return [{**_row(r), "wallet_balance_idr": balance} for r in rows]
