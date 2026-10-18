# Patrac: macOS + Slovakia port (Košický kraj)

Date: 2026-10-18
Branch: `feature/slovakia-macos-port`

## Goal

Run the Patrac QGIS plugin on macOS for search-and-rescue planning in Slovakia, starting with Košický kraj. The user is a Python programmer who is new to GIS, so the work also produces plain explanations of the geo concepts involved. No installer is needed: the plugin runs from a source checkout inside QGIS.

## Out of scope

- Dog-handler call-out (HS ČR API). The code stays but is disabled.
- Live tracking. The user uses CalTopo for that.
- UI translation. English and Czech are sufficient.
- GRASS-based processing. The "lite" algorithm is used.
- Whole-country data. Košický kraj first; the pipeline must accept any region.
- Packaging or installation of the plugin for other users.

## Background findings

- The plugin runs inside QGIS (it uses `qgis.core`, `qgis.gui`, `processing`). It cannot run as a standalone script.
- The lite algorithm (`main/area.py`, `CalculateDistance`) uses only the straight-line distance from the last-seen point(s) to each sector, mapped to a percentage via `grass/distances.txt` (ISRID-style quantiles per person type). It needs no DEM or friction raster. The distance table is not country-specific and stays unchanged.
- A project is created for a municipality chosen from a CSV (`name;coords in S-JTSK;...;region`). The plugin clips pre-built regional layers to a 12 km × 10 km box around it. The clipped layers are `sectors`, `cesta` (roads), `lespru` (forest paths) and `vodtok` (streams), read from `<data_path>/kraje/<region>/vektor/ZABAGED/`.
- The Czech sector layer was produced offline by the original author (merge all polygon and line layers into lines, polygonize, merge into 10–20 ha polygons of one land-use type). That script is not in this repository.
- EPSG:5514 (S-JTSK) is hardcoded in about 40 places. Slovakia used the same system, and `ui/sk_obce_okr_kr_utf8.csv` already holds Slovak municipalities in S-JTSK coordinates. Decision: keep EPSG:5514.
- The existing GPX import (`ui/ui_gpx.py`) only loads tracks as layers grouped by sector or team. It does no analysis.

## Decisions

| Topic | Decision |
|---|---|
| Sector data source | OpenStreetMap, Geofabrik extract of Slovakia, clipped to Košický kraj |
| Swappability | OSM tag to land-use mapping lives in a rules file, so ZBGIS can replace OSM later |
| Coverage | Košický kraj first; the pipeline is region-agnostic |
| Pipeline runtime | QGIS's bundled Python (GDAL and `processing` included), no second geo stack |
| CRS | Keep EPSG:5514 |
| Git | All work on feature branches; commits on `feature/slovakia-macos-port`; master untouched |

## Sub-projects

Each sub-project gets its own implementation plan and commits. Order matters: each depends on the previous one.

### 1. macOS dev setup

- Install QGIS (LTR release) on macOS, with Homebrew or the official installer. The exact version is chosen at install time. The plugin declares `qgisMinimumVersion=3.26`.
- Symlink this repository into the QGIS profile plugins folder: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_patrac_3`. Enable it in the Plugin Manager.
- IDE workflow: the IDE uses QGIS's bundled Python as its interpreter so `qgis.*` imports resolve. Debugging attaches to the running QGIS with `debugpy`. Plugin Reloader or a QGIS restart reloads code.
- Docs: `docs/dev/macos-setup.md` (setup steps) and `docs/dev/qgis-for-python-devs.md` (short glossary: layer, CRS, shapefile, GeoPackage, WMS, processing algorithm, QgsTask, why S-JTSK).
- Acceptance: QGIS starts, the Patrac dock panel appears, and the log shows no import errors. Project creation is not expected to work yet (no data).

### 2. Slovak data pipeline

- New directory `tools/sk_data/`, run with the QGIS Python. Input: a Geofabrik OSM extract, a region polygon (Košický kraj boundary) and an output folder. Output: the folder layout the plugin expects:
  `<data_path>/kraje/<region>/vektor/ZABAGED/{sectors,cesta,lespru,vodtok}.shp`, `lastsectorid.txt` and `<data_path>/kraje/<region>/metadata.json` (version `2020-01-01`, which is what `checkRegion` currently requires).
- `rules/osm_landuse.json` maps OSM tags (`landuse`, `natural`, `highway`, `waterway`, `building` and so on) to the plugin's land-use classes 1–10. The existing `grass/landuse_type_osm.rules` and `landuse_type_zbg.rules` are the reference for the class meanings.
- Sector building:
  1. Collect boundary lines from roads, rails, waterways and the edges of land-use polygons.
  2. Polygonize.
  3. Assign each polygon a land-use class by overlay.
  4. Merge small neighbouring polygons of the same class until sectors are about 10–20 ha.
- Output attributes must match what the plugin reads (`area_ha`, `label`, plus whatever the report code requires). The exact schema is confirmed against `main/sectors.py` and `main/project.py` at the start of this sub-project, and the spec is amended if the schema is larger than expected.
- Validation: the script prints counts and area-size statistics. We then open the result in QGIS and review a few places in Košice with the user, who knows the terrain.
- Municipalities: use `ui/sk_obce_okr_kr_utf8.csv`, filtered to the kraj. Its provenance and accuracy are undocumented, so a sample of its coordinates is verified against OSM place nodes, and the file is regenerated from OSM if it proves unreliable.

### 3. De-Czechify the plugin

- Config: one `data_path` setting (default `~/patracdata`) replaces `getPatracDataPath()` and the drive-letter scans in `patrac.py` and `main/project.py`. The `cr/projekty/simple` lookups and the region `metadata.json` version gate are relaxed or removed.
- Municipality list: switch `places` in the default config to the Slovak CSV.
- Basemaps: replace the ČÚZK WMS entries ([patracdockwidget.py](../../../patracdockwidget.py) around line 2071) with OpenStreetMap, and a Slovak orthophoto WMS if a working public endpoint is verified. The ČÚZK entries are removed from the menu.
- Disable and hide: HS ČR incident creation, users-history API, handler dialog entry points. The code is kept for upstream mergeability.
- Fix macOS-specific issues as found: path separators, `subprocess` calls, the Linux/Windows drive detection in `ui/ui_gpx.py` for GPS devices (macOS mounts under `/Volumes`).
- Messages that say "Out of Czech Republic" become generic.
- Acceptance: create a new project at a Košice-area municipality, see sectors, place a last-seen point, run "calculate area" and see sector percentages, export a sector PDF/GPX.

### 4. GPX analysis

New module `main/analysis.py` with a dialog, reachable from the existing GPX import flow. Input: a folder of GPX files, one per searcher or team. Outputs:

- **Sector coverage %**: for each sector, the area within a configurable distance (default 10 m) of any track, divided by sector area. Geometry work is done in EPSG:5514 so distances are in metres.
- **Gaps layer**: sectors minus the buffered tracks, added to the project as a styled layer.
- **Per-searcher stats**: distance, duration, average speed, start and end time, and the sectors passed through. Shown in a table and exportable to CSV.
- **Remaining probability**: for each sector, `p_remaining = p_prior × (1 − coverage × POD)` normalised across sectors, where `p_prior` is the existing ISRID-style percentage and `POD` is a configurable probability-of-detection (default 0.7). The model is simple and documented as an approximation. It is configurable so the user can tune it.
- Tests: pure-Python functions (buffering, coverage ratio, speed and duration, probability update) are unit-tested without QGIS where possible, using small synthetic tracks and sectors.

## Risks

- OSM coverage and tagging quality in Košický kraj may produce odd sectors (for example large unmapped fields). Mitigation: review with the user and tune the rules and merge thresholds.
- Sector building on a whole kraj may be slow. Mitigation: process by tiles or by the municipality box, and cache.
- A public Slovak orthophoto WMS may need a licence or may not be available. Mitigation: OSM is the default basemap and orthophoto is optional.
- The plugin has about 2000 lines in `patracdockwidget.py`, and Czech assumptions may sit in places the grep missed. Mitigation: sub-project 3 ends with an end-to-end smoke test, and fixes are made as found.
- PROJ's WGS84 to S-JTSK transformation may be less accurate in eastern Slovakia than in the Czech Republic (a few metres). This is acceptable for search planning. It is verified against a known point in Košice.

## Success criteria

On a Mac, with this repo symlinked into QGIS: create a search near a Košický kraj municipality, see sectors with land-use types, compute probability areas from a last-seen point, print or export sectors, then import GPX tracks and get coverage, gaps, per-searcher stats and updated probabilities.
