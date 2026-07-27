"""Tiny in-process, per-caller rate limiter.

Deliberately minimal: a sliding window of request timestamps per key, held in
this worker's memory. It is not a distributed limiter — with several uvicorn
workers the effective limit is (workers x limit). That is fine for its purpose,
which is stopping one authenticated account from looping an endpoint that
proxies a third-party service (Nominatim) hard enough to get our egress IP
banned. Anything stronger belongs at the nginx/edge layer.
"""
from __future__ import annotations

import time
from collections import OrderedDict, deque
from typing import Deque

# Geocoding proxies OpenStreetMap's Nominatim, whose usage policy allows about
# 1 request/second per application. A human typing in the destination picker
# stays far below this; a script does not.
GEOCODING_RATE_LIMIT_REQUESTS = 30
GEOCODING_RATE_LIMIT_WINDOW_SECONDS = 60.0

# Ceiling for the whole deployment, not one caller. The per-caller budget above
# stops a single client looping; this stops many clients (or many demo accounts,
# since the demo password is public by design) from adding up to a volume that
# gets our egress IP banned. Nominatim's policy is ~1 request/second, and the
# response cache absorbs most repeats, so 60/minute leaves real headroom.
GEOCODING_GLOBAL_RATE_LIMIT_REQUESTS = 60

# Cap on distinct keys tracked, so the limiter itself cannot be used to grow
# the heap. Oldest-touched key is evicted first.
MAX_TRACKED_KEYS = 4096

_HITS: "OrderedDict[str, Deque[float]]" = OrderedDict()


def allow(key: str, limit: int, window_seconds: float) -> bool:
    """Record a hit for `key`; return False when it exceeds `limit` per window."""
    now = time.monotonic()
    hits = _HITS.get(key)
    if hits is None:
        hits = deque()
        _HITS[key] = hits
    _HITS.move_to_end(key)

    cutoff = now - window_seconds
    while hits and hits[0] <= cutoff:
        hits.popleft()

    while len(_HITS) > MAX_TRACKED_KEYS:
        _HITS.popitem(last=False)

    if len(hits) >= limit:
        return False
    hits.append(now)
    return True


def reset() -> None:
    """Drop all counters. Test helper — not used by request handling."""
    _HITS.clear()
