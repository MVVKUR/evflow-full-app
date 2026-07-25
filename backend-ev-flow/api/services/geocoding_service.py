"""Geocoding search proxy service for EV-FLOW (Epic 2.0).

Merges SPKLU charging stations and place search results, biased to Indonesia/Java.
Uses 5-minute in-memory caching for non-sensitive geocoding queries.
"""
from __future__ import annotations

import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from api.models import GeocodingItem, GeocodingSearchResponse, Station
from api.services.routing_service import haversine_distance_km


_CACHE: Dict[str, Tuple[float, List[GeocodingItem]]] = {}

CACHE_TTL_SECONDS = 300.0


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
        lat_str = f"{origin_lat:.2f}" if origin_lat is not None else "0"
        lon_str = f"{origin_lon:.2f}" if origin_lon is not None else "0"
        cache_key = f"{q_clean}:{lat_str}:{lon_str}:{limit}"


        now = time.time()
        if cache_key in _CACHE:
            ts, cached_items = _CACHE[cache_key]
            if now - ts < CACHE_TTL_SECONDS:
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
            pass

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
                encoded_q = urllib.parse.quote(query)
                async with httpx.AsyncClient(timeout=4.0) as client:
                    url = f"https://nominatim.openstreetmap.org/search?q={encoded_q}&countrycodes=id&format=json&limit={limit}"
                    headers = {"User-Agent": "EVFLOW-RoutePlanner/2.0"}
                    resp = await client.get(url, headers=headers)

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
            except Exception:
                pass

        final_items = items[:limit]
        _CACHE[cache_key] = (now, final_items)
        return GeocodingSearchResponse(query=query, items=final_items)

    async def reverse_search(self, lat: float, lon: float) -> Dict[str, str]:
        """Reverse geocode lat/lon coordinates to a human-readable location name."""
        # 1. Check nearest station in DB within 1.5 km
        try:
            from api.stations_repo import nearby
            station_rows = nearby(lat, lon, radius_km=1.5, limit=1)
            if station_rows:
                st = station_rows[0]
                st_name = st.get("name") or "SPKLU Station"
                address = st.get("address") or st.get("city") or "Jakarta"
                return {
                    "label": f"Near {st_name}",
                    "address": address,
                    "city": st.get("city") or "Jakarta",
                }
        except Exception:
            pass

        # 2. Check nearest known local place
        closest_place = None
        min_d = 999.0
        for p in KNOWN_INDONESIA_PLACES:
            d = haversine_distance_km(lat, lon, p["latitude"], p["longitude"])
            if d < min_d:
                min_d = d
                closest_place = p

        if closest_place and min_d < 15.0:
            return {
                "label": closest_place["label"],
                "address": closest_place["subtitle"],
                "city": closest_place["label"],
            }

        # 3. Nominatim reverse geocoding API fallback
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=16"
                headers = {"User-Agent": "EVFLOW-RoutePlanner/2.0"}
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    address_dict = data.get("address", {})
                    road = address_dict.get("road") or address_dict.get("suburb") or address_dict.get("neighbourhood")
                    city = address_dict.get("city") or address_dict.get("town") or address_dict.get("city_district") or "Jakarta"
                    if road:
                        return {"label": f"{road}, {city}", "address": data.get("display_name", ""), "city": city}
                    if city:
                        return {"label": city, "address": data.get("display_name", ""), "city": city}
        except Exception:
            pass

        return {
            "label": f"Location ({lat:.4f}, {lon:.4f})",
            "address": "Indonesia",
            "city": "Indonesia",
        }

