"""planning_cells: the 500 m siting grid the planner endpoints read

Epic 4 and Epic 5 answer questions about PLACES, not about individual stations,
so they need a spatial unit that is the same size everywhere. A kelurahan in
central Jakarta is a fraction of the size of one in Kabupaten Bogor, which makes
any count per kelurahan mean different things in different places. A fixed 500 m
cell removes that.

The rows are BUILT OFFLINE, by ev-planner-study/spklu_bootstrap.py plus the
loader in scripts/load_planning_cells.py. Parsing an 854 MB OSM extract and
sampling a population raster needs geopandas, rasterio and pyrosm, which are
deliberately absent from the API image (see requirements-api.txt). The API only
ever reads this table, and the scoring it does on top is a weighted sum plus
ST_ClusterKMeans, both plain SQL, so a planner can move a weight and see the map
change without any of that machinery being installed.

Scores are NOT stored. They are computed per request from whatever weights the
planner sent; storing them would freeze the one thing that has to stay live.

Revision ID: 0018_planning_cells
Revises: 0017_occupancy_sum_per_window
"""
from alembic import op

revision = "0018_planning_cells"
down_revision = "0017_occupancy_sum_per_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS planning_cells (
            cell_id              text PRIMARY KEY,
            geom                 geometry(Polygon, 4326) NOT NULL,
            centroid             geometry(Point,   4326) NOT NULL,
            kota                 text,
            -- Share of the cell inside the administrative outline. Edge cells are
            -- partial, and a count in a 12%-covered cell is not comparable with one
            -- in a whole cell, so callers can weight or exclude on this.
            overlap_frac         double precision,

            -- Points of interest, 17 categories. Thirteen mirror the reference
            -- study so the two feature sets stay comparable; fuel, mall, hospital
            -- and rest_area are the Indonesian additions from Kepmen ESDM 24.K/2025.
            poi_parking          integer NOT NULL DEFAULT 0,
            poi_parking_space    integer NOT NULL DEFAULT 0,
            poi_restaurant       integer NOT NULL DEFAULT 0,
            poi_park             integer NOT NULL DEFAULT 0,
            poi_school           integer NOT NULL DEFAULT 0,
            poi_university       integer NOT NULL DEFAULT 0,
            poi_cinema           integer NOT NULL DEFAULT 0,
            poi_library          integer NOT NULL DEFAULT 0,
            poi_community_centre integer NOT NULL DEFAULT 0,
            poi_place_of_worship integer NOT NULL DEFAULT 0,
            poi_townhall         integer NOT NULL DEFAULT 0,
            poi_government       integer NOT NULL DEFAULT 0,
            poi_civic            integer NOT NULL DEFAULT 0,
            poi_fuel             integer NOT NULL DEFAULT 0,
            poi_mall             integer NOT NULL DEFAULT 0,
            poi_hospital         integer NOT NULL DEFAULT 0,
            poi_rest_area        integer NOT NULL DEFAULT 0,
            poi_total            integer NOT NULL DEFAULT 0,

            -- Land-use area shares. CHECKed at or below 1.0 because overlapping
            -- OSM polygons of the same class produced shares up to 2.77 before the
            -- loader learned to dissolve them, and a share above 1 is not a share.
            lu_commercial_share  double precision NOT NULL DEFAULT 0
                                 CHECK (lu_commercial_share  BETWEEN 0 AND 1),
            lu_retail_share      double precision NOT NULL DEFAULT 0
                                 CHECK (lu_retail_share      BETWEEN 0 AND 1),
            lu_residential_share double precision NOT NULL DEFAULT 0
                                 CHECK (lu_residential_share BETWEEN 0 AND 1),
            lu_industrial_share  double precision NOT NULL DEFAULT 0
                                 CHECK (lu_industrial_share  BETWEEN 0 AND 1),

            road_nodes           integer NOT NULL DEFAULT 0,
            road_length_m        double precision NOT NULL DEFAULT 0,

            -- WorldPop 2026 constrained. A PROJECTION, not a census count; every
            -- response that carries it must say so.
            population           double precision NOT NULL DEFAULT 0,

            -- Existing supply, derived from the stations table at load time.
            station_count        integer NOT NULL DEFAULT 0,
            connector_count      integer NOT NULL DEFAULT 0,
            nearest_station_m    double precision,
            stations_2km         integer NOT NULL DEFAULT 0,

            built_at             timestamptz NOT NULL DEFAULT now()
        );
    """)
    # Centroid index carries the load: scoring, clustering and viewport queries
    # all work off the point, not the polygon.
    op.execute("CREATE INDEX IF NOT EXISTS planning_cells_centroid_gix ON planning_cells USING GIST (centroid);")
    op.execute("CREATE INDEX IF NOT EXISTS planning_cells_geom_gix     ON planning_cells USING GIST (geom);")
    op.execute("CREATE INDEX IF NOT EXISTS planning_cells_kota_ix      ON planning_cells (kota);")


def downgrade() -> None:
    raise NotImplementedError(
        "Refusing to drop planning_cells. Rebuilding it needs an 854 MB OSM extract "
        "and a 170 MB population raster re-processed offline, so an automatic "
        "downgrade would discard hours of work to undo a schema change. Drop it by "
        "hand if that is genuinely what you want."
    )
