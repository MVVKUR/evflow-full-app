"""DB-backed tests for the demo-account seeding in scripts/seed_db.py.

These guard the production hazard: DEPLOY.md runs `python -m scripts.seed_db`
against the live DB, so the seeder must never invent a password, never mint
spendable money by default, never mint it twice, and never reset an existing
demo user's password.

Only station/connector seeding is skipped here — seed_demo_users() is driven
directly against a transaction so the tests stay fast.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.conftest import requires_db

from scripts import seed_db

DEMO_USERNAMES = tuple(u[1] for u in seed_db.DEMO_USERS)


def _purge_demo_rows() -> None:
    from api.db import engine
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM topups WHERE user_id IN (
                SELECT id FROM users WHERE username = ANY(:names))
        """), {"names": list(DEMO_USERNAMES)})
        c.execute(text("""
            DELETE FROM wallet WHERE user_id IN (
                SELECT id FROM users WHERE username = ANY(:names))
        """), {"names": list(DEMO_USERNAMES)})
        c.execute(text("DELETE FROM users WHERE username = ANY(:names)"),
                  {"names": list(DEMO_USERNAMES)})


@pytest.fixture
def clean_demo():
    _purge_demo_rows()
    yield
    _purge_demo_rows()


def _run_seed() -> str:
    from api.db import engine
    with engine.begin() as c:
        return seed_db.seed_demo_users(c)


def _demo_state() -> list[dict]:
    from api.db import engine
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT u.username,
                   u.password_hash,
                   COALESCE(w.balance_idr, 0)                      AS balance_idr,
                   (SELECT COUNT(*) FROM topups t WHERE t.user_id = u.id) AS topup_rows,
                   (SELECT COALESCE(SUM(t.amount_idr), 0) FROM topups t
                     WHERE t.user_id = u.id AND t.status = 'paid')  AS ledger_idr
            FROM users u
            LEFT JOIN wallet w ON w.user_id = u.id
            WHERE u.username = ANY(:names)
            ORDER BY u.username
        """), {"names": list(DEMO_USERNAMES)}).mappings().all()
    return [dict(r) for r in rows]


@requires_db
def test_no_password_env_seeds_nothing(monkeypatch, clean_demo):
    monkeypatch.delenv(seed_db.DEMO_PASSWORD_ENV, raising=False)
    summary = _run_seed()
    assert "skipped" in summary
    assert _demo_state() == []


@requires_db
def test_blank_password_env_seeds_nothing(monkeypatch, clean_demo):
    monkeypatch.setenv(seed_db.DEMO_PASSWORD_ENV, "   ")
    _run_seed()
    assert _demo_state() == []


@requires_db
def test_wallet_not_seeded_when_flag_off(monkeypatch, clean_demo):
    monkeypatch.setenv(seed_db.DEMO_PASSWORD_ENV, "seed-test-password-1")
    monkeypatch.delenv(seed_db.SEED_WALLET_ENV, raising=False)

    _run_seed()

    state = _demo_state()
    assert [r["username"] for r in state] == sorted(DEMO_USERNAMES)
    for row in state:
        assert row["balance_idr"] == 0, "flag off must not create spendable money"
        assert row["topup_rows"] == 0


@requires_db
def test_wallet_flag_off_by_default_for_arbitrary_values(monkeypatch, clean_demo):
    monkeypatch.setenv(seed_db.DEMO_PASSWORD_ENV, "seed-test-password-1")
    for value in ("", "0", "false", "no", "off", "maybe"):
        monkeypatch.setenv(seed_db.SEED_WALLET_ENV, value)
        _run_seed()
        assert all(r["balance_idr"] == 0 for r in _demo_state()), value


@requires_db
def test_wallet_grant_is_idempotent_and_matches_the_ledger(monkeypatch, clean_demo):
    monkeypatch.setenv(seed_db.DEMO_PASSWORD_ENV, "seed-test-password-1")
    monkeypatch.setenv(seed_db.SEED_WALLET_ENV, "true")
    monkeypatch.setenv(seed_db.DEMO_WALLET_BALANCE_ENV, "500000")

    _run_seed()
    first = _demo_state()
    assert len(first) == len(DEMO_USERNAMES)
    for row in first:
        assert row["balance_idr"] == 500000
        # the money is backed by the ledger, so wallet and topups reconcile
        assert row["topup_rows"] == 1
        assert row["ledger_idr"] == 500000

    # a second (and third) run must not add money again
    _run_seed()
    _run_seed()
    for row in _demo_state():
        assert row["balance_idr"] == 500000, "re-seed double-credited the wallet"
        assert row["topup_rows"] == 1
        assert row["ledger_idr"] == row["balance_idr"]


@requires_db
def test_reseed_does_not_reset_existing_password(monkeypatch, clean_demo):
    monkeypatch.setenv(seed_db.DEMO_PASSWORD_ENV, "seed-test-password-1")
    _run_seed()
    before = {r["username"]: r["password_hash"] for r in _demo_state()}

    # someone rotates the demo password out of band, then the seed is re-run
    # with the OLD value still in the environment
    from api import security
    from api.db import engine
    rotated = security.hash_password("rotated-by-the-user")
    with engine.begin() as c:
        c.execute(text("UPDATE users SET password_hash = :ph WHERE username = ANY(:names)"),
                  {"ph": rotated, "names": list(DEMO_USERNAMES)})

    monkeypatch.setenv(seed_db.DEMO_PASSWORD_ENV, "seed-test-password-2")
    _run_seed()

    after = {r["username"]: r["password_hash"] for r in _demo_state()}
    for username in DEMO_USERNAMES:
        assert after[username] == rotated, "re-seed silently reset an existing password"
        assert after[username] != before[username]


@requires_db
def test_invalid_wallet_amount_is_rejected(monkeypatch, clean_demo):
    monkeypatch.setenv(seed_db.DEMO_PASSWORD_ENV, "seed-test-password-1")
    monkeypatch.setenv(seed_db.SEED_WALLET_ENV, "true")
    monkeypatch.setenv(seed_db.DEMO_WALLET_BALANCE_ENV, "0")
    with pytest.raises(SystemExit):
        _run_seed()

    monkeypatch.setenv(seed_db.DEMO_WALLET_BALANCE_ENV, "not-a-number")
    with pytest.raises(SystemExit):
        _run_seed()
