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

Every sector in `sectors.shp` has two string fields the plugin needs (`tools/sk_data/naming.py`):

- `id`: `"1"` to `"N"`, unique in the file, numbered in reading order (cell row from the south, cell from the west,
  then 500 m bands from the north, west to east inside a band). The plugin gives sectors created by splitting ids from
  1,000,000 upwards (`lastsectorid.txt`), so the file may hold fewer than 1,000,000 sectors; the build refuses more.
- `label`: the visible name, one letter and a number, for example `K142`. Short enough to say over the radio.

The letter comes from a grid of 12 km cells in S-JTSK (about the size of one search project). There are 16 letters,
`ABCDEFGHJKLMNPRS` (no I, O, Q), repeating every 4 cells in x and in y: any 3 x 3 block of cells has 9 different
letters, and two cells with the same letter are at least 4 cells (36 km) apart. The number is a counter that starts at 1
in every cell and follows the same reading order. The cell of a sector is the cell of its `point_on_surface`.
So a search area never contains two sectors with the same label, wherever it is placed. The numbering does not depend on
the order the sectors were produced in, only on their geometry, so a rebuild of unchanged data gives the same names.

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
