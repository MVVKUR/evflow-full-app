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
from api.models import GeocodingItem, GeocodingSearchResponse, Station
from api.services.routing_service import haversine_distance_km


logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300.0
# Bounded so a hostile/no-op query stream cannot grow the process heap.
CACHE_MAX_ENTRIES = 512

# 4 dp ~= 11 m. Same precision api.main uses for the routing call "according to
# DMP (privacy and caching)"; keep the two consistent.
COORD_PRECISION_DP = 4
# Reverse geocoding is a "where is this person right now" lookup, so it is
# coarsened harder: 3 dp ~= 110 m, which is still street-level for a label.
REVERSE_COORD_PRECISION_DP = 3

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


def _cache_get(cache: OrderedDict, key: str):
    entry = cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.time() - ts >= CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    cache.move_to_end(key)
    return value


def _cache_put(cache: OrderedDict, key: str, value) -> None:
    cache[key] = (time.time(), value)
    cache.move_to_end(key)
    while len(cache) > CACHE_MAX_ENTRIES:
        cache.popitem(last=False)


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
    ) -> GeocodingSearchResponse:
        q_clean = query.strip().casefold()
        # Never keep the caller's full-precision position past this point.
        if origin_lat is not None:
            origin_lat = round_coord(origin_lat)
        if origin_lon is not None:
            origin_lon = round_coord(origin_lon)
        lat_str = f"{origin_lat:.2f}" if origin_lat is not None else "0"
        lon_str = f"{origin_lon:.2f}" if origin_lon is not None else "0"
        cache_key = f"{q_clean}:{lat_str}:{lon_str}:{limit}"

        cached_items = _cache_get(_CACHE, cache_key)
        if cached_items is not None:
            return GeocodingSearchResponse(query=query, items=cached_items)

        items: List[GeocodingItem] = []
        seen_labels = set()

        # 1. Search SPKLU stations first
        try:
            from api.stations_repo import list_stations
            _, station_rows = list_stations({"q": query}, limit=3, offset=0)
            for st in station_rows:
                st_lat = float(st["latitude"])
                st_lon = float(st["longitude"])

                dist_km = None
                if origin_lat is not None and origin_lon is not None:
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
                    dist_km = None
                    if origin_lat is not None and origin_lon is not None:
                        dist_km = round(haversine_distance_km(origin_lat, origin_lon, p_lat, p_lon), 1)

                    items.append(
                        GeocodingItem(
                            id=f"place-{place['label'].lower().replace(' ', '-')}",
                            label=place["label"],
                            subtitle=place["subtitle"],
                            latitude=p_lat,
                            longitude=p_lon,
                            distance_km=dist_km,
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
                                dist_km = None
                                if origin_lat is not None and origin_lon is not None:
                                    dist_km = round(haversine_distance_km(origin_lat, origin_lon, r_lat, r_lon), 1)

                                items.append(
                                    GeocodingItem(
                                        id=f"osm-{r.get('place_id', len(items))}",
                                        label=label,
                                        subtitle=subtitle,
                                        latitude=r_lat,
                                        longitude=r_lon,
                                        distance_km=dist_km,
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

        final_items = items[:limit]
        _cache_put(_CACHE, cache_key, final_items)
        return GeocodingSearchResponse(query=query, items=final_items)

    async def reverse_search(self, lat: float, lon: float) -> Dict[str, str]:
        """Reverse geocode lat/lon coordinates to a human-readable location name.

        The incoming position is coarsened immediately: everything downstream of
        this line (DB query, upstream call, cache key, fallback label, logs)
        sees only the rounded value.
        """
        lat = round_coord(lat, REVERSE_COORD_PRECISION_DP)
        lon = round_coord(lon, REVERSE_COORD_PRECISION_DP)

        cache_key = f"{lat}:{lon}"
        cached = _cache_get(_REVERSE_CACHE, cache_key)
        if cached is not None:
            return cached

        # 1. Check nearest station in DB within 1.5 km
        try:
            from api.stations_repo import nearby
            station_rows = nearby(lat, lon, radius_km=1.5, limit=1)
            if station_rows:
                st = station_rows[0]
                st_name = st.get("name") or "SPKLU Station"
                address = st.get("address") or st.get("city") or "Jakarta"
                return self._cache_reverse(cache_key, {
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
            return self._cache_reverse(cache_key, {
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
                        return self._cache_reverse(cache_key, {
                            "label": f"{road}, {city}", "address": data.get("display_name", ""), "city": city})
                    if city:
                        return self._cache_reverse(cache_key, {
                            "label": city, "address": data.get("display_name", ""), "city": city})
                else:
                    logger.warning("reverse geocoding: upstream returned HTTP %s", resp.status_code)
        except httpx.TimeoutException:
            logger.warning("reverse geocoding: upstream timed out")
        except Exception:
            logger.warning("reverse geocoding: upstream failed", exc_info=True)

        # Last-resort label. lat/lon here are already coarsened, and this string
        # is returned to the caller only — it is never logged.
        return self._cache_reverse(cache_key, {
            "label": f"Location ({lat:.{REVERSE_COORD_PRECISION_DP}f}, {lon:.{REVERSE_COORD_PRECISION_DP}f})",
            "address": "Indonesia",
            "city": "Indonesia",
        })

    @staticmethod
    def _cache_reverse(cache_key: str, result: Dict[str, str]) -> Dict[str, str]:
        _cache_put(_REVERSE_CACHE, cache_key, result)
        return result

