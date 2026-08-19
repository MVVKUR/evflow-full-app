#!/usr/bin/env python3
"""
SPKLU Jabodetabek — data bootstrap pipeline
============================================
Reproducible acquisition + feature engineering for the 500 m grid.
Adapts Maurya et al. (2024) to Jabodetabek with open/licensed sources only.

Usage:
    python spklu_bootstrap.py grid          # build 500 m grid (or use the delivered .gpkg)
    python spklu_bootstrap.py substations   # BIG gardu induk -> per-cell grid features
    python spklu_bootstrap.py zenodo        # download + inspect the 137-site EVCS dataset
    python spklu_bootstrap.py ocm           # Open Charge Map pull (needs OCM_API_KEY)
    python spklu_bootstrap.py population    # WorldPop zonal stats per cell
    python spklu_bootstrap.py poi           # POI + landuse features from Geofabrik PBF

Deps:
    pip install geopandas shapely pyproj scipy pandas openpyxl requests
    pip install rasterio rasterstats          # for `population`
    pip install pyrosm                        # for `poi`

Licences of what this script touches:
    geoBoundaries gbOpen IDN ADM2  CC BY 3.0 IGO (source: BPS/WFP/OCHA)
    BIG Satu Peta SARANA_PRASARANA public REST, no stated licence -> cite + timestamp
    Zenodo 10.5281/zenodo.16946731 CC BY 4.0
    Open Charge Map                CC BY 4.0 (check per-record DataProviderID)
    OSM / Geofabrik                ODbL 1.0  ("(c) OpenStreetMap contributors")
    WorldPop                       CC BY 4.0

Architecture note (EV-FLOW): run this as an OFFLINE batch job that writes to
PostGIS. The API should read precomputed cell features, never compute the
26k-cell spatial joins per request.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA, exist_ok=True)

CRS_METRIC = 32748          # UTM 48S — metric, correct for Jabodetabek
GRID_SIZE = 500.0           # metres, matches the reference study
GRID_GPKG = os.path.join(DATA, "grid_jabodetabek_500m.gpkg")
ADM2_GPKG = os.path.join(DATA, "jabodetabek_adm2.gpkg")

# Jabodetabek bbox (lon/lat) with margin
BBOX = (106.30, -6.95, 107.30, -5.85)

JABO_KEYS = ["Jakarta", "Bogor", "Depok", "Tangerang", "Bekasi", "Seribu"]


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}")


# ----------------------------------------------------------------------------
# 1. GRID
# ----------------------------------------------------------------------------
def build_grid():
    import geopandas as gpd
    import shapely

    if not os.path.exists(ADM2_GPKG):
        # geoBoundaries gbOpen IDN ADM2 (CC BY 3.0 IGO). Pin the commit hash for
        # reproducibility — this is the "dated snapshot" principle.
        url = ("https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/"
               "9469f09/releaseData/gbOpen/IDN/ADM2/geoBoundaries-IDN-ADM2.geojson")
        log(f"downloading ADM2 boundaries (152 MB): {url}")
        tmp = os.path.join(DATA, "idn_adm2.geojson")
        urllib.request.urlretrieve(url, tmp)
        adm2 = gpd.read_file(tmp)
        sel = adm2[adm2["shapeName"].apply(
            lambda n: any(k in str(n) for k in JABO_KEYS))].copy()
        assert len(sel) == 14, f"expected 14 Jabodetabek ADM2 units, got {len(sel)}"
        sel.to_file(ADM2_GPKG, layer="adm2", driver="GPKG")
        os.remove(tmp)
        log(f"saved {ADM2_GPKG} ({len(sel)} units)")

    adm2 = gpd.read_file(ADM2_GPKG).to_crs(CRS_METRIC)
    adm2["kota"] = adm2["shapeName"]
    union = adm2.union_all()

    xmin, ymin, xmax, ymax = union.bounds
    S = GRID_SIZE
    xs = np.arange(np.floor(xmin / S) * S, xmax, S)
    ys = np.arange(np.floor(ymin / S) * S, ymax, S)
    gx, gy = (a.ravel() for a in np.meshgrid(xs, ys))
    grid = gpd.GeoDataFrame(geometry=shapely.box(gx, gy, gx + S, gy + S),
                            crs=CRS_METRIC)

    hit = grid.sindex.query(union, predicate="intersects")
    grid = grid.iloc[np.sort(hit)].reset_index(drop=True)
    log(f"{len(grid)} cells intersect the study area")

    inter = shapely.intersection(grid.geometry.values, union)
    grid["overlap_frac"] = shapely.area(inter) / (S * S)

    rep = gpd.GeoDataFrame(geometry=grid.representative_point(), crs=CRS_METRIC)
    j = gpd.sjoin(rep, adm2[["kota", "geometry"]], how="left", predicate="within")
    grid["kota"] = j["kota"].values
    miss = grid["kota"].isna()
    if miss.any():
        jn = gpd.sjoin_nearest(rep[miss.values], adm2[["kota", "geometry"]], how="left")
        grid.loc[miss, "kota"] = jn["kota"].values

    grid["cell_id"] = ["JBDTBK_" + str(i).zfill(5) for i in range(len(grid))]
    c = grid.geometry.centroid
    grid["centroid_x"], grid["centroid_y"] = c.x, c.y
    ll = c.to_crs(4326)
    grid["lon"], grid["lat"] = ll.x.round(6), ll.y.round(6)

    grid.to_file(GRID_GPKG, layer="grid", driver="GPKG")
    log(f"SAVED {GRID_GPKG}: {len(grid)} cells")
    print(grid.groupby("kota").size().sort_values(ascending=False))


# ----------------------------------------------------------------------------
# 2. SUBSTATIONS (BIG Satu Peta, layer 9 "Peta Sebaran Lokasi Gardu Induk")
# ----------------------------------------------------------------------------
def pull_substations():
    import geopandas as gpd
    from scipy.spatial import cKDTree

    base = ("https://kspservices.big.go.id/satupeta/rest/services/PUBLIK/"
            "SARANA_PRASARANA/MapServer/9/query")
    feats = []
    offset = 0
    while True:
        url = (f"{base}?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326"
               f"&f=geojson&resultOffset={offset}&resultRecordCount=1000")
        with urllib.request.urlopen(url, timeout=180) as r:
            d = json.load(r)
        batch = d.get("features", [])
        feats += batch
        log(f"offset {offset}: +{len(batch)}")
        if len(batch) < 1000:
            break
        offset += 1000

    out = os.path.join(DATA, "gardu_induk_national.geojson")
    with open(out, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats,
                   "_retrieved": datetime.datetime.now().isoformat(),
                   "_source": base}, f)
    log(f"saved {out}: {len(feats)} substations nationally")
    # Verified 2026-08-15 via count queries: total 1,109; alamat LIKE
    # '%Jakarta%' 59, '%Bekasi%' 32, '%Tangerang%' 30, '%Bogor%' 21.

    gi = gpd.read_file(out).to_crs(CRS_METRIC)
    gi["kapgi"] = pd.to_numeric(gi["kapgi"], errors="coerce").fillna(0.0)
    gi["teggi"] = pd.to_numeric(gi["teggi"], errors="coerce").fillna(0.0)

    grid = gpd.read_file(GRID_GPKG, layer="grid")
    tree = cKDTree(np.c_[gi.geometry.x, gi.geometry.y])
    dist, idx = tree.query(np.c_[grid["centroid_x"], grid["centroid_y"]])
    grid["dist_gi_m"] = dist.round(0)
    grid["gi_nearest_kv"] = gi.iloc[idx]["teggi"].values
    grid["gi_nearest_mva"] = gi.iloc[idx]["kapgi"].values   # 0 = unpopulated, NOT zero capacity!
    grid["gi_nearest_name"] = gi.iloc[idx]["namaobj"].values

    # kapgi is sparsely populated (16/59 in Jakarta) -> also provide an ordinal
    # capacity proxy from voltage class, and distance to nearest *populated* GI.
    grid["gi_kv_class"] = pd.cut(grid["gi_nearest_kv"], [0, 70, 150, 500, 9999],
                                 labels=["<70", "70", "150", "500"], right=True)
    gi_cap = gi[gi["kapgi"] > 0]
    tree2 = cKDTree(np.c_[gi_cap.geometry.x, gi_cap.geometry.y])
    d2, i2 = tree2.query(np.c_[grid["centroid_x"], grid["centroid_y"]])
    grid["dist_gi_with_mva_m"] = d2.round(0)
    grid["gi_with_mva_capacity"] = gi_cap.iloc[i2]["kapgi"].values

    grid.to_file(GRID_GPKG, layer="grid", driver="GPKG")
    log("grid updated with substation features")


# ----------------------------------------------------------------------------
# 3. ZENODO 137-site EVCS dataset (CC BY 4.0)
# ----------------------------------------------------------------------------
def get_zenodo():
    url = "https://zenodo.org/records/16946731/files/poi_iii_Zenodo.xlsx?download=1"
    out = os.path.join(DATA, "poi_iii_Zenodo.xlsx")
    if not os.path.exists(out):
        log(f"downloading {url}")
        urllib.request.urlretrieve(url, out)
    df = pd.read_excel(out)
    log(f"{len(df)} rows x {len(df.columns)} cols")
    print("columns:", list(df.columns))
    print(df.head(3).to_string())
    coord_cols = [c for c in df.columns
                  if any(k in c.lower() for k in ("lat", "lon", "lng", "coord", "x", "y"))]
    print("\nlikely coordinate columns:", coord_cols or "NONE FOUND — check manually")
    # If coordinates exist: this is your calibration set for the utilisation
    # model (Epic 5 viability score). Join to grid via sjoin on points.


# ----------------------------------------------------------------------------
# 4. OPEN CHARGE MAP (CC BY 4.0) — free key: openchargemap.org -> my apps
# ----------------------------------------------------------------------------
def pull_ocm():
    key = os.environ.get("OCM_API_KEY")
    if not key:
        sys.exit("set OCM_API_KEY first (free at openchargemap.org -> profile -> my apps)")
    url = ("https://api.openchargemap.io/v3/poi?countrycode=ID&maxresults=100000"
           f"&compact=false&verbose=false&output=geojson&key={key}")
    out = os.path.join(DATA, "ocm_indonesia.geojson")
    req = urllib.request.Request(url, headers={"User-Agent": "spklu-thesis/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        raw = r.read()
    with open(out, "wb") as f:
        f.write(raw)
    d = json.loads(raw)
    n = len(d.get("features", []))
    log(f"saved {out}: {n} POIs (Indonesia)")
    # Next: filter bbox to Jabodetabek; record per-feature DataProviderID for the
    # licence audit; de-duplicate vs OSM (amenity=charging_station) and vs your
    # existing PLN table with a 150 m nearest-neighbour match.


# ----------------------------------------------------------------------------
# 5. POPULATION (WorldPop 2020 constrained, 100 m, CC BY 4.0)
# ----------------------------------------------------------------------------
def population():
    import geopandas as gpd
    from rasterstats import zonal_stats

    # Current-year estimate from WorldPop's 2015-2030 projection series (release
    # R2025A, published 2025-08). The older Global_2000_2020_Constrained ends at
    # 2020; keep that 2020 raster in mind only if calibrating against the SP2020
    # census, where matching epochs matters more than currency:
    #   .../Global_2000_2020_Constrained/2020/BSGM/IDN/idn_ppp_2020_constrained.tif
    tif = os.path.join(DATA, "idn_pop_2026_CN_100m_R2025A_v1.tif")
    if not os.path.exists(tif):
        url = ("https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/"
               "2026/IDN/v1/100m/constrained/idn_pop_2026_CN_100m_R2025A_v1.tif")
        log(f"downloading WorldPop 2026 constrained (~170 MB): {url}")
        urllib.request.urlretrieve(url, tif)

    grid = gpd.read_file(GRID_GPKG, layer="grid")
    # raster is EPSG:4326 -> compute stats on reprojected geometries
    g4326 = grid.to_crs(4326)
    log("zonal stats (sum of people per cell)…")
    zs = zonal_stats(g4326.geometry, tif, stats=["sum"], all_touched=False, nodata=-99999)
    grid["population"] = [z["sum"] or 0.0 for z in zs]
    grid["population"] = grid["population"].round(1)
    grid.to_file(GRID_GPKG, layer="grid", driver="GPKG")
    log(f"population added. total study-area pop: {grid['population'].sum():,.0f}")
    # Alternative for exact 500 m alignment: GHS-POP 100 m Mollweide, aggregate
    # 5x5. State deliberately which product + variant you use in the thesis.


# ----------------------------------------------------------------------------
# 6. POI + LANDUSE from Geofabrik Java PBF (ODbL)
# ----------------------------------------------------------------------------
# German-study schema -> OSM raw tags. The four starred ones are NOT separable
# in Geofabrik's pre-classified shapefile fclass — that is why we read the PBF.
POI_TAGS = {
    "parking":          ("amenity", "parking"),
    "parking_space":    ("amenity", "parking_space"),   # sparse in ID — report count
    "restaurant":       ("amenity", "restaurant"),
    "park":             ("leisure", "park"),
    "school":           ("amenity", "school"),
    "university":       ("amenity", "university"),
    "cinema":           ("amenity", "cinema"),
    "library":          ("amenity", "library"),
    "community_centre": ("amenity", "community_centre"),  # *
    "place_of_worship": ("amenity", "place_of_worship"),
    "townhall":         ("amenity", "townhall"),          # *
    "government":       ("office", "government"),         # *
    "civic":            ("building", "civic"),            # * closest OSM equivalent
    # Indonesia-specific additions (Kepmen 24.K/2025 siting categories):
    "fuel":             ("amenity", "fuel"),
    "mall":             ("shop", "mall"),
    "hospital":         ("amenity", "hospital"),
    "rest_area":        ("highway", "services"),
}
LANDUSE_SHARE = ["commercial", "retail", "residential", "industrial"]


def poi_features(pbf_path):
    import geopandas as gpd
    from pyrosm import OSM

    grid = gpd.read_file(GRID_GPKG, layer="grid")
    minx, miny, maxx, maxy = BBOX
    osm = OSM(pbf_path, bounding_box=[minx, miny, maxx, maxy])

    # --- POI counts (centroid-in-cell, matching the reference method) ---
    keys = {}
    for col, (k, v) in POI_TAGS.items():
        keys.setdefault(k, []).append(v)
    pois = osm.get_data_by_custom_criteria(
        custom_filter=keys, filter_type="keep",
        keep_nodes=True, keep_ways=True, keep_relations=True)
    pois = pois.to_crs(CRS_METRIC)
    pois["geometry"] = pois.geometry.centroid

    for col, (k, v) in POI_TAGS.items():
        if k not in pois.columns:
            grid[col] = 0
            continue
        sub = pois[pois[k] == v]
        j = gpd.sjoin(sub[["geometry"]], grid[["cell_id", "geometry"]],
                      how="inner", predicate="within")
        counts = j.groupby("cell_id").size()
        grid[col] = grid["cell_id"].map(counts).fillna(0).astype(int)
        log(f"{col}: {int(grid[col].sum())} POIs")

    # Checkpoint: POI counts are expensive to recompute, so persist them before
    # the landuse overlay. A failure below then costs the landuse pass only.
    grid.to_file(GRID_GPKG, layer="grid", driver="GPKG")
    log("checkpoint written after POI counts")

    # --- landuse area share per cell ---
    lu = osm.get_landuse().to_crs(CRS_METRIC)
    # get_landuse() returns Polygon AND MultiPolygon (and occasionally point or
    # line features tagged landuse=*). gpd.overlay refuses mixed types, so keep
    # the polygonal rows and explode multiparts into single polygons.
    lu = lu[lu.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    lu = lu.explode(index_parts=False)
    lu = lu[lu.geometry.geom_type == "Polygon"]
    log(f"landuse polygons after type filter: {len(lu):,}")
    # Dissolve each class into a single geometry before intersecting. OSM often
    # carries overlapping polygons of the same class (a residential estate drawn
    # inside a wider residential area), and intersecting them separately counts
    # the overlap once per polygon. That produced shares above 1.0 in 1,062 cells
    # for residential alone, which is impossible for a proportion of cell area.
    lu = lu.dissolve(by="landuse", as_index=False)
    for cls in LANDUSE_SHARE:
        sub = lu[lu["landuse"] == cls]
        if sub.empty:
            grid[f"lu_{cls}_share"] = 0.0
            continue
        ov = gpd.overlay(grid[["cell_id", "geometry"]], sub[["geometry"]],
                         how="intersection", keep_geom_type=True)
        share = ov.assign(a=ov.area).groupby("cell_id")["a"].sum() / (GRID_SIZE ** 2)
        grid[f"lu_{cls}_share"] = grid["cell_id"].map(share).fillna(0.0).round(4)
        log(f"lu_{cls}: mean share {grid[f'lu_{cls}_share'].mean():.4f}")

    # --- road network nodes / edges (reference-study variables) ---
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    nodes = nodes.to_crs(CRS_METRIC)
    jn = gpd.sjoin(nodes[["geometry"]], grid[["cell_id", "geometry"]],
                   how="inner", predicate="within")
    grid["node"] = grid["cell_id"].map(jn.groupby("cell_id").size()).fillna(0).astype(int)

    edges = edges.to_crs(CRS_METRIC)
    ov = gpd.overlay(grid[["cell_id", "geometry"]],
                     edges[["geometry"]].explode(index_parts=False),
                     how="intersection", keep_geom_type=False)
    ov = ov[ov.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    grid["edge_len_m"] = grid["cell_id"].map(
        ov.assign(L=ov.length).groupby("cell_id")["L"].sum()).fillna(0).round(0)

    grid.to_file(GRID_GPKG, layer="grid", driver="GPKG")
    log("POI/landuse/network features written")
    # QA next: compare school / place_of_worship counts per kelurahan against
    # PODES 2024 — that comparison is your OSM-completeness contribution.


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["grid", "substations", "zenodo", "ocm",
                                     "population", "poi"])
    ap.add_argument("--pbf", help="path to java-latest.osm.pbf (for `poi`)")
    a = ap.parse_args()
    {"grid": build_grid,
     "substations": pull_substations,
     "zenodo": get_zenodo,
     "ocm": pull_ocm,
     "population": population,
     "poi": lambda: poi_features(a.pbf or sys.exit("--pbf required")),
     }[a.step]()
