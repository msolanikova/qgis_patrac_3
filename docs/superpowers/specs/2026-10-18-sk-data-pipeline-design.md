# Slovak data pipeline (sub-project 2): design

Date: 2026-10-18
Branch: `feature/sk-data-pipeline`
Parent spec: [2026-10-18-slovakia-macos-port-design.md](2026-10-18-slovakia-macos-port-design.md) (sub-project 2). This document refines it using the results of a spike on real data.

## Goal

A command-line tool that turns open data into the files Patrac reads for a region, first for Košický kraj and later for any Slovak region: search sectors with a land-use type, roads, forest tracks and streams, plus a municipality list. It runs with QGIS's bundled Python, so no extra geo software is installed.

## What the spike showed (all numbers are from real data)

- OSM sector building works. A 12 × 10 km box around Košice takes 4 s. The whole of Košický kraj takes 4.3 min and 3.2 GB in a single pass, so tiling and seam handling are not needed.
- The user judged the borders and land-use colours in Košice as matching the ground, and asked for sectors of 60,000–80,000 m² (6–8 ha). The kraj-wide result has 109,794 sectors, a median of 7.0 ha, and 78% of sectors (88% of area) in 6–8 ha.
- OSM land-use mapping is incomplete in the countryside. About 50% of the kraj has no OSM land-use polygon (it is 23% in the Košice box), and OSM forest is only 12% of the area while the real figure is much higher.
- ESA WorldCover 2021 (10 m satellite classes, CC BY 4.0, free download, no login) agrees with OSM where OSM has labels: forest 99%, arable 89%, grass 84%, water 82%. For the areas OSM leaves unlabelled it says 69% tree cover, 24% cropland, 7% grass.
- PROJ's area-aware default for Slovakia is EPSG:4836 "S-JTSK to WGS 84 (4)" (1 m, defined for Slovakia). The generic fallback (3) differs by about 10 m at Košice.

## Decisions

| Topic | Decision |
|---|---|
| Land-cover sources | OSM polygons (high priority) over ESA WorldCover (base layer, fills gaps). A switch `--landcover osm\|osm+worldcover` allows the user to compare both after the full kraj is built. Default: `osm+worldcover`. |
| Sector size | Configurable `min/target/max` in hectares. Default 6 / 7 / 8 (user request). |
| Typ codes | Keep the Czech ZABAGED-style codes (`LPSTROM`, `ORNAPU`, `AREZAS`, …). The plugin's styles and reports use them. |
| Merge rule | Merge small faces only within the same plugin class (the 10 classes in `main/sectors.py:getReportItems`), then label the result by the type with the largest area. Thin slivers (< 5 ha, compactness < 0.1) and faces < 1 ha merge into any neighbour. |
| Split rule | Areas above the maximum are cut into near-equal parts (balanced area, along the long axis), not repeatedly halved. |
| Runtime | QGIS's Python (`$QGIS_PY`): shapely, geopandas, pyproj, numpy and GDAL are already there. Tests use `unittest`. |
| Transformation | Pin EPSG:4836 for WGS84 to S-JTSK in the pipeline and test it against Košice. |
| CRS | EPSG:5514 (S-JTSK), as in the plugin. |
| Regions | Region key is the lower-case ISO 3166-2 suffix: `ba tt tn nr za bb po ke`. Boundaries come from OSM `admin_level=4` relations. |

## Layout

```
tools/sk_data/
  __main__.py          # CLI: python -m tools.sk_data <command> ...
  config.py            # region table, sector size defaults, paths (default ~/patracdata)
  download.py          # fetch Geofabrik extract and WorldCover tiles; record URL, date, sha256
  extract.py           # OSM -> lines/polygons/boundaries for a region (GDAL OSM driver)
  rules/
    osm_landuse.json   # OSM tag -> typ, each entry marked "verified" or "guess"
    worldcover.json    # WorldCover class -> typ
    classes.json       # typ -> plugin class 1..10 (copied from the plugin's report code)
  landcover.py         # cover polygons: OSM on top, WorldCover base underneath
  sectors.py           # polygonize, type, merge, split (pure functions, unit-tested)
  layers.py            # cesta / lespru / vodtok from OSM lines
  places.py            # municipality CSV in the plugin's format
  export.py            # shapefiles, lastsectorid.txt, metadata.json, ATTRIBUTION.txt
  validate.py          # checks the output (see Validation)
  qgis_project.py      # builds a .qgz to inspect a result, with the plugin's styles and an OSM basemap
tests/sk_data/         # unit tests; integration test on a small bbox when the extract exists
docs/dev/sk-data.md    # how to run it, what each file means
```

## Pipeline

1. `download`: Geofabrik `slovakia-latest.osm.pbf` and the WorldCover tiles that cover the region (N48E018, N48E021 for `ke`) into `~/patracdata/source/`.
2. `extract`: cut OSM to the region boundary plus an 800 m margin.
3. `landcover`: OSM cover polygons from the rules file, minimum area 0.25 ha. WorldCover is sieved (regions under 0.25 ha removed), polygonized, and reduced to the part not covered by OSM polygons.
4. `sectors`: lines (main roads, railways, rivers/streams/canals, edges of cover polygons, region margin) are noded and polygonized into faces. Each face gets the type of the smallest cover polygon containing a representative point. Unlabelled faces with at least 8% building coverage become `AREZAS`. Then merge, then split, then keep sectors whose representative point is inside the region boundary.
5. `layers`: `cesta` (highways), `lespru` (tracks and paths in forest), `vodtok` (waterways) in the region.
6. `places`: municipality list as `x;y;code;name;okres_code;okres_name;KE` from OSM municipality boundaries and place nodes, coordinates in S-JTSK.
7. `export`: write `~/patracdata/kraje/<key>/vektor/ZABAGED/{sectors,cesta,lespru,vodtok}.shp`, `lastsectorid.txt` (1000000, the plugin's own fallback), `kraje/<key>/metadata.json` (`"version": "2020-01-01"`, source versions) and `ATTRIBUTION.txt`. The directory name `ZABAGED` is kept so the plugin works unchanged; sub-project 3 may rename it.

## Validation

`validate` fails the run if any of these is false:

- `sectors.shp` is EPSG:5514, has a string field `typ` whose values all appear in `classes.json`, and every geometry is a valid polygon.
- Sector areas sum to the region area within 0.5%, and sectors do not overlap (total area equals the area of their union within 0.1%).
- No sector above the configured maximum; the share of sectors inside `[min, max]` is reported.
- `lastsectorid.txt` holds an integer and `metadata.json` has the version the plugin expects.
- The Košice test point transforms to S-JTSK within 1 m of the EPSG:4836 result.

Printed report: sector count, area percentiles, area per `typ`, share of `OTHER`, and the same figures for `osm` versus `osm+worldcover` when both were built.

## Licences and attribution

OpenStreetMap data is ODbL (© OpenStreetMap contributors). ESA WorldCover 2021 is CC BY 4.0 (© ESA WorldCover project 2021, contains modified Copernicus Sentinel data processed by the ESA WorldCover consortium). Every output folder carries `ATTRIBUTION.txt` with both, and `metadata.json` records the source files and download dates. The data is for the user's own use; publishing derived data would need ODbL share-alike handling.

## Known uncertainties

- Some Czech type codes have no documented OSM or WorldCover equivalent (`MAZCHU`, `POTELO`, `INTRAV`, `USNAOD`, `PRSTPR`, `ROZTRA`, `ROZZRI`, `OSPLSI`, `ODPOCI`). They are marked `"guess"` in the rules and listed in the docs so the user can correct them.
- `lespru` ("průseky") has no direct OSM tag. The first version uses `highway=track|path|bridleway` inside forest sectors.
- `lastsectorid.txt` semantics for Czech data are unknown; the value 1000000 follows the plugin's fallback when the file is missing or invalid.
- ZBGIS (official Slovak data) is not used; the rules-file design allows it later.

## Out of scope

Plugin changes (reading the new municipality list, the Slovak transformation in the plugin, basemaps, the `ZABAGED` folder name): sub-project 3. Terrain and DEM. Other regions than Košický kraj in this plan (the code is region-agnostic and the other seven kraje can be run afterwards). The GPX analysis: sub-project 4.

## Acceptance

1. `python -m tools.sk_data build --region ke` runs from a clean checkout, given the downloads, and `validate` passes.
2. The user opens the generated QGIS project and compares `osm` with `osm+worldcover`, then decides which stays as the default. This is the planned re-evaluation after Košický kraj is complete.
3. Unit tests pass under QGIS's Python.
