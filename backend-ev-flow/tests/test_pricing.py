"""Pure unit tests for charging price quotes + settlement (no DB)."""
from api import pricing


def test_quote_breakdown(monkeypatch):
    monkeypatch.setenv("CHARGING_BASE_RATE_IDR", "2466")
    monkeypatch.setenv("CHARGING_ADMIN_FEE_IDR", "2500")
    q = pricing.quote(20)
    assert q["base_rate_idr"] == 2466
    assert q["admin_fee_idr"] == 2500
    assert q["energy_cost_idr"] == 49320          # 20 * 2466
    assert q["total_due_idr"] == 51820            # + admin fee


def test_settlement_refunds_undelivered(monkeypatch):
    monkeypatch.setenv("CHARGING_BASE_RATE_IDR", "2466")
    monkeypatch.setenv("CHARGING_ADMIN_FEE_IDR", "2500")
    s = pricing.settlement(20, 16.5)
    assert s["delivered_kwh"] == 16.5
    assert s["actual_cost_idr"] == round(16.5 * 2466) + 2500   # 43189
    assert s["deposit_idr"] == 51820
    assert s["refund_idr"] == 51820 - s["actual_cost_idr"]      # 8631


def test_settlement_never_negative_and_caps_at_purchased(monkeypatch):
    monkeypatch.setenv("CHARGING_BASE_RATE_IDR", "2466")
    monkeypatch.setenv("CHARGING_ADMIN_FEE_IDR", "2500")
    # delivered above purchased is capped -> full cost, zero refund
    full = pricing.settlement(20, 25)
    assert full["delivered_kwh"] == 20
    assert full["refund_idr"] == 0
    # delivered 0 -> only admin fee charged, rest refunded
    none = pricing.settlement(20, 0)
    assert none["actual_cost_idr"] == 2500
    assert none["refund_idr"] == 49320
