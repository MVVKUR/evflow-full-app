"""Payback arithmetic, and the ways a naive version of it lies.

The frontend currently computes payback as `max(2.5, 5.5 - score/30)`, which
always returns a number between 2.5 and 5.5 years no matter what the site costs
or earns. Replacing that is only worth doing if the replacement refuses to
answer when it cannot, so most of these tests are about the refusals.

Two of them matter more than the rest. A site whose revenue does not cover its
running costs never pays back, and the naive formula capex / (revenue - opex)
returns a NEGATIVE number there, which renders as "-3.2 years" and reads like a
fast payback rather than a loss. And a site cannot serve more sessions than its
connectors physically allow, so an assumption above that ceiling is not
optimistic, it is impossible, and a projection built on it is fiction.
"""
import math

import pytest

from api.services.site_economics import (
    DAYS_PER_MONTH,
    SiteEconomicsInput,
    capacity_sessions_per_day,
    project,
    sessions_from_utilisation,
)


def _input(**over):
    base = dict(
        connectors=2, power_kw=60.0,
        sessions_per_day=12.0, energy_per_session_kwh=30.0,
        capex_per_connector_idr=250_000_000, opex_monthly_idr=15_000_000,
        tariff_idr_per_kwh=2466, admin_fee_idr=2500, horizon_years=10,
    )
    base.update(over)
    return SiteEconomicsInput(**base)


# --------------------------------------------------------------- the arithmetic

def test_revenue_follows_energy_sold_plus_the_admin_fee():
    r = project(_input(sessions_per_day=10.0, energy_per_session_kwh=30.0))
    sessions_month = 10.0 * DAYS_PER_MONTH
    expected = round(sessions_month * 30.0 * 2466 + sessions_month * 2500)
    assert r["revenue_monthly_idr"] == expected


def test_capex_counts_every_connector():
    r = project(_input(connectors=4, capex_per_connector_idr=250_000_000))
    assert r["capex_total_idr"] == 1_000_000_000


def test_payback_is_capex_over_the_monthly_margin():
    r = project(_input())
    margin = r["revenue_monthly_idr"] - r["opex_monthly_idr"]
    assert margin > 0
    assert r["payback_months"] == pytest.approx(r["capex_total_idr"] / margin, rel=1e-9)
    assert r["payback_years"] == pytest.approx(r["payback_months"] / 12, rel=1e-9)
    assert r["breaks_even"] is True


# ------------------------------------------------------- the refusal that matters

def test_a_site_that_loses_money_never_pays_back():
    # capex / (revenue - opex) is negative here. Reporting that as a payback
    # period turns a business that bleeds money into one that looks quick.
    r = project(_input(sessions_per_day=1.0, opex_monthly_idr=50_000_000))
    assert r["gross_margin_monthly_idr"] < 0
    assert r["payback_months"] is None
    assert r["payback_years"] is None
    assert r["breaks_even"] is False


def test_a_site_that_exactly_covers_its_costs_never_pays_back_either():
    # Margin of zero is division by zero, not an infinitely good investment.
    r = project(_input())
    r2 = project(_input(opex_monthly_idr=r["revenue_monthly_idr"]))
    assert r2["gross_margin_monthly_idr"] == 0
    assert r2["payback_months"] is None
    assert r2["breaks_even"] is False


def test_the_loss_is_still_reported_at_the_horizon():
    # Refusing to give a payback must not mean refusing to say how bad it is.
    r = project(_input(sessions_per_day=1.0, opex_monthly_idr=50_000_000))
    assert r["net_at_horizon_idr"] < 0


# ------------------------------------------------------ the physical ceiling

def test_capacity_is_bounded_by_connectors_and_charge_time():
    # 30 kWh at 60 kW is half an hour, so one connector serves 48 a day.
    assert capacity_sessions_per_day(1, 60.0, 30.0) == pytest.approx(48.0)
    assert capacity_sessions_per_day(2, 60.0, 30.0) == pytest.approx(96.0)
    # A slow charger serves far fewer.
    assert capacity_sessions_per_day(2, 7.0, 30.0) == pytest.approx(2 * 24 / (30 / 7))


def test_utilisation_is_reported_against_that_ceiling():
    r = project(_input(connectors=2, power_kw=60.0,
                       energy_per_session_kwh=30.0, sessions_per_day=48.0))
    assert r["capacity_sessions_per_day"] == pytest.approx(96.0)
    assert r["utilisation"] == pytest.approx(0.5)


def test_demand_above_the_physical_ceiling_is_refused():
    # Not clamped quietly. A planner who assumed 200 sessions on two connectors
    # has made an error, and silently projecting 96 would hide it while still
    # producing a confident payback figure.
    with pytest.raises(ValueError, match="capacity"):
        project(_input(connectors=2, power_kw=60.0,
                       energy_per_session_kwh=30.0, sessions_per_day=200.0))


# ------------------------------------------------------------- input validation

def test_a_site_needs_at_least_one_connector():
    with pytest.raises(ValueError, match="connector"):
        project(_input(connectors=0))


def test_negative_money_is_refused():
    with pytest.raises(ValueError, match="capex"):
        project(_input(capex_per_connector_idr=-1))
    with pytest.raises(ValueError, match="opex"):
        project(_input(opex_monthly_idr=-1))


def test_a_zero_or_negative_tariff_is_refused():
    with pytest.raises(ValueError, match="tariff"):
        project(_input(tariff_idr_per_kwh=0))


def test_power_and_energy_must_be_positive():
    with pytest.raises(ValueError, match="power"):
        project(_input(power_kw=0))
    with pytest.raises(ValueError, match="energy"):
        project(_input(energy_per_session_kwh=0))


def test_negative_demand_is_refused():
    with pytest.raises(ValueError, match="sessions"):
        project(_input(sessions_per_day=-1))


def test_non_finite_input_is_refused():
    for field in ("power_kw", "energy_per_session_kwh", "sessions_per_day"):
        with pytest.raises(ValueError, match="finite"):
            project(_input(**{field: float("nan")}))
        with pytest.raises(ValueError, match="finite"):
            project(_input(**{field: float("inf")}))


def test_the_horizon_must_be_a_real_span():
    with pytest.raises(ValueError, match="horizon"):
        project(_input(horizon_years=0))


# --------------------------------------------------------------- no silent drift

def test_zero_demand_is_allowed_and_says_the_site_earns_nothing():
    # A legitimate question: what if nobody comes. It must answer, not raise.
    r = project(_input(sessions_per_day=0.0))
    assert r["revenue_monthly_idr"] == 0
    assert r["payback_months"] is None
    assert r["utilisation"] == 0.0


def test_days_per_month_is_the_averaged_year_not_a_round_thirty():
    assert DAYS_PER_MONTH == pytest.approx(365.25 / 12)
    assert not math.isclose(DAYS_PER_MONTH, 30.0)


# ------------------------------------------------ demand expressed as utilisation

def test_utilisation_converts_to_the_daily_sessions_it_implies():
    # A planner thinks in "busy a fifth of the time", not in sessions per day,
    # and utilisation is the figure comparable against what neighbours do.
    assert sessions_from_utilisation(0.5, 2, 60.0, 30.0) == pytest.approx(48.0)
    assert sessions_from_utilisation(0.0, 2, 60.0, 30.0) == 0.0
    assert sessions_from_utilisation(1.0, 2, 60.0, 30.0) == pytest.approx(96.0)


def test_a_utilisation_derived_demand_can_never_exceed_capacity():
    # The round trip must not be able to construct the impossible input that
    # project() is built to refuse.
    s = sessions_from_utilisation(1.0, 2, 60.0, 30.0)
    assert project(_input(sessions_per_day=s))["utilisation"] == pytest.approx(1.0)


def test_utilisation_outside_zero_to_one_is_refused():
    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError, match="between 0 and 1"):
            sessions_from_utilisation(bad, 2, 60.0, 30.0)
    with pytest.raises(ValueError, match="finite"):
        sessions_from_utilisation(float("nan"), 2, 60.0, 30.0)


def test_a_negative_admin_fee_is_refused():
    with pytest.raises(ValueError, match="admin fee"):
        project(_input(admin_fee_idr=-1))


# ------------------------------------------- what the operator actually keeps

def test_energy_bought_is_subtracted_from_energy_sold():
    # The tariff is what the driver pays. The operator buys that same energy
    # from PLN first, and only keeps the spread. Treating the full tariff as
    # revenue overstates every projection.
    sold = project(_input(sessions_per_day=10.0, energy_cost_idr_per_kwh=0))
    bought = project(_input(sessions_per_day=10.0, energy_cost_idr_per_kwh=1500))
    assert bought["revenue_monthly_idr"] == sold["revenue_monthly_idr"]
    assert bought["energy_cost_monthly_idr"] > 0
    assert bought["gross_margin_monthly_idr"] < sold["gross_margin_monthly_idr"]


def test_energy_cost_is_priced_per_kwh_delivered():
    r = project(_input(sessions_per_day=10.0, energy_cost_idr_per_kwh=1500))
    assert r["energy_cost_monthly_idr"] == round(r["energy_per_month_kwh"] * 1500)


def test_margin_is_revenue_less_energy_and_opex():
    r = project(_input(sessions_per_day=10.0, energy_cost_idr_per_kwh=1500))
    assert r["gross_margin_monthly_idr"] == (
        r["revenue_monthly_idr"] - r["energy_cost_monthly_idr"] - r["opex_monthly_idr"])


def test_selling_below_the_purchase_price_shows_as_a_loss_not_a_payback():
    # A real failure mode when a tariff is capped below cost. It must not
    # produce a payback period.
    r = project(_input(sessions_per_day=40.0, energy_cost_idr_per_kwh=5000))
    assert r["gross_margin_monthly_idr"] < 0
    assert r["payback_months"] is None


def test_energy_cost_defaults_to_zero_meaning_it_sits_inside_opex():
    r = project(_input(sessions_per_day=10.0))
    assert r["energy_cost_monthly_idr"] == 0
    assert r["energy_cost_idr_per_kwh"] == 0


def test_a_negative_energy_cost_is_refused():
    with pytest.raises(ValueError, match="energy cost"):
        project(_input(energy_cost_idr_per_kwh=-1))
