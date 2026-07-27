"""Routing service adapter for EV-FLOW (Epic 2.0).

Primary provider: OSRM (Open Source Routing Machine API v5.24) configured via OSRM_BASE_URL.
Fallback provider: Local NetworkX Dijkstra graph router in `api.routing`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import shutil
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

logger = logging.getLogger(__name__)

OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
ROUTING_TIMEOUT_SECONDS = float(os.getenv("ROUTING_TIMEOUT_SECONDS", "10.0"))

# A provider that answers "0 km" for two points this far apart is off its map
# and is reporting nonsense (two identical coordinates for a 111 km ocean pair).
# Such a reply is discarded rather than published as a healthy direct route.
DEGENERATE_ROUTE_KM = float(os.getenv("ROUTING_DEGENERATE_ROUTE_KM", "0.5"))

# Providers whose geometry is real road geometry (as opposed to a straight line).
ROAD_PROVIDERS = ("osrm", "local_dijkstra")

# Not a routing provider: the label a DEGRADED, straight-line estimate carries so
# a client can tell it apart from real road geometry. Deliberately excluded from
# ROAD_PROVIDERS, which keeps `distance_basis` at 'straight_line' and
# `turn_by_turn_available` at False wherever it is used.
HAVERSINE_FALLBACK_PROVIDER = "haversine_fallback"

# Average speed used to turn a straight-line distance into a duration when no
# road provider answered. Matches the local Dijkstra fallback's own assumption.
ROUTING_FALLBACK_SPEED_KMH = float(os.getenv("ROUTING_FALLBACK_SPEED_KMH", "40.0"))

# Straight-line distance under-reports the real drive, and in the degraded path
# that error runs in the unsafe direction: a shorter distance means a rosier
# arrival SoC, which can hide the below-reserve warning. 1.3 is the usual road
# circuity ratio for a dense urban network like Jabodetabek. Raising it makes the
# fallback more cautious; lowering it below 1.0 would be actively unsafe.
ROUTING_CIRCUITY_FACTOR = max(1.0, float(os.getenv("ROUTING_CIRCUITY_FACTOR", "1.3")))


class RouteUnavailable(RuntimeError):
    """Raised when no road-following route geometry can be produced."""


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def straight_line_route(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    waypoints: Optional[List[Tuple[float, float]]] = None,
) -> Dict[str, Any]:
    """A clearly-labelled DEGRADED estimate for when every road provider is down.

    This is NOT a route and must never be published as one. It exists so a driver
    who is ALREADY UNDER WAY keeps receiving a remaining distance, an arrival-SoC
    projection and a battery warning when road routing dies mid-trip (AC 2.1.1 /
    AC 2.4.2) instead of being cut off with a 503.

    `provider` is 'haversine_fallback' and is absent from ROAD_PROVIDERS, so every
    existing consumer already treats the numbers as straight-line rather than
    road, and reports turn-by-turn as unavailable. TRIP PLANNING deliberately does
    NOT use this: POST /api/v1/route-plans still refuses rather than draw a line
    across the map.
    """
    coords = [origin, *(waypoints or []), destination]
    straight_km = sum(
        haversine_distance_km(a[0], a[1], b[0], b[1])
        for a, b in zip(coords, coords[1:])
    )
    # Roads do not run in straight lines. Publishing the raw haversine distance
    # would understate the real drive by 20-40%, which makes the arrival-SoC
    # projection OPTIMISTIC and can suppress the below-reserve battery warning at
    # the exact moment routing is broken and the driver is relying on it. Erring
    # short here is the dangerous direction, so the estimate is inflated by a
    # circuity factor before any energy maths sees it.
    distance_km = straight_km * ROUTING_CIRCUITY_FACTOR
    speed_kmh = ROUTING_FALLBACK_SPEED_KMH if ROUTING_FALLBACK_SPEED_KMH > 0 else 40.0
    return {
        "distance_km": round(distance_km, 2),
        "straight_line_km": round(straight_km, 2),
        "circuity_factor": ROUTING_CIRCUITY_FACTOR,
        "duration_minutes": round((distance_km / speed_kmh) * 60.0, 1),
        "geometry": {"type": "LineString", "coordinates": [[c[1], c[0]] for c in coords]},
        # No steps at all rather than a fabricated instruction: there is nothing
        # honest to say about which roads to take.
        "steps": [],
        "provider": HAVERSINE_FALLBACK_PROVIDER,
    }


class RoutingService:
    """Routing service providing directions and path geometry."""

    def __init__(self, osrm_base_url: str = OSRM_BASE_URL, timeout: float = ROUTING_TIMEOUT_SECONDS):
        self.osrm_base_url = osrm_base_url.rstrip("/")
        self.timeout = timeout

    async def get_route(
        self,
        origin: Tuple[float, float],       # (lat, lon)
        destination: Tuple[float, float],  # (lat, lon)
        waypoints: Optional[List[Tuple[float, float]]] = None,
    ) -> Dict[str, Any]:
        """Fetch driving directions. Tries OSRM first, falls back to local graph."""
        coords = [origin]
        if waypoints:
            coords.extend(waypoints)
        coords.append(destination)

        # Attempt OSRM if configured
        if self.osrm_base_url:
            try:
                osrm_result = await self._fetch_osrm_route(coords)
                if osrm_result:
                    return osrm_result
            except Exception:
                # Swallowing this silently made a degraded plan (2-point geometry,
                # one synthetic step) indistinguishable from a real one in the
                # logs. The client still gets a 200 with `routing_provider` set.
                logger.warning("routing: OSRM request failed, falling back", exc_info=True)

        # Fallback to the local OSM road graph. Do not fabricate geometry: every
        # route returned to the map must come from a road-routing provider.
        return self._local_fallback_route(coords)

    async def _fetch_osrm_route(self, coords: List[Tuple[float, float]]) -> Optional[Dict[str, Any]]:
        # OSRM expects coordinates in lon,lat order
        coord_str = ";".join([f"{lon:.6f},{lat:.6f}" for lat, lon in coords])
        url = f"{self.osrm_base_url}/route/v1/driving/{coord_str}?overview=full&geometries=geojson&steps=true"

        data = await self._request_osrm_json(url)
        if not data or data.get("code") != "Ok" or not data.get("routes"):
            return None

        route = data["routes"][0]
        dist_km = route["distance"] / 1000.0
        dur_mins = route["duration"] / 60.0

        # Reject a degenerate answer instead of reporting it as a healthy
        # plan: OSRM snapped both ends to the same off-map node.
        requested_km = sum(
            haversine_distance_km(a[0], a[1], b[0], b[1])
            for a, b in zip(coords, coords[1:])
        )
        if dist_km < DEGENERATE_ROUTE_KM <= requested_km:
            logger.warning(
                "routing: provider returned a degenerate 0 km route for a %.1f km request; "
                "discarding", requested_km)
            return None

        geometry = route["geometry"]  # GeoJSON LineString
        steps = []
        for leg_index, leg in enumerate(route.get("legs", [])):
            for step in leg.get("steps", []):
                maneuver = step.get("maneuver", {})
                steps.append({
                    "instruction": f"{maneuver.get('type', 'turn')} {maneuver.get('modifier', '')}".strip(),
                    "name": step.get("name", ""),
                    "distance_m": step.get("distance", 0),
                    "duration_s": step.get("duration", 0),
                    "location": maneuver.get("location", []),
                    # Which leg the step belongs to, so the client can tell
                    # where the charging stop falls in a multi-leg plan.
                    "leg_index": leg_index,
                })

        return {
            "distance_km": round(dist_km, 2),
            "duration_minutes": round(dur_mins, 1),
            "geometry": geometry,
            "steps": steps,
            "provider": "osrm",
        }

    async def _request_osrm_json(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": "EVFlow/1.0"},
            ) as client:
                resp = await client.get(url)
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception as exc:
            logger.warning("routing: httpx OSRM request failed, trying curl fallback: %s", exc)
            return await self._request_osrm_json_with_curl(url)

    async def _request_osrm_json_with_curl(self, url: str) -> Optional[Dict[str, Any]]:
        curl = shutil.which("curl")
        if not curl:
            return None

        proc = await asyncio.create_subprocess_exec(
            curl,
            "--globoff",
            "--silent",
            "--show-error",
            "--fail",
            "--location",
            "--compressed",
            "--max-time",
            str(max(1, int(math.ceil(self.timeout)))),
            "--user-agent",
            "EVFlow/1.0",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout + 1)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return None

        if proc.returncode != 0:
            logger.warning("routing: curl OSRM fallback failed: %s", stderr.decode("utf-8", "ignore").strip())
            return None

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("routing: curl OSRM fallback returned invalid JSON")
            return None

    def _local_fallback_route(self, coords: List[Tuple[float, float]]) -> Dict[str, Any]:
        """Local Dijkstra router fallback."""
        from api.routing import GraphUnavailable, shortest_path

        total_dist_km = 0.0
        all_coordinates: List[List[float]] = []

        try:
            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]
                res = shortest_path(p1[0], p1[1], p2[0], p2[1])
                if not res:
                    raise ValueError("Route unreachable in local graph")
                total_dist_km += res["distance_m"] / 1000.0

                coords_segment = res["geometry"]["coordinates"]
                if i > 0 and all_coordinates and coords_segment:
                    coords_segment = coords_segment[1:]
                all_coordinates.extend(coords_segment)

            total_duration_mins = (total_dist_km / 40.0) * 60.0  # Est 40 km/h
            return {
                "distance_km": round(total_dist_km, 2),
                "duration_minutes": round(total_duration_mins, 1),
                "geometry": {
                    "type": "LineString",
                    "coordinates": all_coordinates,
                },
                "steps": [
                    {"instruction": "Head towards destination", "name": "Main Road", "distance_m": total_dist_km * 1000, "duration_s": total_duration_mins * 60, "location": [coords[0][1], coords[0][0]], "leg_index": 0}
                ],
                "provider": "local_dijkstra",
            }
        except GraphUnavailable as exc:
            logger.warning("routing: local road graph unavailable", exc_info=True)
            raise RouteUnavailable("road routing is unavailable; no route geometry was generated") from exc
        except Exception:
            logger.warning("routing: local road graph could not find a route", exc_info=True)
            raise RouteUnavailable("no drivable road route found between the selected points")
