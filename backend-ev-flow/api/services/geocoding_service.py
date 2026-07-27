"""Geocoding search proxy service for EV-FLOW (Epic 2.0).

Merges SPKLU charging stations and place search results, biased to Indonesia/Java.

Privacy / abuse notes (AC 2.3.2 + Nominatim usage policy):
  * Coordinates are rounded to COORD_PRECISION_DP before they leave this process
    (upstream call, cache key) and NOTHING here ever logs a raw coordinate.
  * Every outbound call carries an explicit timeout and a descriptive
    User-Agent with a contact address (NOMINATIM_CONTACT_EMAIL).
  * Results are cached in a bounded LRU so repeated lookups do not hit
    Nominatim. Upstream failure degrades to local data, never to a traceback.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import httpx
from api.models import (
    DISTANCE_FROM_ORIGIN,
    DISTANCE_FROM_REFERENCE_POINT,
    GeocodingItem,
    GeocodingSearchResponse,
    ServiceAreaSummary,
    Station,
)
from api.services import service_area
from api.services.routing_service import haversine_distance_km


logger = logging.getLogger(__name__)

# The query-keyed cache: its key is a place NAME plus a ~1.1 km origin bucket.
CACHE_TTL_SECONDS = float(os.getenv("GEOCODING_SEARCH_CACHE_TTL_SECONDS", "300.0"))

# AC 2.3.3: temporary route history must be gone within 30 seconds. The reverse
# cache is keyed on the CALLER'S OWN POSITION, so it is the one store in this
# process that holds a location record; it gets its own, much shorter window.
# 300 s (the search TTL) is ten times the budget the AC allows.
REVERSE_CACHE_TTL_SECONDS = float(os.getenv("GEOCODING_REVERSE_CACHE_TTL_SECONDS", "30.0"))

# How long the background sweeper is allowed to sleep when NOTHING is cached.
# When something is cached it sleeps only until that entry's deadline instead,
# so the TTL above is an actual bound rather than a polling approximation.
CACHE_SWEEP_IDLE_POLL_SECONDS = float(
    os.getenv("GEOCODING_CACHE_SWEEP_IDLE_POLL_SECONDS", "5.0"))

# Bounded so a hostile/no-op query stream cannot grow the process heap.
CACHE_MAX_ENTRIES = 512

# How many route sessions may be indexed for targeted deletion at once. The
# index maps route_plan_id -> reverse-cache keys, and those keys ARE coarsened
# positions, so it is pruned on exactly the same deadline as the cache itself.
SESSION_INDEX_MAX_SESSIONS = 512

# 4 dp ~= 11 m. Same precision api.main uses for the routing call "according to
# DMP (privacy and caching)"; keep the two consistent.
COORD_PRECISION_DP = 4
# Reverse geocoding is a "where is this person right now" lookup, so it is
# coarsened harder: 3 dp ~= 110 m, which is still street-level for a label.
REVERSE_COORD_PRECISION_DP = 3

# AC 2.2.7 wants "estimated distances" on every suggestion. Distances used to be
# conditional on the CLIENT passing lat/lon, so a first-launch or
# permission-denied session (exactly the AC 2.2.8 no-GPS case) got a picker with
# names and nothing else. When no origin of any kind is available the distance is
# measured from this documented reference point instead, and the item says so via
# `distance_from` -- a labelled estimate beats a bare null.
FALLBACK_ORIGIN_LAT = float(os.getenv("GEOCODING_FALLBACK_ORIGIN_LAT",
                                      os.getenv("JAKARTA_CENTER_LAT", "-6.2088")))
FALLBACK_ORIGIN_LON = float(os.getenv("GEOCODING_FALLBACK_ORIGIN_LON",
                                      os.getenv("JAKARTA_CENTER_LON", "106.8456")))
FALLBACK_ORIGIN_LABEL = os.getenv("GEOCODING_FALLBACK_ORIGIN_LABEL", "Jakarta")

NOMINATIM_BASE_URL = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").rstrip("/")
NOMINATIM_TIMEOUT_SECONDS = 4.0
NOMINATIM_REVERSE_TIMEOUT_SECONDS = 2.5

# Nominatim's usage policy requires an identifiable app name AND a contact
# address; an anonymous UA is itself grounds for a block. The fallback is a
# role address, never a real person's, and deployments override it.
DEFAULT_NOMINATIM_CONTACT = "ops@evflow.example"


def _nominatim_user_agent() -> str:
    contact = (os.getenv("NOMINATIM_CONTACT_EMAIL", "") or "").strip() or DEFAULT_NOMINATIM_CONTACT
    return f"EVFLOW-RoutePlanner/2.0 (+{contact})"


# Nominatim's usage policy allows about one request per second per application.
# The endpoint rate limits cap what callers may ask of us; this caps what we
# actually send upstream, which is the number OpenStreetMap measures when it
# decides to ban an IP. Requests are spaced rather than rejected, so a burst
# that survives the endpoint limits is slowed instead of failing.
NOMINATIM_MIN_INTERVAL_SECONDS = float(os.getenv("NOMINATIM_MIN_INTERVAL_SECONDS", "1.0"))

_upstream_lock = asyncio.Lock()
_last_upstream_call = 0.0


async def _await_upstream_slot() -> None:
    """Space outbound Nominatim calls by at least NOMINATIM_MIN_INTERVAL_SECONDS."""
    global _last_upstream_call
    async with _upstream_lock:
        wait = NOMINATIM_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_upstream_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_upstream_call = time.monotonic()


def round_coord(value: float, dp: int = COORD_PRECISION_DP) -> float:
    """Coarsen a coordinate before it is sent upstream, cached, or logged."""
    return round(float(value), dp)


_CACHE: "OrderedDict[str, Tuple[float, List[GeocodingItem]]]" = OrderedDict()
_REVERSE_CACHE: "OrderedDict[str, Tuple[float, Dict[str, str]]]" = OrderedDict()

# route_plan_id -> the reverse-cache keys that session created. This is what
# makes "the session ended, delete ITS location data" (AC 2.3.3) targetable: the
# reverse cache is keyed on a coarsened position, so without this index the
# DELETE endpoint has no way to tell one caller's entries from another's and can
# only drop entries that already expired -- i.e. exactly the wrong ones.
_SESSION_KEYS: "OrderedDict[str, set]" = OrderedDict()


def _sweep(cache: OrderedDict, ttl: float, now: Optional[float] = None) -> int:
    """Drop every expired entry. Returns how many were removed."""
    now = time.time() if now is None else now
    stale = [k for k, (ts, _) in cache.items() if now - ts >= ttl]
    for k in stale:
        cache.pop(k, None)
    return len(stale)


def _prune_session_index() -> None:
    """Forget indexed keys whose cache entry is gone, and sessions left empty.

    The index maps a session to coarsened positions, so it is itself a location
    record: it must never outlive the entries it points at.
    """
    live = set(_REVERSE_CACHE)
    for session_id in list(_SESSION_KEYS):
        remaining = _SESSION_KEYS[session_id] & live
        if remaining:
            _SESSION_KEYS[session_id] = remaining
        else:
            _SESSION_KEYS.pop(session_id, None)


def _remember_session_key(session_id: Optional[str], key: str) -> None:
    if not session_id:
        return
    _SESSION_KEYS.setdefault(session_id, set()).add(key)
    _SESSION_KEYS.move_to_end(session_id)
    while len(_SESSION_KEYS) > SESSION_INDEX_MAX_SESSIONS:
        _SESSION_KEYS.popitem(last=False)


def _cache_get(cache: OrderedDict, key: str, ttl: float = CACHE_TTL_SECONDS):
    entry = cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.time() - ts >= ttl:
        cache.pop(key, None)
        return None
    cache.move_to_end(key)
    return value


def _cache_put(cache: OrderedDict, key: str, value, ttl: float = CACHE_TTL_SECONDS) -> None:
    _sweep(cache, ttl)
    cache[key] = (time.time(), value)
    cache.move_to_end(key)
    while len(cache) > CACHE_MAX_ENTRIES:
        cache.popitem(last=False)


def purge_expired(now: Optional[float] = None) -> int:
    """Sweep both caches with their own TTLs. Returns how many entries went."""
    now = time.time() if now is None else now
    dropped = (_sweep(_CACHE, CACHE_TTL_SECONDS, now)
               + _sweep(_REVERSE_CACHE, REVERSE_CACHE_TTL_SECONDS, now))
    _prune_session_index()
    return dropped


def purge_session(session_id: Optional[str]) -> int:
    """Delete the location data THIS session created (AC 2.3.3's "session ends").

    Unlike :func:`purge_expired`, which can only drop entries that already timed
    out, this removes the caller's own still-live entries -- the ones the AC is
    actually about. Returns how many reverse-cache entries were removed.
    """
    if not session_id:
        return 0
    keys = _SESSION_KEYS.pop(session_id, set())
    dropped = 0
    for key in keys:
        if _REVERSE_CACHE.pop(key, None) is not None:
            dropped += 1
    _prune_session_index()
    return dropped


def seconds_until_next_expiry(now: Optional[float] = None) -> float:
    """Seconds until the earliest cached entry is due to be deleted.

    Clamped to ``CACHE_SWEEP_IDLE_POLL_SECONDS`` so the sweeper still wakes on an
    empty process, and floored at 0 so an already-overdue entry sweeps at once.
    """
    now = time.time() if now is None else now
    deadlines = [ts + CACHE_TTL_SECONDS for ts, _ in _CACHE.values()]
    deadlines += [ts + REVERSE_CACHE_TTL_SECONDS for ts, _ in _REVERSE_CACHE.values()]
    if not deadlines:
        return CACHE_SWEEP_IDLE_POLL_SECONDS
    return max(0.0, min(min(deadlines) - now, CACHE_SWEEP_IDLE_POLL_SECONDS))


async def sweep_forever(sleep=None) -> None:
    """Enforce the TTLs on a process that receives no traffic at all (AC 2.3.3).

    Expiry used to run only inside ``_cache_put``, so when nobody performed
    another reverse lookup an entry outlived its TTL indefinitely and the
    30-second bound was not a bound. This task sleeps until the NEXT entry is
    due -- never longer than ``CACHE_SWEEP_IDLE_POLL_SECONDS`` -- and then
    purges, so the deadline holds whether or not the API is ever called again.

    ``sleep`` is injectable so a test can advance a clock instead of waiting.
    """
    _sleep = asyncio.sleep if sleep is None else sleep
    while True:
        await _sleep(seconds_until_next_expiry())
        purge_expired()


_sweeper_task: "Optional[asyncio.Task]" = None


def start_sweeper() -> "asyncio.Task":
    """Start :func:`sweep_forever` on the running loop. Idempotent.

    The app lifespan calls this. It is a named function rather than an inline
    ``create_task`` so a test can assert the guarantee is actually WIRED UP, not
    merely defined -- the same failure mode that once left coordinate masking
    declared but never attached.
    """
    global _sweeper_task
    if _sweeper_task is None or _sweeper_task.done():
        _sweeper_task = asyncio.create_task(sweep_forever(), name="geocoding-cache-sweeper")
    return _sweeper_task


def sweeper_is_running() -> bool:
    return _sweeper_task is not None and not _sweeper_task.done()


async def stop_sweeper() -> None:
    """Cancel the sweeper and wait for it, so shutdown leaves no pending task."""
    global _sweeper_task
    task, _sweeper_task = _sweeper_task, None
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


KNOWN_INDONESIA_PLACES = [
    {"label": "Sudirman (Jl. Jend. Sudirman)", "subtitle": "Jakarta Pusat · Central Business District", "latitude": -6.2163, "longitude": 106.8188},
    {"label": "Thamrin (Jl. M.H. Thamrin)", "subtitle": "Jakarta Pusat · Commercial Corridor", "latitude": -6.1930, "longitude": 106.8230},
    {"label": "Gatot Subroto", "subtitle": "Jakarta Selatan · Main Arterial Road", "latitude": -6.2300, "longitude": 106.8150},
    {"label": "Kuningan (HR Rasuna Said)", "subtitle": "Jakarta Selatan · Embassy District", "latitude": -6.2240, "longitude": 106.8320},
    {"label": "Senayan (GBK Sports Complex)", "subtitle": "Jakarta Pusat · Landmark & Stadium", "latitude": -6.2185, "longitude": 106.8026},
    {"label": "Taman Mini Indonesia Indah (TMII)", "subtitle": "Jakarta Timur · Cultural Park", "latitude": -6.3024, "longitude": 106.8952},
    {"label": "Pondok Indah", "subtitle": "Jakarta Selatan · Residential & Mall", "latitude": -6.2650, "longitude": 106.7840},
    {"label": "Kelapa Gading", "subtitle": "Jakarta Utara · Commercial District", "latitude": -6.1580, "longitude": 106.9080},
    {"label": "PIK (Pantai Indah Kapuk)", "subtitle": "Jakarta Utara · Coastal Boulevard", "latitude": -6.1110, "longitude": 106.7380},
    {"label": "BSD City (Bumi Serpong Damai)", "subtitle": "Tangerang Selatan · Banten", "latitude": -6.3000, "longitude": 106.6500},
    {"label": "Bandara Soekarno-Hatta (CGK)", "subtitle": "Tangerang · International Airport", "latitude": -6.1275, "longitude": 106.6537},
    {"label": "Bandung", "subtitle": "West Java · via Tol Cipularang", "latitude": -6.9175, "longitude": 107.6191},
    {"label": "Bogor", "subtitle": "West Java · via Tol Jagorawi", "latitude": -6.5971, "longitude": 106.7996},
    {"label": "Bekasi", "subtitle": "West Java · via Tol Jakarta-Cikampek", "latitude": -6.2383, "longitude": 106.9756},
    {"label": "Depok", "subtitle": "West Java · via Tol Desari", "latitude": -6.4025, "longitude": 106.7942},
    {"label": "Semarang", "subtitle": "Central Java · via Tol Trans-Jawa", "latitude": -6.9667, "longitude": 110.4167},
    {"label": "Surabaya", "subtitle": "East Java · via Tol Trans-Jawa", "latitude": -7.2575, "longitude": 112.7521},
    {"label": "Yogyakarta", "subtitle": "DI Yogyakarta · Special Region", "latitude": -7.7956, "longitude": 110.3695},
    {"label": "Jakarta Pusat", "subtitle": "DKI Jakarta · City Center", "latitude": -6.1805, "longitude": 106.8284},
    {"label": "Monas (Monumen Nasional)", "subtitle": "Jakarta Pusat · Landmark", "latitude": -6.1754, "longitude": 106.8272},
    {"label": "SPKLU Rest Area KM 57", "subtitle": "Tol Jakarta-Cikampek · Fast Charging", "latitude": -6.3780, "longitude": 107.2840},
    {"label": "SPKLU Rest Area KM 88", "subtitle": "Tol Cipularang · Ultra Fast Charging", "latitude": -6.6540, "longitude": 107.4380},
]



class GeocodingService:
    """Geocoding proxy searching SPKLU stations and places."""

    async def search(
        self,
        query: str,
        origin_lat: Optional[float] = None,
        origin_lon: Optional[float] = None,
        limit: int = 5,
        in_service_area_only: bool = False,
    ) -> GeocodingSearchResponse:
        """Destination suggestions, each tagged with whether the planner accepts it.

        ``in_service_area_only`` drops suggestions the planner would 422 instead
        of merely labelling them, for a picker that would rather show nothing
        than show something un-routable.
        """
        q_clean = query.strip().casefold()
        # Never keep the caller's full-precision position past this point.
        if origin_lat is not None:
            origin_lat = round_coord(origin_lat)
        if origin_lon is not None:
            origin_lon = round_coord(origin_lon)

        # AC 2.2.7: every suggestion carries an estimated distance, even when the
        # caller has no fix yet. Fall back to the configured reference point and
        # SAY SO, rather than returning a bare null the picker cannot render.
        distance_from = DISTANCE_FROM_ORIGIN
        reference_label: Optional[str] = None
        if origin_lat is None or origin_lon is None:
            origin_lat = round_coord(FALLBACK_ORIGIN_LAT)
            origin_lon = round_coord(FALLBACK_ORIGIN_LON)
            distance_from = DISTANCE_FROM_REFERENCE_POINT
            reference_label = FALLBACK_ORIGIN_LABEL

        lat_str = f"{origin_lat:.2f}"
        lon_str = f"{origin_lon:.2f}"
        # The service-area flag is part of the key: the two variants return
        # different item sets, and the boundary is reconfigurable at runtime.
        cache_key = (f"{q_clean}:{lat_str}:{lon_str}:{distance_from}:{limit}"
                     f":{int(bool(in_service_area_only))}")

        cached = _cache_get(_CACHE, cache_key)
        if cached is not None:
            cached_items, cached_filtered = cached
            return self._response(query, cached_items, distance_from,
                                  reference_label, cached_filtered)

        items: List[GeocodingItem] = []
        seen_labels = set()

        # 1. Search SPKLU stations first
        try:
            from api.stations_repo import list_stations
            _, station_rows = list_stations({"q": query}, limit=3, offset=0)
            for st in station_rows:
                st_lat = float(st["latitude"])
                st_lon = float(st["longitude"])

                dist_km = round(haversine_distance_km(origin_lat, origin_lon, st_lat, st_lon), 1)

                st_name = st.get("name") or "SPKLU Station"
                address = st.get("address") or st.get("city") or "Charging Station"
                subtitle = f"Charging station · {address}"

                station_model = Station(
                    id=st["id"],
                    name=st_name,
                    sources=st.get("sources") or [],
                    latitude=st_lat,
                    longitude=st_lon,
                    address=st.get("address"),
                    province=st.get("province"),
                    city=st.get("city"),
                    operator=st.get("operator") or "PLN",
                    power_kw=float(st.get("power_kw") or 50.0),
                    charge_type=st.get("charge_type") or "fast",
                    speed_tier=st.get("speed_tier") or "fast",
                    connectors=st.get("connectors") or [],
                    connector_types=st.get("connector_types") or ["CCS2"],
                    connector_inferred=st.get("connector_inferred", True),
                    status=st.get("status") or "operational",
                    date_verified=st.get("date_verified"),
                    distance_km=dist_km,
                )

                item = GeocodingItem(
                    id=f"station-{st['id']}",
                    label=st_name,
                    subtitle=subtitle,
                    latitude=st_lat,
                    longitude=st_lon,
                    distance_km=dist_km,
                    distance_from=distance_from,
                    distance_reference_label=reference_label,
                    type="station",
                    station=station_model,
                    attribution="PLN SPKLU, OpenChargeMap",
                )
                items.append(item)
                seen_labels.add(st_name.casefold())
        except Exception:
            logger.warning("geocoding: station lookup failed", exc_info=True)

        # 2. Search known local places
        for place in KNOWN_INDONESIA_PLACES:
            if q_clean in place["label"].casefold() or place["label"].casefold() in q_clean:
                if place["label"].casefold() not in seen_labels:
                    p_lat = place["latitude"]
                    p_lon = place["longitude"]
                    dist_km = round(haversine_distance_km(origin_lat, origin_lon, p_lat, p_lon), 1)

                    items.append(
                        GeocodingItem(
                            id=f"place-{place['label'].lower().replace(' ', '-')}",
                            label=place["label"],
                            subtitle=place["subtitle"],
                            latitude=p_lat,
                            longitude=p_lon,
                            distance_km=dist_km,
                            distance_from=distance_from,
                            distance_reference_label=reference_label,
                            type="place",
                            station=None,
                            attribution="OpenStreetMap contributors",
                        )
                    )
                    seen_labels.add(place["label"].casefold())

        # 3. Attempt Nominatim open geocoder call if items < limit

        if len(items) < limit:
            try:
                params = {"q": query, "countrycodes": "id", "format": "json", "limit": str(limit)}
                await _await_upstream_slot()
                async with httpx.AsyncClient(timeout=NOMINATIM_TIMEOUT_SECONDS) as client:
                    resp = await client.get(
                        f"{NOMINATIM_BASE_URL}/search",
                        params=params,
                        headers={"User-Agent": _nominatim_user_agent()},
                    )

                    if resp.status_code == 200:
                        results = resp.json()
                        for r in results:
                            display_name = r.get("display_name", "")
                            parts = [p.strip() for p in display_name.split(",")]
                            label = parts[0] if parts else query
                            subtitle = ", ".join(parts[1:3]) if len(parts) > 1 else "Indonesia"

                            if label.casefold() not in seen_labels:
                                r_lat = float(r["lat"])
                                r_lon = float(r["lon"])
                                dist_km = round(
                                    haversine_distance_km(origin_lat, origin_lon, r_lat, r_lon), 1)

                                items.append(
                                    GeocodingItem(
                                        id=f"osm-{r.get('place_id', len(items))}",
                                        label=label,
                                        subtitle=subtitle,
                                        latitude=r_lat,
                                        longitude=r_lon,
                                        distance_km=dist_km,
                                        distance_from=distance_from,
                                        distance_reference_label=reference_label,
                                        type="place",
                                        station=None,
                                        attribution="OpenStreetMap contributors",
                                    )
                                )
                                seen_labels.add(label.casefold())
                    else:
                        logger.warning("geocoding: upstream search returned HTTP %s", resp.status_code)
            except httpx.TimeoutException:
                # Degrade to local results; the caller still gets a 200 with
                # whatever stations/places matched.
                logger.warning("geocoding: upstream search timed out")
            except Exception:
                logger.warning("geocoding: upstream search failed", exc_info=True)

        # Drop the un-routable suggestions BEFORE truncating, so asking for 5
        # in-area results does not silently return 2 because three out-of-area
        # matches took the slots.
        filtered_out = 0
        if in_service_area_only:
            kept = [i for i in items if i.in_service_area]
            filtered_out = len(items) - len(kept)
            items = kept

        final_items = items[:limit]
        _cache_put(_CACHE, cache_key, (final_items, filtered_out))
        return self._response(query, final_items, distance_from, reference_label, filtered_out)

    @staticmethod
    def _response(query: str, items: List[GeocodingItem], distance_from: str,
                  reference_label: Optional[str], filtered_out: int) -> GeocodingSearchResponse:
        """Always echo the service area the items were judged against (AC 2.2.1).

        Without it the picker can see `in_service_area: false` but cannot tell
        the user WHERE the app does work, which is the only actionable half.
        """
        return GeocodingSearchResponse(
            query=query,
            items=items,
            distance_from=distance_from,
            distance_reference_label=reference_label,
            service_area=ServiceAreaSummary(**service_area.describe()),
            filtered_out_of_service_area=filtered_out,
        )

    async def reverse_search(self, lat: float, lon: float,
                             session_id: Optional[str] = None) -> Dict[str, str]:
        """Reverse geocode lat/lon coordinates to a human-readable location name.

        The incoming position is coarsened immediately: everything downstream of
        this line (DB query, upstream call, cache key, fallback label, logs)
        sees only the rounded value.

        ``session_id`` (the driver's ``route_plan_id``) tags whatever gets cached
        so ``DELETE /api/v1/route-plans/{route_plan_id}`` can delete exactly this
        session's entries when the trip ends (AC 2.3.3). The cache KEY stays
        position-only, so sessions still share hits; only the deletion index is
        per-session.
        """
        lat = round_coord(lat, REVERSE_COORD_PRECISION_DP)
        lon = round_coord(lon, REVERSE_COORD_PRECISION_DP)

        cache_key = f"{lat}:{lon}"
        cached = _cache_get(_REVERSE_CACHE, cache_key, REVERSE_CACHE_TTL_SECONDS)
        if cached is not None:
            # A cache HIT is still this session touching this position, so it
            # must be deletable when the session ends.
            _remember_session_key(session_id, cache_key)
            return cached

        # 1. Check nearest station in DB within 1.5 km
        try:
            from api.stations_repo import nearby
            station_rows = nearby(lat, lon, radius_km=1.5, limit=1)
            if station_rows:
                st = station_rows[0]
                st_name = st.get("name") or "SPKLU Station"
                address = st.get("address") or st.get("city") or "Jakarta"
                return self._cache_reverse(cache_key, session_id, {
                    "label": f"Near {st_name}",
                    "address": address,
                    "city": st.get("city") or "Jakarta",
                })
        except Exception:
            logger.warning("reverse geocoding: station lookup failed", exc_info=True)

        # 2. Check nearest known local place
        closest_place = None
        min_d = 999.0
        for p in KNOWN_INDONESIA_PLACES:
            d = haversine_distance_km(lat, lon, p["latitude"], p["longitude"])
            if d < min_d:
                min_d = d
                closest_place = p

        if closest_place and min_d < 15.0:
            return self._cache_reverse(cache_key, session_id, {
                "label": closest_place["label"],
                "address": closest_place["subtitle"],
                "city": closest_place["label"],
            })

        # 3. Nominatim reverse geocoding API fallback (rounded coords only)
        try:
            params = {"lat": str(lat), "lon": str(lon), "format": "json", "zoom": "16"}
            await _await_upstream_slot()
            async with httpx.AsyncClient(timeout=NOMINATIM_REVERSE_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    f"{NOMINATIM_BASE_URL}/reverse",
                    params=params,
                    headers={"User-Agent": _nominatim_user_agent()},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    address_dict = data.get("address", {})
                    road = address_dict.get("road") or address_dict.get("suburb") or address_dict.get("neighbourhood")
                    city = address_dict.get("city") or address_dict.get("town") or address_dict.get("city_district") or "Jakarta"
                    if road:
                        return self._cache_reverse(cache_key, session_id, {
                            "label": f"{road}, {city}", "address": data.get("display_name", ""), "city": city})
                    if city:
                        return self._cache_reverse(cache_key, session_id, {
                            "label": city, "address": data.get("display_name", ""), "city": city})
                else:
                    logger.warning("reverse geocoding: upstream returned HTTP %s", resp.status_code)
        except httpx.TimeoutException:
            logger.warning("reverse geocoding: upstream timed out")
        except Exception:
            logger.warning("reverse geocoding: upstream failed", exc_info=True)

        # Last-resort label. lat/lon here are already coarsened, and this string
        # is returned to the caller only — it is never logged.
        return self._cache_reverse(cache_key, session_id, {
            "label": f"Location ({lat:.{REVERSE_COORD_PRECISION_DP}f}, {lon:.{REVERSE_COORD_PRECISION_DP}f})",
            "address": "Indonesia",
            "city": "Indonesia",
        })

    @staticmethod
    def _cache_reverse(cache_key: str, session_id: Optional[str],
                       result: Dict[str, str]) -> Dict[str, str]:
        # Position-keyed: never held longer than the AC 2.3.3 window, and tagged
        # to the route session so ending the trip can delete it immediately.
        _cache_put(_REVERSE_CACHE, cache_key, result, REVERSE_CACHE_TTL_SECONDS)
        _remember_session_key(session_id, cache_key)
        return result

