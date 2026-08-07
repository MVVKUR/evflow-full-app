"""Rate limits on /auth/login, /auth/register and /auth/forgot-password.

These three are the endpoints where the limiter has to defend something and give
nothing away while doing it:

* /auth/login is a CPU denial-of-service primitive before it is a guessing one --
  one attempt against an existing account costs a bcrypt(cost 12) verify, ~300 ms
  of one of the ~40 shared threadpool threads every sync handler competes for --
  and the demo password ships in the public web bundle, so a known-good username
  is public knowledge;
* /auth/register creates a wallet row whose id is a smallint allocated by
  SELECT MAX(id)+1, so account 32,767 is the last one that can ever have a wallet;
* /auth/forgot-password turns one anonymous POST into one email to an address the
  caller names, against a shared SMTP account whose suspension would take both
  recovery paths (reset mail and the help desk) down together.

And a 429 must never answer a question a 401/404 refuses to: not "does this
account exist", not "which of my limits did I hit".

No database and no bcrypt: the repositories and the password functions are
replaced, so what is exercised is the handler's ordering and the limiter.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient      # noqa: E402

from api import rate_limit, security, users_repo   # noqa: E402
from api import wallet_repo as wallet              # noqa: E402
from api.main import app                           # noqa: E402

LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"
FORGOT = "/api/v1/auth/forgot-password"

# Long enough and not a placeholder, so security._require_secret() accepts it.
TEST_SECRET = "rate-limit-tests-secret-0123456789abcdef"
GOOD_PASSWORD = "s3cret123"

# Two callers at two addresses. In production both would arrive as loopback (see
# _client_ip in main.py); these prove the buckets are wired to the address the
# app is given, which is what starts discriminating the day a real one arrives.
CALLER_A = ("203.0.113.10", 41000)
CALLER_B = ("198.51.100.20", 41001)


def _client(source=CALLER_A) -> TestClient:
    """A client that presents `source` as its address."""
    return TestClient(app, client=source)


def _user(user_id: str = "user-a", username: str = "budi") -> dict:
    return {
        "id": user_id, "username": username, "email": f"{username}@example.test",
        "full_name": "Budi Santoso", "account_type": "ev_user", "ev_model_id": None,
        "main_connector_type": None, "location_consent": False,
        "profile_completed": False,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "password_hash": "$2b$12$not-a-real-hash",
    }


# ============================================================ POST /auth/login
@pytest.fixture
def login_backend(monkeypatch):
    """A known account, without a database and without paying for bcrypt."""
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    known = _user()
    calls = {"lookups": 0}

    def get_by_username_or_email(identifier: str):
        calls["lookups"] += 1
        return known if identifier in (known["username"], known["email"]) else None

    monkeypatch.setattr(users_repo, "get_by_username_or_email", get_by_username_or_email)
    monkeypatch.setattr(security, "verify_password", lambda pw, h: pw == GOOD_PASSWORD)
    return calls


def _login(client: TestClient, username: str = "budi", password: str = "wrong"):
    return client.post(LOGIN, json={"username": username, "password": password})


@pytest.mark.integration
def test_login_permits_normal_use_because_only_failures_are_charged(login_backend, monkeypatch):
    """A driver signs in about weekly (tokens last 7 days). However many times
    they succeed, they must never approach the limit -- which is what allows the
    limit to be low enough to matter."""
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_GLOBAL_RATE_LIMIT_REQUESTS", 2)
    client = _client()

    codes = [_login(client, password=GOOD_PASSWORD).status_code for _ in range(10)]

    assert codes == [200] * 10


@pytest.mark.integration
def test_login_blocks_a_brute_force_run(login_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    client = _client()

    codes = [_login(client, password=f"guess-{i}").status_code for i in range(6)]

    assert codes == [401, 401, 401, 429, 429, 429]


@pytest.mark.integration
def test_a_shed_login_never_reaches_the_lookup_or_the_hash(login_backend, monkeypatch):
    """The whole point of enforcing first: a shed request must cost nothing. If it
    reached security.verify_password it would still burn ~300 ms of a shared
    threadpool thread, and the 429 would be decoration."""
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 2)
    client = _client()
    for _ in range(2):
        _login(client)
    lookups_before = login_backend["lookups"]

    for _ in range(20):
        assert _login(client).status_code == 429

    assert login_backend["lookups"] == lookups_before


@pytest.mark.integration
def test_one_callers_failures_do_not_lock_out_another(login_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    attacker, bystander = _client(CALLER_A), _client(CALLER_B)

    for _ in range(4):
        _login(attacker)

    assert _login(attacker).status_code == 429
    assert _login(bystander).status_code == 401, "a bystander must still be able to try"
    assert _login(bystander, password=GOOD_PASSWORD).status_code == 200


@pytest.mark.integration
def test_the_deployment_wide_failure_ceiling_catches_credential_stuffing(login_backend, monkeypatch):
    """Many usernames from many sources is the shape a per-caller bucket misses;
    the global failure budget is what sees it."""
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_GLOBAL_RATE_LIMIT_REQUESTS", 4)

    for i in range(4):
        source = (f"203.0.113.{i}", 42000 + i)
        assert _login(_client(source), username=f"victim{i}").status_code == 401

    assert _login(_client(("203.0.113.99", 42099)), username="victim9").status_code == 429


@pytest.mark.integration
def test_the_login_lockout_expires(login_backend, monkeypatch, rate_limit_clock):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 2)
    client = _client()
    for _ in range(2):
        _login(client)
    assert _login(client).status_code == 429

    rate_limit_clock.advance(rate_limit.LOGIN_FAILURE_RATE_LIMIT_WINDOW_SECONDS + 1)

    assert _login(client).status_code == 401, "the window should have drained"


@pytest.mark.integration
def test_a_nonexistent_username_is_charged_exactly_like_a_real_one(login_backend, monkeypatch):
    """If only real accounts were charged, the moment 429s begin would itself
    answer 'does this account exist?' -- a cheaper oracle than the one being
    bounded."""
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 3)
    client = _client()

    codes = [_login(client, username="no-such-account").status_code for _ in range(5)]

    assert codes == [401, 401, 401, 429, 429]


@pytest.mark.integration
def test_the_429_body_is_identical_whether_or_not_the_account_exists(login_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 1)
    client = _client()
    _login(client)

    known = _login(client, username="budi")
    unknown = _login(client, username="no-such-account")

    assert known.status_code == unknown.status_code == 429
    assert known.json() == unknown.json()


@pytest.mark.integration
def test_the_429_body_does_not_say_which_limit_tripped(login_backend, monkeypatch):
    """Per-caller and deployment-wide must be indistinguishable, or the attacker
    learns which dimension to vary."""
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 1)
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    per_caller = _client(CALLER_A)
    _login(per_caller)
    caller_429 = _login(per_caller)

    rate_limit.reset()
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_GLOBAL_RATE_LIMIT_REQUESTS", 1)
    _login(_client(CALLER_B))
    global_429 = _login(_client(("203.0.113.77", 43000)))

    assert caller_429.json() == global_429.json()
    body = caller_429.json()["detail"].lower()
    for leak in ("global", "ip", "address", "deployment", "bucket"):
        assert leak not in body, f"the 429 names its bucket: {body!r}"


@pytest.mark.integration
def test_the_login_429_carries_one_retry_after_for_every_bucket(login_backend, monkeypatch):
    """Both buckets share one window on purpose: two windows on one endpoint would
    put 'which limit did I hit' into the header instead of the body."""
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 1)
    client = _client()
    _login(client)

    r = _login(client)

    assert r.headers["Retry-After"] == \
        str(int(rate_limit.LOGIN_FAILURE_RATE_LIMIT_WINDOW_SECONDS))


@pytest.mark.integration
def test_the_401_text_is_unchanged_and_still_generic(login_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 10)
    client = _client()

    known = _login(client, username="budi").json()["detail"]
    unknown = _login(client, username="no-such-account").json()["detail"]

    assert known == unknown == "invalid username/email or password"


@pytest.mark.integration
def test_the_rate_limit_log_line_names_no_caller(login_backend, monkeypatch, caplog):
    """The subject may be an address, a user id or an email hash, and this line
    lands in the access log (AC 2.3.2)."""
    monkeypatch.setattr(rate_limit, "LOGIN_FAILURE_RATE_LIMIT_REQUESTS", 1)
    client = _client()
    _login(client)

    with caplog.at_level("WARNING"):
        _login(client, username="budi")

    text = caplog.text
    assert "rate limit hit" in text
    assert CALLER_A[0] not in text
    assert "budi" not in text


# ========================================================= POST /auth/register
@pytest.fixture
def register_backend(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    created: list[dict] = []

    def create_user(**kwargs):
        created.append(kwargs)
        return _user(user_id=f"user-{len(created)}", username=kwargs["username"])

    monkeypatch.setattr(users_repo, "get_by_username", lambda username: None)
    monkeypatch.setattr(users_repo, "create_user", create_user)
    monkeypatch.setattr(wallet, "get_wallet", lambda user_id: {"balance_idr": 0})
    monkeypatch.setattr(security, "hash_password", lambda pw: "$2b$12$not-a-real-hash")
    return created


def _register(client: TestClient, n: int = 0):
    return client.post(REGISTER, json={"username": f"driver{n}", "password": GOOD_PASSWORD})


@pytest.mark.integration
def test_register_permits_a_classroom_signing_up(register_backend, monkeypatch):
    """Sized for a demo audience registering in one session, not for one human --
    a person registers once, ever."""
    monkeypatch.setattr(rate_limit, "REGISTER_RATE_LIMIT_REQUESTS", 20)
    monkeypatch.setattr(rate_limit, "REGISTER_GLOBAL_RATE_LIMIT_REQUESTS", 40)
    client = _client()

    codes = [_register(client, n).status_code for n in range(20)]

    assert codes == [201] * 20


@pytest.mark.integration
def test_register_blocks_bulk_account_creation(register_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "REGISTER_RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(rate_limit, "REGISTER_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    client = _client()

    codes = [_register(client, n).status_code for n in range(6)]

    assert codes == [201, 201, 201, 429, 429, 429]


@pytest.mark.integration
def test_no_account_and_no_wallet_row_is_created_once_the_limit_is_hit(register_backend, monkeypatch):
    """This is the assertion that protects the smallint wallet id: the wallet
    table is what runs out at 32,767 rows, permanently."""
    monkeypatch.setattr(rate_limit, "REGISTER_RATE_LIMIT_REQUESTS", 2)
    client = _client()
    for n in range(2):
        _register(client, n)

    for n in range(2, 30):
        assert _register(client, n).status_code == 429

    assert len(register_backend) == 2


@pytest.mark.integration
def test_register_is_bucketed_per_caller(register_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "REGISTER_RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(rate_limit, "REGISTER_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    a, b = _client(CALLER_A), _client(CALLER_B)
    for n in range(2):
        _register(a, n)

    assert _register(a, 9).status_code == 429
    assert _register(b, 10).status_code == 201


@pytest.mark.integration
def test_the_deployment_wide_register_ceiling_holds_across_callers(register_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "REGISTER_RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(rate_limit, "REGISTER_GLOBAL_RATE_LIMIT_REQUESTS", 3)

    codes = [_register(_client((f"203.0.113.{n}", 44000 + n)), n).status_code
             for n in range(5)]

    assert codes == [201, 201, 201, 429, 429]


@pytest.mark.integration
def test_the_register_limit_expires(register_backend, monkeypatch, rate_limit_clock):
    monkeypatch.setattr(rate_limit, "REGISTER_RATE_LIMIT_REQUESTS", 1)
    client = _client()
    _register(client, 0)
    assert _register(client, 1).status_code == 429

    rate_limit_clock.advance(rate_limit.REGISTER_RATE_LIMIT_WINDOW_SECONDS + 1)

    assert _register(client, 2).status_code == 201


# ================================================== POST /auth/forgot-password
@pytest.fixture
def forgot_backend(monkeypatch):
    """Nobody exists by default: the 404 path is the one an abuser walks."""
    from api import main
    lookups: list[str] = []

    def get_by_email(email: str):
        lookups.append(email)
        return None

    monkeypatch.setattr(users_repo, "get_by_email", get_by_email)
    # Never create a token or open an SMTP connection from a test.
    monkeypatch.setattr(main, "_send_reset_email", lambda user_id, email: None)
    return lookups


def _forgot(client: TestClient, email: str = "victim@example.test"):
    return client.post(FORGOT, json={"email": email})


@pytest.mark.integration
def test_forgot_password_permits_the_second_attempt_a_real_person_makes(forgot_backend, monkeypatch):
    """A person asks once, twice if the first mail is slow. Three is the budget."""
    client = _client()

    codes = [_forgot(client).status_code for _ in range(3)]

    assert codes == [404] * 3, "a real person's retries must not be throttled"


@pytest.mark.integration
def test_forgot_password_bounds_the_mail_bomb_at_three_an_hour(forgot_backend):
    client = _client()

    codes = [_forgot(client).status_code for _ in range(6)]

    assert codes[:3] == [404, 404, 404]
    assert codes[3:] == [429, 429, 429]


@pytest.mark.integration
def test_one_targets_budget_is_not_another_targets(forgot_backend, monkeypatch):
    """Keyed on the hashed address, so flooding one inbox cannot deny the reset
    mail to anybody else."""
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_IP_RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    client = _client()
    for _ in range(4):
        _forgot(client, "victim@example.test")

    assert _forgot(client, "victim@example.test").status_code == 429
    assert _forgot(client, "someone-else@example.test").status_code == 404


@pytest.mark.integration
def test_the_email_bucket_ignores_case_and_surrounding_space(forgot_backend, monkeypatch):
    """One inbox, one budget: otherwise ' Victim@Example.test ' is a fresh budget
    for the same mailbox, and the limit means nothing."""
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_IP_RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    client = _client()
    for _ in range(3):
        _forgot(client, "victim@example.test")

    assert _forgot(client, "  VICTIM@Example.TEST  ").status_code == 429


@pytest.mark.integration
def test_the_per_caller_forgot_bucket_catches_a_spread_of_addresses(forgot_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_IP_RATE_LIMIT_REQUESTS", 4)
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    client = _client()

    codes = [_forgot(client, f"target{i}@example.test").status_code for i in range(6)]

    assert codes == [404, 404, 404, 404, 429, 429]


@pytest.mark.integration
def test_the_deployment_wide_forgot_ceiling_bounds_total_smtp_volume(forgot_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_IP_RATE_LIMIT_REQUESTS", 100)
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_GLOBAL_RATE_LIMIT_REQUESTS", 3)

    codes = [_forgot(_client((f"203.0.113.{i}", 45000 + i)), f"t{i}@example.test").status_code
             for i in range(5)]

    assert codes == [404, 404, 404, 429, 429]


@pytest.mark.integration
def test_the_forgot_password_limit_expires(forgot_backend, rate_limit_clock):
    client = _client()
    for _ in range(3):
        _forgot(client)
    assert _forgot(client).status_code == 429

    rate_limit_clock.advance(rate_limit.FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS + 1)

    assert _forgot(client).status_code == 404


@pytest.mark.integration
def test_an_unregistered_address_is_charged_before_the_lookup(forgot_backend):
    """Charging only addresses that exist would make '429 rather than 404' the
    enumeration answer -- and a shed request must not query the database either.
    """
    client = _client()
    for _ in range(3):
        _forgot(client, "not-registered@example.test")
    lookups_before = len(forgot_backend)

    assert _forgot(client, "not-registered@example.test").status_code == 429
    assert len(forgot_backend) == lookups_before


@pytest.mark.integration
def test_a_registered_and_an_unregistered_address_get_the_same_429(forgot_backend, monkeypatch):
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_GLOBAL_RATE_LIMIT_REQUESTS", 1)
    client = _client()
    _forgot(client, "first@example.test")

    unknown = _forgot(client, "unknown@example.test")
    monkeypatch.setattr(users_repo, "get_by_email", lambda e: _user())
    known = _forgot(client, "budi@example.test")

    assert unknown.status_code == known.status_code == 429
    assert unknown.json() == known.json()


@pytest.mark.integration
def test_the_forgot_429_names_neither_the_bucket_nor_the_address(forgot_backend):
    client = _client()
    for _ in range(3):
        _forgot(client, "victim@example.test")

    r = _forgot(client, "victim@example.test")

    body = r.json()["detail"]
    assert "victim@example.test" not in body
    for leak in ("global", "ip", "address book", "bucket"):
        assert leak not in body.lower()
    assert r.headers["Retry-After"] == \
        str(int(rate_limit.FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS))


@pytest.mark.integration
def test_malformed_addresses_still_spend_the_budget(forgot_backend, monkeypatch):
    """The 422 for a missing '@' is decided after the limit, deliberately: junk
    input must not be a free way to walk the counters."""
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_IP_RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(rate_limit, "FORGOT_PASSWORD_GLOBAL_RATE_LIMIT_REQUESTS", 100)
    client = _client()

    codes = [_forgot(client, f"not-an-email-{i}").status_code for i in range(3)]

    assert codes == [422, 422, 422]
    assert _forgot(client, "victim@example.test").status_code == 429
