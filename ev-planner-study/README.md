# ev-planner-study

Groundwork study for Epics 4 & 5 (Strategic SPKLU Placement Optimization and the site
feasibility dashboard): a full inventory of the data we hold, the production cleaning pipeline
run end to end on it, a first 500 m grid feature build, a coverage-gap analysis with automated
candidate pinpoints, and a reproduction of the reference methodology on its own data.

## Contents

| File | What it is |
|---|---|
| `ev_planner_study.ipynb` | The study, fully executed (37 cells, all outputs embedded) |
| `spklu_bootstrap.py` | Team's acquisition pipeline (grid · substations · Zenodo · OCM · population · POI), licences in its docstring |
| `grid_jabodetabek_500m.gpkg` / `jabodetabek_adm2.gpkg` | Team-built grid and ADM2 boundaries the study runs on |
| `jabodetabek_adm_pcode.gpkg` | HDX COD-AB subset: 14 ADM2 + 187 kecamatan (ADM3), each with its P-code — the bridge to BPS tables (`pcode[2:]` = kode wilayah) |
| `idn_admin_boundaries.gdb` | Raw HDX COD-AB national geodatabase the subset above was cut from |
| `.venv-etl/` | Dedicated ETL environment (geopandas · pyogrio · rasterio · rasterstats · pyrosm) — heavy deps stay out of the API image by design |
| `output/jabodetabek_grid_features_phase0.parquet` | 28,176 cells × phase-0 features (station counts, connector capacity, nearest-station distance, gap score) |
| `output/candidate_pinpoints_phase0.csv` | 15 coverage-gap candidate coordinates (UTM 48S + WGS84) |

## How to run

```bash
cd ev-planner-study
jupyter nbconvert --to notebook --execute --inplace ev_planner_study.ipynb
```

No database and no network needed. Dependencies are the already-installed scientific stack
(`pandas`, `numpy`, `matplotlib`, `scikit-learn`, `shapely`, `scipy`, `pyarrow`) — deliberately
no `geopandas`/`pyproj`: the grid GeoPackage is read via plain `sqlite3`, and WGS84→UTM 48S is
an inline Snyder transform validated against Monas.

Inputs read (paths resolved relative to the repo, plus one absolute):

- `backend-ev-flow/data/raw/` — the three raw station feeds (PLN, OCM, OSM)
- `backend-ev-flow/api/` — the **production** `sources` / `dedup` / `service_area` modules,
  imported and executed, not re-implemented
- `ev-planner-study/grid_jabodetabek_500m.gpkg` — the team's 28,176-cell grid (kota labels,
  boundary overlap fraction) and `jabodetabek_adm2.gpkg` (14 ADM2 units, geoBoundaries)
- `/Users/mvvkur/Documents/iterasi3-evflow/data-science-Optimal-EV-station-placement/` — the
  reference repo: its German training data, plus the earlier 27,941-cell grid iteration whose
  OSM-only label (19 positive cells) the notebook uses as the before/after baseline

## Numbers the notebook pins (asserted, not narrated)

- 3,569 raw records → **2,931** stations after 75 m cross-source dedup → **1,236** inside the
  Jabodetabek service area — byte-for-byte the counts the deployed API serves
- Re-labelling the team's grid with our merged footprint: **19 → 889** positive cells
- 1,196 of the 1,236 box stations fall inside the ADM2 mask (the rest: bay and fringe cells)
- Reference method, leave-one-city-out AUC **0.893** (random split 0.905) — transfers honestly
- 15 candidate pinpoints, every one ≥ 10 km from any existing station

## What comes next (phases)

1. POI + land use from the Geofabrik Java PBF — `python spklu_bootstrap.py poi` (PBF URL already wired)
2. Population: WorldPop via `python spklu_bootstrap.py population`, calibrated with BPS SP2020 WebAPI — set `BPS_API_KEY` in
   `backend-ev-flow/.env` (already configured locally; the key is not committed)
3. Substation MVA headroom + RDTR zoning mask (licence still to be resolved)
4. Utilisation labels (Zenodo 16946731, 137 Greater Jakarta sites) → the supervised model
5. Epic 5 financial layer — blocked on real utilisation data; simulated demand must not price ROI

## Provenance rules

Simulated or proxy data is labelled as such wherever it appears; the gap surface is explicitly a
*coverage* surface, not demand; no model in this notebook is trained on features that leak its
label.
