import time

import pytest

pytest.importorskip("bcrypt")
pytest.importorskip("jwt")

from api import security

TEST_SECRET = "unit-test-jwt-secret-0123456789abcdef"  # >= 32 chars


@pytest.mark.unit
def test_password_hash_and_verify():
    h = security.hash_password("secret123")
    assert h != "secret123"
    assert security.verify_password("secret123", h)
    assert not security.verify_password("wrong", h)


@pytest.mark.unit
def test_jwt_roundtrip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    tok = security.create_access_token("user-123")
    assert security.decode_access_token(tok) == "user-123"


@pytest.mark.unit
def test_jwt_invalid_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    import jwt as pyjwt
    with pytest.raises(pyjwt.PyJWTError):
        security.decode_access_token("not.a.jwt")


@pytest.mark.unit
@pytest.mark.parametrize("bad_secret", [
    "",                                        # unset/empty
    "short-secret",                            # < 32 chars
    "change-me-please-to-something-stronger",  # placeholder prefix
    "your-32-character-placeholder-secret",    # placeholder prefix
])
def test_weak_jwt_secret_rejected_for_encode_and_decode(monkeypatch, bad_secret):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    tok = security.create_access_token("user-123")

    monkeypatch.setenv("JWT_SECRET", bad_secret)
    with pytest.raises(RuntimeError):
        security.create_access_token("user-123")
    with pytest.raises(RuntimeError):
        security.decode_access_token(tok)
    with pytest.raises(RuntimeError):
        security.sign_state()
    assert not security.verify_state("nonce.0.sig")  # fail closed


@pytest.mark.unit
def test_state_sign_and_verify(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    s = security.sign_state()
    assert security.verify_state(s)
    assert not security.verify_state(s + "tamper")
    assert not security.verify_state("garbage")
    assert not security.verify_state("only.two")
    assert not security.verify_state(None)


@pytest.mark.unit
def test_state_expires_after_max_age(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    now = time.time()
    monkeypatch.setattr(security.time, "time", lambda: now - security.STATE_MAX_AGE_SECONDS - 1)
    stale = security.sign_state()
    monkeypatch.setattr(security.time, "time", lambda: now)
    assert not security.verify_state(stale)  # too old
    fresh = security.sign_state()
    assert security.verify_state(fresh)


@pytest.mark.unit
def test_state_with_tampered_timestamp_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    nonce, ts, sig = security.sign_state().split(".")
    assert not security.verify_state(f"{nonce}.{int(ts) + 999}.{sig}")  # ts not covered by sig
    assert not security.verify_state(f"{nonce}.not-a-number.{sig}")
