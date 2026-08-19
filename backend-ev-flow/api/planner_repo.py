"""All planning_cells SQL, isolated from the endpoints.

Scores are computed per request rather than stored. The whole point of the
weights being a planner control is that moving one changes the map, so a stored
score would freeze exactly the thing that has to stay live. Cost is not the
reason to store: the grid is 28,176 rows and the work is a window function plus
a weighted sum, which Postgres finishes well inside a request.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from .db import engine
from .services.planner_viewport import Viewport, metric_column
from .services.site_scoring import SiteWeights, normalised_weights

#: Percentile rank per feature, computed across every cell that survives the
#: filter. `coverage` is capped at 10 km first: past that distance a cell is
#: unserved in any practical sense, and without the cap the far edge of Kabupaten
#: Bogor would stretch the scale and compress everywhere a driver actually is.
_RANKED = """
    WITH filtered AS (
        SELECT * FROM planning_cells
         WHERE overlap_frac >= :min_overlap
           AND kota <> ALL(:excluded_kota)
    ),
    ranked AS (
        SELECT cell_id, kota, centroid, population, poi_total, road_nodes,
               station_count, connector_count, nearest_station_m, stations_2km,
               PERCENT_RANK() OVER (ORDER BY LEAST(COALESCE(nearest_station_m, 0), 10000)) AS r_coverage,
               PERCENT_RANK() OVER (ORDER BY population)  AS r_population,
               PERCENT_RANK() OVER (ORDER BY poi_total)   AS r_activity,
               PERCENT_RANK() OVER (ORDER BY road_nodes)  AS r_roads
          FROM filtered
    ),
    scored AS (
        SELECT *,
               round((r_coverage   * :w_coverage
                    + r_population * :w_population
                    + r_activity   * :w_activity
                    + r_roads      * :w_roads)::numeric, 4) AS score
          FROM ranked
    )
"""

# Sea-separated cells are unreachable by road, so they are excluded from
# candidate generation by default rather than left to distort cluster centres.
DEFAULT_EXCLUDED_KOTA = ["Kepulauan Seribu"]


def _weight_params(weights: SiteWeights) -> dict:
    w = normalised_weights(weights)
    return {f"w_{name}": value for name, value in w.items()}


def score_cells(weights: SiteWeights, limit: int = 50, min_overlap: float = 0.5,
                excluded_kota: Optional[list[str]] = None) -> list[dict]:
    """Highest scoring cells under the given weights, best first."""
    params = _weight_params(weights)
    params.update(limit=limit, min_overlap=min_overlap,
                  excluded_kota=excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA)
    sql = _RANKED + """
        SELECT cell_id, kota, score,
               ST_Y(centroid) AS latitude, ST_X(centroid) AS longitude,
               population, poi_total, road_nodes,
               station_count, connector_count,
               round(nearest_station_m::numeric, 0) AS nearest_station_m, stations_2km
          FROM scored
      ORDER BY score DESC, cell_id
         LIMIT :limit
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def candidate_sites(weights: SiteWeights, clusters: int = 15,
                    quantile: float = 0.90, min_overlap: float = 0.5,
                    excluded_kota: Optional[list[str]] = None) -> list[dict]:
    """Cluster the top-scoring cells into a handful of suggested points.

    ST_ClusterKMeans groups the qualifying cells geographically, and each group
    is reported at its highest scoring member rather than at its centroid. A
    centroid can land in the middle of a river or on the wrong side of a toll
    road; an actual cell is somewhere a survey can be sent.
    """
    params = _weight_params(weights)
    params.update(clusters=clusters, quantile=quantile, min_overlap=min_overlap,
                  excluded_kota=excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA)
    sql = _RANKED + """,
    top AS (
        SELECT * FROM scored
         WHERE score >= (SELECT percentile_cont(:quantile) WITHIN GROUP (ORDER BY score) FROM scored)
    ),
    clustered AS (
        SELECT *, ST_ClusterKMeans(centroid, LEAST(:clusters, (SELECT count(*)::int FROM top)))
                    OVER () AS cluster_id
          FROM top
    ),
    best_per_cluster AS (
        SELECT DISTINCT ON (cluster_id) *
          FROM clustered
      ORDER BY cluster_id, score DESC, cell_id
    )
        SELECT cluster_id, cell_id, kota, score,
               ST_Y(centroid) AS latitude, ST_X(centroid) AS longitude,
               population, poi_total, station_count,
               round(nearest_station_m::numeric, 0) AS nearest_station_m, stations_2km,
               (SELECT count(*) FROM clustered c2 WHERE c2.cluster_id = best_per_cluster.cluster_id) AS cluster_size
          FROM best_per_cluster
      ORDER BY score DESC
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def cells_geojson(viewport: Viewport, metric: str = "score",
                  weights: Optional[SiteWeights] = None, limit: int = 1500,
                  min_overlap: float = 0.5,
                  excluded_kota: Optional[list[str]] = None) -> list[dict]:
    """Cell polygons inside the viewport, carrying the value the map colours by.

    The map draws real polygons rather than a rendered image, so the geometry
    goes over the wire. That makes the row limit the thing standing between a
    zoomed-out request and a multi-megabyte response, which is why cells are
    ordered by the chosen value and the highest ones survive the cut: a truncated
    heatmap should lose its quiet cells, not an arbitrary slice of the map.

    `metric` never reaches SQL as caller text. It is resolved through the fixed
    table in planner_viewport, because a column name cannot be a bound parameter.
    """
    column = metric_column(metric)
    # Safe to interpolate: `column` is a value from METRIC_COLUMNS, not input.
    value_expr = "s.score" if column == "score" else f"p.{column}"

    params = _weight_params(weights or SiteWeights())
    params.update(west=viewport.west, south=viewport.south,
                  east=viewport.east, north=viewport.north,
                  limit=limit, min_overlap=min_overlap,
                  excluded_kota=excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA)
    sql = _RANKED + f"""
        SELECT s.cell_id, s.kota, s.score, {value_expr} AS value,
               -- 6 decimals is about 11 cm, far finer than a 500 m cell needs.
               -- The default 15 nearly doubles the payload for no visible gain.
               ST_AsGeoJSON(p.geom, 6) AS geometry,
               s.population, s.poi_total, s.station_count,
               round(s.nearest_station_m::numeric, 0) AS nearest_station_m
          FROM scored s
          JOIN planning_cells p ON p.cell_id = s.cell_id
         WHERE p.geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
      ORDER BY value DESC NULLS LAST, s.cell_id
         LIMIT :limit
    """
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(sql), params).mappings().all()]


def cells_in_viewport(viewport: Viewport, min_overlap: float = 0.5,
                      excluded_kota: Optional[list[str]] = None) -> int:
    """How many cells the viewport actually covers, so a truncated response can say so."""
    sql = """
        SELECT count(*) FROM planning_cells
         WHERE overlap_frac >= :min_overlap
           AND kota <> ALL(:excluded_kota)
           AND geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
    """
    with engine.connect() as c:
        return c.execute(text(sql), {
            "west": viewport.west, "south": viewport.south,
            "east": viewport.east, "north": viewport.north,
            "min_overlap": min_overlap,
            "excluded_kota": excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA,
        }).scalar_one()


def get_cell(cell_id: str, weights: Optional[SiteWeights] = None,
             min_overlap: float = 0.5,
             excluded_kota: Optional[list[str]] = None) -> Optional[dict]:
    """Every feature for one cell, plus its score and rank under the weights.

    The filter defaults match score_cells deliberately. A percentile rank is a
    position within a set, so ranking one cell against all 28,176 while the map
    ranks it against the 27,219 that survive the filter gives the same cell two
    different scores, and a planner who clicks a cell scored 0.8390 on the map
    would read 0.8374 in the panel.

    A cell outside the filter is still returned, because it is still on the map
    and clicking it should explain itself rather than 404. It comes back with a
    null score and `in_scored_set` false, which says "not ranked" instead of
    quietly ranking it on a different basis.
    """
    params = _weight_params(weights or SiteWeights())
    params.update(cell_id=cell_id, min_overlap=min_overlap,
                  excluded_kota=excluded_kota if excluded_kota is not None else DEFAULT_EXCLUDED_KOTA)
    sql = _RANKED + """,
    with_rank AS (
        SELECT cell_id, score, rank() OVER (ORDER BY score DESC) AS rank_overall
          FROM scored
    )
        SELECT p.cell_id, p.kota, w.score, w.rank_overall,
               (SELECT count(*) FROM scored) AS cells_total,
               (w.cell_id IS NOT NULL) AS in_scored_set,
               ST_Y(p.centroid) AS latitude, ST_X(p.centroid) AS longitude,
               p.overlap_frac, p.population,
               p.poi_parking, p.poi_parking_space, p.poi_restaurant, p.poi_park,
               p.poi_school, p.poi_university, p.poi_cinema, p.poi_library,
               p.poi_community_centre, p.poi_place_of_worship, p.poi_townhall,
               p.poi_government, p.poi_civic, p.poi_fuel, p.poi_mall,
               p.poi_hospital, p.poi_rest_area, p.poi_total,
               p.lu_commercial_share, p.lu_retail_share,
               p.lu_residential_share, p.lu_industrial_share,
               p.road_nodes, p.road_length_m,
               p.station_count, p.connector_count,
               round(p.nearest_station_m::numeric, 0) AS nearest_station_m, p.stations_2km
          FROM planning_cells p
     LEFT JOIN with_rank w ON w.cell_id = p.cell_id
         WHERE p.cell_id = :cell_id
    """
    with engine.connect() as c:
        row = c.execute(text(sql), params).mappings().first()
    return dict(row) if row else None


def nearby_stations(cell_id: str, radius_km: float = 5.0, limit: int = 10) -> list[dict]:
    """Existing stations around a cell, nearest first (Epic 5 benchmarking)."""
    sql = """
        SELECT s.id, s.name, s.operator, s.power_kw, s.speed_tier,
               round(ST_Distance(p.centroid::geography, s.geom::geography)::numeric, 0) AS distance_m,
               count(c.id) FILTER (WHERE c.status = 'available') AS available_connectors,
               count(c.id) AS total_connectors
          FROM planning_cells p
          JOIN stations s
            ON ST_DWithin(p.centroid::geography, s.geom::geography, :radius_m)
     LEFT JOIN connectors c ON c.station_id = s.id
         WHERE p.cell_id = :cell_id
      GROUP BY s.id, s.name, s.operator, s.power_kw, s.speed_tier, p.centroid, s.geom
      ORDER BY distance_m
         LIMIT :limit
    """
    with engine.connect() as c:
        rows = c.execute(text(sql), {"cell_id": cell_id, "radius_m": radius_km * 1000.0,
                                     "limit": limit}).mappings().all()
    return [dict(r) for r in rows]


def grid_summary() -> dict:
    """Coverage of the loaded grid, for a health check and for the dashboard header."""
    sql = """
        SELECT count(*)                                        AS cells,
               count(*) FILTER (WHERE station_count > 0)        AS cells_with_station,
               count(*) FILTER (WHERE population > 0)           AS cells_populated,
               COALESCE(sum(station_count), 0)                  AS stations,
               COALESCE(sum(connector_count), 0)                AS connectors,
               COALESCE(round(sum(population)::numeric, 0), 0)  AS population_total,
               count(DISTINCT kota)                             AS areas,
               max(built_at)                                    AS built_at
          FROM planning_cells
    """
    with engine.connect() as c:
        return dict(c.execute(text(sql)).mappings().one())
