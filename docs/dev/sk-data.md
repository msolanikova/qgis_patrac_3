# Slovak data pipeline

`tools/sk_data/` builds the data Patrac reads for a region (sectors with a land-use type, roads, forest
tracks, streams and a municipality list) from open data. It runs with QGIS's bundled Python.

Design: [docs/superpowers/specs/2026-10-18-sk-data-pipeline-design.md](../superpowers/specs/2026-10-18-sk-data-pipeline-design.md).

## Before you start

QGIS 3 LTR must be installed and the environment set up as described in `docs/dev/macos-setup.md`. Run every
command from the repository root. `download` needs an internet connection and about 550 MB of disk space.

## Run it

```bash
source tools/dev/qgis_env.sh                      # gives you $QGIS_PY and the right PYTHONPATH
"$QGIS_PY" -m tools.sk_data download --region ke  # OSM extract (~350 MB) + WorldCover tiles (~190 MB), once
"$QGIS_PY" -m tools.sk_data build --region ke     # build into ~/patracdata/kraje/ke and validate it
```

Region keys: `ba tt tn nr za bb po ke` (the eight kraje). Košický kraj takes about 6 minutes with OSM only and
about 20 minutes with WorldCover, and needs 3-8 GB of memory. It is a one-time build.

To look at a single place first, build only a 12 x 10 km window around a point (about 45 seconds):

```bash
"$QGIS_PY" -m tools.sk_data build --region ke --window 21.2611,48.7164 --out "$HOME/patracdata/build/ke-kosice-window"
```

A window has no municipality list (it writes an empty `places.csv`) and must be written to its own `--out` folder.

To regenerate only the municipality list, without rebuilding the sectors, run
`"$QGIS_PY" -m tools.sk_data places --region ke [--out DIR]`. It takes about a minute and writes just `places.csv`
(to `~/patracdata/kraje/<region>` unless `--out` is given), replacing an existing one.

Options of `build`:

| Option | Meaning |
|---|---|
| `--landcover osm+worldcover` (default) | OSM polygons on top of the ESA WorldCover satellite classes, which fill the gaps |
| `--landcover osm` | OSM only. About half of the countryside of Košický kraj stays `OTHER` |
| `--out DIR` | write somewhere other than `~/patracdata/kraje/<region>` |
| `--overwrite` | replace an existing non-empty output folder, but only after the new build validates |
| `--window LON,LAT` | build only a 12 x 10 km area around this point (needs `--out`) |
| `--min-ha 6 --target-ha 7 --max-ha 8` | sector size; the defaults are 60,000-80,000 m2 |

The data folder is `~/patracdata` (override with `$PATRAC_DATA`). Without `--out`, `build --region ke` writes to
`~/patracdata/kraje/ke`, the folder the plugin reads. A relative `--out` is resolved against the current
directory (the repository root), so use `$HOME/...` paths.

### Existing output folders are protected

A build refuses to write into an existing non-empty output folder (it stops at once with exit code 2 and tells
you to pass `--overwrite` or choose another `--out`). The new data is always written to a sibling folder
`<out>.partial-*` and validated there. With `--overwrite` the old folder is replaced only after the new build
validates. When validation fails, the old folder is untouched and the new data stays in the `<out>.partial-*`
folder for inspection (the path is printed); delete it when you no longer need it.

## Service bundle for the SAR Planner

`python -m tools.sk_data service-bundle --region ke --version 2026-11-22 [--out ROOT] [--osm PATH] [--no-roads] [--overwrite]`
cuts the sectors of a built region (`vektor/ZABAGED/sectors.shp`) into 10 km tiles for the SAR Planner, and the roads
and tracks of the region into road tiles (see below). Default `ROOT` is
`<data>/service-bundles` (`~/patracdata/service-bundles`). The layout is `<ROOT>/<region>/<version>/manifest.json`
and `tiles/<tx>_<ty>.jsonl.gz` (one JSON sector per line: id, label, typ, class, area_ha, polygon as WKT in
EPSG:5514, outline in WGS84). A sector goes to the tile of its centroid, `floor(x / 10000)`. The WKT is snapped to
a 1 cm grid with `shapely.set_precision` (plain rounding to 2 decimals made about 6 % of the polygons invalid); the
few sectors with a hairline neck that the 1 cm grid would split are snapped to 0.1 mm and written with 4 decimals.
The manifest is written last and carries the sources from `metadata.json`, the notice from `ATTRIBUTION.txt` and
`coverage_wkt`: the area the region's data covers (union of all sectors, `buffer(100)`, `simplify(100)`, snapped to
whole metres, EPSG:5514), so the SAR Planner can warn when a search area reaches beyond the data. An existing
version is refused (exit code 2, before anything is read); `--overwrite` replaces it only after the new one is complete. The bundle is
data: keep it out of git.

### Road tiles

By default the command also cuts the roads and tracks of the region into `roads/<tx>_<ty>.jsonl.gz` (the same 10 km
tiles; a piece goes to the tile of the midpoint of its line) and adds `"roads": {"count", "tiles", "osm_bytes",
"max_piece_m", "min_piece_m", "built_up_class", "built_up_excluded"}` to the manifest. `--no-roads` leaves them out: the bundle then has no `roads` folder and no
`roads` key. The roads are read from the downloaded OSM file (`<data>/source/osm-slovakia/slovakia-latest.osm.pbf`;
`--osm PATH` uses another file) and not from the built region, so they cost one more pass over that file (the lines
inside the region's bounding box only, filtered by `highway`). A missing file is an error (exit code 2). The sectors come
from the build of the region, the roads from the OSM file at the time of the command: when the file's size differs from
the `sources.osm.bytes` in the region's `metadata.json`, the command logs a warning (the roads and the sectors are from
different OSM snapshots) and the manifest's `osm_bytes` says which file the roads came from.

A line of a road tile has `id` (`r1`, `r2`, ...; unique in the bundle; numbered by the midpoint of the piece, so the
same data gives the same ids; two pieces with exactly the same geometry are ordered by `highway`, `name`, `tracktype`,
`surface`, nulls last), `name` (the OSM `name`, else `ref`, else null), `highway`, `tracktype` and `surface` (as
in OSM or null), `worse` (true or false), `length_m` (one decimal), `wkt` (the line in EPSG:5514, 2 decimals) and
`outline` (its vertices in WGS84, 6 decimals). A piece is the stretch of a road between two junctions, where a
junction is an OSM node shared by two ways (ways that cross without a shared node, a bridge for example, are neither cut
nor joined there). Stretches that meet at a point where exactly two end are joined when `highway`, name, `tracktype`,
`surface` and `worse` agree. A piece belongs to the region when its midpoint lies in the region's polygon; pieces are
not clipped at the border. Pieces in built-up areas are left out (see the guesses below): the command takes the
sectors of plugin class 6 (`roads.BUILT_UP_CLASS`; `AREZAS`, `ARUCZA`, `HRBITO`, `PRSTPR`, `ROZTRA`, `ROZZRI`,
`ULOMIS`, `USNAOD`, `INTRAV` in `rules/classes.json`) from the region's `sectors.shp` and drops every piece, of any road
type, whose midpoint lies within one of them; the manifest records `built_up_class` and `built_up_excluded`.

**Road tiles ship only in a new version.** A case stores the bundle version it was planned on; if roads appeared in
that version later, a re-plan of an older case would find road rows it never had and fail with a conflict. So build
roads into a version name that no case uses yet (`--version 2026-12-01`), and do not use `--overwrite` on a version
that cases were made on.

**Guesses in the road rules** (each is one named constant in `tools/sk_data/roads.py`; the owner may change any):

- Included `highway` values (`INCLUDED_HIGHWAYS`): track, path, bridleway, service, unclassified, residential,
  living_street, tertiary, cycleway, footway. Motorways, trunk, primary and secondary roads (and their links) and steps
  are left out.
- Left out by tag even when the `highway` value is included: a tunnel (`layers.TUNNEL_VALUES`), `footway` sidewalk or
  crossing, traffic_island or access_aisle (`footway=link` stays), `service` parking_aisle, driveway, drive-through or
  emergency_access, `indoor=yes`, `access` no or private (unless `foot` is yes, permissive or designated:
  `ACCESS_FOOT_OVERRIDE`).
- Mountain-grade paths are left out (the owner: "those are searched by the mountain service, not by us"): any way whose
  `sac_scale` is in `EXCLUDED_SAC_SCALES` (demanding_mountain_hiking, alpine_hiking, demanding_alpine_hiking,
  difficult_alpine_hiking), whatever its `highway`. `mountain_hiking` (T2) and `hiking` stay.
- No roads in built-up areas (the owner: "we don't need roads as gpx in built-up areas"): a piece whose midpoint lies
  in a sector of class `BUILT_UP_CLASS = 6` is dropped, all road types. `EXCLUDE_IN_BUILT_UP = False` turns this off.
  A piece that only touches a built-up sector with an end, or crosses one, stays: it is the midpoint that counts.
- "Worse" (`worse: true`): the `highway` is track, path or bridleway (a track of any `tracktype`), or any `;`-separated
  part of `surface` is in `UNPAVED_SURFACES` (unpaved, compacted, fine_gravel, gravel, pebblestone, dirt, earth,
  ground, grass, mud, sand, woodchips, clay, rock, ice, snow, salt).
- Lengths: `MAX_PIECE_M = 5000`, a longer chain is cut into equal parts of at most that length (a chain of exactly 5000 m
  stays whole); `MIN_PIECE_M = 30`, shorter pieces (junction stubs, connectors) are dropped.

Run it (after `build --region ke`, with a version name no case uses):

```bash
source tools/dev/qgis_env.sh
"$QGIS_PY" -m tools.sk_data service-bundle --region ke --version 2026-12-01
```

## Compare two builds in QGIS

```bash
"$QGIS_PY" -m tools.sk_data build --region ke --landcover osm --out "$HOME/patracdata/build/ke-osm"
"$QGIS_PY" -m tools.sk_data build --region ke --landcover osm+worldcover --out "$HOME/patracdata/build/ke-osm-worldcover"
"$QGIS_PY" -m tools.sk_data project --out "$HOME/patracdata/build/ke-compare.qgz" \
    --region-dir "OSM only=$HOME/patracdata/build/ke-osm" \
    --region-dir "OSM + WorldCover=$HOME/patracdata/build/ke-osm-worldcover"
```

Add `--bookmark "NAME=LON,LAT"` (repeatable) to get map bookmarks; the project opens on the first one.

Open `ke-compare.qgz`. It has an OpenStreetMap basemap and one sectors layer per build (tick one at a time).
The sectors are coloured by land-use type with a complete English legend; unclassified land (`OTHER`) is bright
orange, so the places where OSM has no land-use data stand out. The plugin's own style is not used here because
it has no entry for most of our types (built-up, gardens, parks, cemeteries, wetland). QGIS asks once which
coordinate transformation to use for the S-JTSK layers: choose **S-JTSK to WGS 84 (4)**, the one defined for
Slovakia.

## What is written

```
<out>/vektor/ZABAGED/sectors.shp  cesta.shp  lespru.shp  vodtok.shp  lastsectorid.txt
<out>/metadata.json               version the plugin checks, sources, sector size, land-cover mode
<out>/places.csv                  municipality list in the format of the plugin's ui/*.csv
<out>/ATTRIBUTION.txt             OpenStreetMap (ODbL) and ESA WorldCover (CC BY 4.0) notices
```

The folder is called `ZABAGED` only because the plugin looks for that name; the data is not ZABAGED.
`places.csv` columns: `x;y;0;name;0;district;REGION`. The two zero columns are codes the plugin does not read.
The list holds the OSM municipalities (`admin_level=8`) and the two cities that are split into districts,
Košice and Bratislava, which OSM maps as `admin_level=5`.

## Sector names

Every sector in `sectors.shp` has two string fields the plugin needs (`tools/sk_data/naming.py`). The fields are
written in the order `id`, `label`, `typ`: the plugin reads and writes sector attributes by position (`id, label, typ,
stav, prostredky, area_ha, ...`, for example when merging sectors, splitting by grid and in the sector dialog), so another
order would put the type into the id and the id into the label. `tests/test_sector_field_order.py` checks the order
against the plugin source.

- `id`: `"1"` to `"N"`, unique in the file, numbered in reading order (cell row from the south, cell from the west,
  then 500 m bands from the north, west to east inside a band). The plugin gives sectors created by splitting ids from
  1,000,000 upwards (`lastsectorid.txt`), so the file may hold fewer than 1,000,000 sectors; the build refuses more.
- `label`: the visible name, one letter and a number, for example `K142`. Short enough to say over the radio.

The letter comes from a grid of 12 km cells in S-JTSK (about the size of one search project). There are 16 letters,
`ABCDEFGHJKLMNPRS` (no I, O, Q), repeating every 4 cells in x and in y: any 3 x 3 block of cells has 9 different
letters, and two cells with the same letter are at least 4 cells (36 km) apart. The number is a counter that starts at 1
in every cell and follows the same reading order. The cell of a sector is the cell of its `point_on_surface`.
Within one build, any set of sectors whose reference points span less than 36 km (which covers a 12 x 10 km search
project plus margin) has distinct labels. The numbering does not depend on the order the sectors were produced in, only
on their geometry, so a rebuild of unchanged data gives the same names. Ids and labels are unique only within one
build: do not mix or append sectors from different builds or windows in one project, because the counters differ. A
rebuild with a different window or different data changes the counters. The plugin's "extend area" function can grow a
project beyond 36 km, where repeated labels can occur.

Validation reports a problem for: a missing `id` or `label` field; duplicate ids; an id that is not a positive integer
without leading zeros or is 1,000,000 or more; a label that is not one capital letter followed by digits; and two sectors
with the same label whose reference points are closer than 30 km. The report has `id_max` and
`labels` (`max_length` and `duplicated_labels`, the number of labels used more than once).

## Review the guessed mappings

`"$QGIS_PY" -m tools.sk_data rules` lists the OSM tags whose Czech land-use type is a guess. They are
marked `"status": "guess"` in `tools/sk_data/rules/osm_landuse.json`; edit the file to change one. The
WorldCover mapping is in `rules/worldcover.json`, and `rules/classes.json` (typ to the plugin's 10 classes) is
checked against `main/sectors.py` by a test.

Czech codes with no OSM or WorldCover mapping yet: `ODPOCI`, `OSPLSI`, `POTELO`, `CHMELN`, `LPKOSO`, `PRSTPR`,
`ROZTRA`, `ROZZRI`, `USNAOD`, `INTRAV`. Land with these types in the Czech data ends up as one of the
mapped types or `OTHER` here.

## How a sector is made

1. Roads (every class from motorway down to residential streets), railways, rivers/streams/canals and the edges of land-cover polygons are drawn together
   and polygonized into small faces.
2. Each face gets a type: the smallest OSM polygon containing it, else the WorldCover class, else `OTHER`
   (faces that would otherwise be `OTHER` and have at least 8% buildings become `AREZAS`).
3. Faces smaller than the minimum merge with the neighbour of the same plugin class that shares the
   longest border. Tiny faces (< 1 ha) and thin slivers merge into any neighbour.
4. Areas above the maximum are cut into near-equal parts along their long axis.
5. Fragments smaller than 1 ha (left by the cutting) join the neighbour they share the longest border with
   (or the smallest touching neighbour if that would push the sector above the maximum).
   That can push a sector slightly above the maximum, by less than 1 ha; validation allows that and
   reports how many sectors are over the maximum.

## Tests

```bash
source tools/dev/qgis_env.sh
QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest discover -s tests -t .
```

Under plain `python3` the `tests/sk_data` package is skipped (it needs the geo libraries bundled with QGIS).
