"""The one timezone this product reasons about.

EVFlow serves Jabodetabek, so every hour a user reads on a chart is a Jakarta
hour. The database does not agree by default: it runs Etc/UTC, and EXTRACT on a
timestamptz converts to the session TimeZone before pulling the field out. That
turned every bucket in station_hourly_occupancy into a UTC hour wearing a local
label, seven hours from the truth, which is why the peak-hours chart reported
22:00 to 02:00 as the busiest window in Jakarta and the morning commute as the
quietest.

The fix is applied in SQL, with AT TIME ZONE on the timestamptz before EXTRACT.
This module exists so the zone is named once, so Python-side code and the API
description agree with what the SQL does, and so the assumption that makes a
single conversion safe (Jakarta has no daylight saving) is pinned by a test
rather than remembered.

Changing the database's TimeZone setting instead was rejected: it would silently
alter every other timestamptz comparison in the application, including the ones
that are correct to reason in UTC.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

#: IANA zone for the served region. Passed verbatim to AT TIME ZONE in SQL.
BUSINESS_TIMEZONE = "Asia/Jakarta"

#: Western Indonesian Time is UTC+7 all year. Kept as a number for readability
#: in messages and tests; the conversion itself always goes through the zone.
UTC_OFFSET_HOURS = 7

_ZONE = ZoneInfo(BUSINESS_TIMEZONE)


def _local(instant: datetime) -> datetime:
    if instant.tzinfo is None:
        # Assuming UTC here is exactly how a seven hour error gets reintroduced
        # somewhere else, quietly, in a place nobody is looking at.
        raise ValueError("instant must carry a timezone; a naive datetime has no true local hour")
    return instant.astimezone(_ZONE)


def local_hour(instant: datetime) -> int:
    """Hour 0 to 23 as lived in Jakarta. Mirrors EXTRACT(HOUR FROM ts AT TIME ZONE ...)."""
    return _local(instant).hour


def local_isodow(instant: datetime) -> int:
    """ISO weekday 1 (Monday) to 7 (Sunday) as lived in Jakarta."""
    return _local(instant).isoweekday()
