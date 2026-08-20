"""The hour a chart shows has to be the hour a driver in Jakarta lived through.

charging_sessions.created_at is timestamptz, and EXTRACT on a timestamptz
converts to the session's TimeZone setting first. The production database runs
Etc/UTC, so every hour bucket in station_hourly_occupancy was seven hours away
from the local hour it claimed to be: the peak-hours chart reported 22:00 to
02:00 as the busiest time in Jabodetabek and the morning commute as the
quietest.

These tests pin the conversion the SQL now performs. The last one is the reason
a fixed offset would have been acceptable and a named zone is still better.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from api.services.local_time import (
    BUSINESS_TIMEZONE,
    UTC_OFFSET_HOURS,
    local_hour,
    local_isodow,
)


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_the_zone_is_a_real_iana_name():
    # The SQL passes this string to AT TIME ZONE, where an unknown name is a
    # runtime error inside a stored procedure rather than a startup failure.
    assert ZoneInfo(BUSINESS_TIMEZONE) is not None


def test_midday_utc_is_evening_in_jakarta():
    assert local_hour(_utc(2026, 8, 20, 12)) == 19


def test_the_morning_commute_is_not_the_middle_of_the_night():
    # 07:00 UTC is 14:00 in Jakarta. Reporting it as hour 7 is what made the
    # chart claim the afternoon rush happened at breakfast.
    assert local_hour(_utc(2026, 8, 20, 7)) == 14


def test_the_day_rolls_over_before_utc_does():
    # 19:00 Sunday UTC is already 02:00 Monday in Jakarta, so bucketing by UTC
    # files Monday's small hours under Sunday and skews the weekend curve too.
    sunday_evening_utc = _utc(2026, 8, 16, 19)
    assert sunday_evening_utc.isoweekday() == 7
    assert local_isodow(sunday_evening_utc) == 1
    assert local_hour(sunday_evening_utc) == 2


def test_the_offset_holds_at_seven_hours():
    assert UTC_OFFSET_HOURS == 7
    assert local_hour(_utc(2026, 1, 1, 0)) == 7


def test_jakarta_never_observes_daylight_saving():
    # This is what lets one named zone stand in for the whole year. If the
    # offset moved, every hour bucket either side of a transition would be
    # comparing different local hours under the same label, and the fix would
    # need per-date handling rather than a single AT TIME ZONE.
    zone = ZoneInfo(BUSINESS_TIMEZONE)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for day in range(0, 366, 7):
        moment = start + timedelta(days=day)
        assert moment.astimezone(zone).utcoffset() == timedelta(hours=UTC_OFFSET_HOURS), moment


def test_conversion_is_stable_across_the_whole_day():
    for hour in range(24):
        assert local_hour(_utc(2026, 6, 15, hour)) == (hour + UTC_OFFSET_HOURS) % 24


def test_a_naive_timestamp_is_refused_rather_than_assumed():
    # Guessing that a naive datetime meant UTC is how a seven hour error gets
    # reintroduced somewhere else.
    import pytest
    with pytest.raises(ValueError, match="timezone"):
        local_hour(datetime(2026, 8, 20, 12))
