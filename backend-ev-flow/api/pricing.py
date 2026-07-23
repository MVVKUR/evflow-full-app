"""Charging price quotes (Epic 4.0).

Tariff is configured here (env-overridable) rather than hardcoded in the
frontend, so the backend is the single source of truth for what a session
costs. A real deployment would make this per-operator/per-station; for now it
is one flat public-charging tariff.

Pure / stdlib-only so it is unit-testable without a DB.
"""
from __future__ import annotations

import os


def base_rate_idr() -> int:
    """Energy price per kWh, in IDR."""
    return int(os.getenv("CHARGING_BASE_RATE_IDR", "2466"))


def admin_fee_idr() -> int:
    """Flat per-session admin fee, in IDR."""
    return int(os.getenv("CHARGING_ADMIN_FEE_IDR", "2500"))


def quote(energy_kwh: float) -> dict:
    """Break down what `energy_kwh` of charging will cost up front.

    The deposit charged at session start = total_due_idr. Settlement later
    refunds the unused portion based on energy actually delivered.
    """
    rate = base_rate_idr()
    fee = admin_fee_idr()
    energy_cost = round(energy_kwh * rate)
    return {
        "energy_kwh": energy_kwh,
        "base_rate_idr": rate,
        "admin_fee_idr": fee,
        "energy_cost_idr": energy_cost,
        "total_due_idr": energy_cost + fee,
        "currency": "IDR",
    }


def settlement(energy_kwh: float, delivered_kwh: float) -> dict:
    """Compute the final cost + refund for a completed session.

    Charged for energy actually delivered (capped at what was purchased), plus
    the same flat admin fee. Refund = deposit - actual_cost, never negative.

    `delivered_kwh` is client-reported pending charger-hardware integration,
    so it is clamped server-side to [0, energy_kwh] — a caller can never bill
    more than was purchased or turn a negative reading into extra refund.
    """
    purchased = quote(energy_kwh)
    billable_kwh = min(max(delivered_kwh, 0.0), energy_kwh)
    actual_cost = round(billable_kwh * base_rate_idr()) + admin_fee_idr()
    deposit = purchased["total_due_idr"]
    refund = max(deposit - actual_cost, 0)
    return {
        "delivered_kwh": billable_kwh,
        "actual_cost_idr": actual_cost,
        "deposit_idr": deposit,
        "refund_idr": refund,
    }
