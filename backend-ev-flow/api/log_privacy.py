"""Coordinate masking for request logs (AC 2.3.2).

Some endpoints must keep taking coordinates as GET query parameters because the
shipped frontend calls them that way. uvicorn's access logger writes the full
request line verbatim, so without this filter a user's exact GPS fix lands in
plain text in the access log.

The filter rewrites `lat=` / `lon=` (and their long forms) in the logged request
line to a coarsened value. It only touches the log record — the handler still
receives the value the client sent, and rounds it itself before using it.
"""
from __future__ import annotations

import logging
import re

# 4 dp ~= 11 m: precise enough for a log line to stay useful for debugging,
# coarse enough not to be a personal location record.
LOG_COORD_PRECISION_DP = 4

_COORD_RE = re.compile(
    r"\b(lat|lon|lng|latitude|longitude|origin_lat|origin_lon|dest_lat|dest_lon)"
    r"=(-?\d+\.\d+)",
    re.IGNORECASE,
)


def mask_coordinates(text: str) -> str:
    """Return `text` with any coordinate-looking query parameter coarsened."""
    def _mask(m: re.Match) -> str:
        try:
            value = round(float(m.group(2)), LOG_COORD_PRECISION_DP)
        except ValueError:
            return f"{m.group(1)}=redacted"
        return f"{m.group(1)}={value}"

    return _COORD_RE.sub(_mask, text)


class CoordinateMaskingFilter(logging.Filter):
    """Coarsen coordinates in a log record before it is emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                mask_coordinates(a) if isinstance(a, str) else a for a in record.args
            )
        if isinstance(record.msg, str):
            record.msg = mask_coordinates(record.msg)
        return True


def install() -> None:
    """Attach the filter to uvicorn's access logger (idempotent)."""
    for name in ("uvicorn.access", "gunicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, CoordinateMaskingFilter) for f in logger.filters):
            logger.addFilter(CoordinateMaskingFilter())
