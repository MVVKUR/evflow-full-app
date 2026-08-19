"""The planner surface is not for drivers.

Every /planner/* route reads commercial siting intelligence: where the network is
weak, which coordinates score highest, what a site might earn. A driver account
reaching it would be an authorisation hole that returns 200 and therefore leaves
no trace in the logs to notice later.
"""
import pytest
from fastapi import HTTPException

from api.main import require_planner


def _user(account_type):
    return {"id": "u-1", "username": "someone", "account_type": account_type}


def test_business_planner_is_allowed():
    user = _user("business_planner")
    assert require_planner(user) is user


def test_driver_is_refused_with_403_not_401():
    # 401 would tell the client to log in again, which a driver would do
    # successfully and then hit the same wall. The account is authenticated; it
    # is simply not permitted, and 403 is what says so.
    with pytest.raises(HTTPException) as e:
        require_planner(_user("ev_user"))
    assert e.value.status_code == 403


def test_unknown_or_missing_account_type_is_refused():
    # Fail closed. A row written before account_type existed, or by a future
    # migration that adds a role, must not inherit planner access by silence.
    for value in ("fleet_operator", "", None):
        with pytest.raises(HTTPException) as e:
            require_planner(_user(value))
        assert e.value.status_code == 403

    with pytest.raises(HTTPException) as e:
        require_planner({"id": "u-2", "username": "no-type"})
    assert e.value.status_code == 403


def test_refusal_does_not_leak_what_the_surface_contains():
    with pytest.raises(HTTPException) as e:
        require_planner(_user("ev_user"))
    detail = str(e.value.detail).lower()
    assert "planner" in detail
    for leak in ("candidate", "score", "roi", "revenue", "grid"):
        assert leak not in detail
