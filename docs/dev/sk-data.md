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

Options of `build`:

| Option | Meaning |
|---|---|
| `--landcover osm+worldcover` (default) | OSM polygons on top of the ESA WorldCover satellite classes, which fill the gaps |
| `--landcover osm` | OSM only. About half of the countryside of Košický kraj stays `OTHER` |
| `--out DIR` | write somewhere other than `~/patracdata/kraje/<region>` |
| `--window LON,LAT` | build only a 12 x 10 km area around this point (needs `--out`) |
| `--min-ha 6 --target-ha 7 --max-ha 8` | sector size; the defaults are 60,000-80,000 m2 |

The data folder is `~/patracdata` (override with `$PATRAC_DATA`).

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
