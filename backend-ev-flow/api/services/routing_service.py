"""Routing service adapter for EV-FLOW (Epic 2.0).

Primary provider: OSRM (Open Source Routing Machine API v5.24) configured via OSRM_BASE_URL.
Fallback provider: Local NetworkX Dijkstra graph router in `api.routing`.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
ROUTING_TIMEOUT_SECONDS = float(os.getenv("ROUTING_TIMEOUT_SECONDS", "3.0"))



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
                pass

        # Fallback to local graph or straight-line estimation
        return self._local_fallback_route(coords)

    async def _fetch_osrm_route(self, coords: List[Tuple[float, float]]) -> Optional[Dict[str, Any]]:
        # OSRM expects coordinates in lon,lat order
        coord_str = ";".join([f"{lon:.6f},{lat:.6f}" for lat, lon in coords])
        url = f"{self.osrm_base_url}/route/v1/driving/{coord_str}?overview=full&geometries=geojson&steps=true"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None

            route = data["routes"][0]
            dist_km = route["distance"] / 1000.0
            dur_mins = route["duration"] / 60.0

            geometry = route["geometry"]  # GeoJSON LineString
            steps = []
            for leg in route.get("legs", []):
                for step in leg.get("steps", []):
                    maneuver = step.get("maneuver", {})
                    steps.append({
                        "instruction": f"{maneuver.get('type', 'turn')} {maneuver.get('modifier', '')}".strip(),
                        "name": step.get("name", ""),
                        "distance_m": step.get("distance", 0),
                        "duration_s": step.get("duration", 0),
                        "location": maneuver.get("location", []),
                    })

            return {
                "distance_km": round(dist_km, 2),
                "duration_minutes": round(dur_mins, 1),
                "geometry": geometry,
                "steps": steps,
                "provider": "osrm",
            }

    def _local_fallback_route(self, coords: List[Tuple[float, float]]) -> Dict[str, Any]:
        """Local Dijkstra router fallback or straight-line segment generator."""
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
                    {"instruction": "Head towards destination", "name": "Main Road", "distance_m": total_dist_km * 1000, "duration_s": total_duration_mins * 60, "location": [coords[0][1], coords[0][0]]}
                ],
                "provider": "local_dijkstra",
            }
        except Exception:
            # Simple Haversine fallback for synthetic/test environments
            line_coords = []
            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]
                total_dist_km += haversine_distance_km(p1[0], p1[1], p2[0], p2[1]) * 1.25  # 1.25 winding factor
                if not line_coords:
                    line_coords.append([p1[1], p1[0]])
                line_coords.append([p2[1], p2[0]])

            total_duration_mins = (total_dist_km / 50.0) * 60.0
            return {
                "distance_km": round(total_dist_km, 2),
                "duration_minutes": round(total_duration_mins, 1),
                "geometry": {
                    "type": "LineString",
                    "coordinates": line_coords,
                },
                "steps": [
                    {"instruction": "Proceed along route", "name": "Highway", "distance_m": total_dist_km * 1000, "duration_s": total_duration_mins * 60, "location": line_coords[0]}
                ],
                "provider": "haversine_fallback",
            }
