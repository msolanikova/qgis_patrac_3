# Slovak Data Pipeline Implementation Plan (sub-project 2 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A command-line tool, `python -m tools.sk_data`, that builds the data Patrac reads for a Slovak region (sectors with land-use types, roads, forest tracks, streams, municipality list) from OpenStreetMap and ESA WorldCover, validated against what the plugin expects, and then builds Košický kraj with it.

**Architecture:** Small modules with one job each in `tools/sk_data/`, working on shapely geometries in EPSG:5514: extract OSM, build land-cover polygons (OSM on top of WorldCover), polygonize roads/rails/streams/cover edges into faces, type them, merge small faces within the plugin's land-use classes, split large ones into near-equal parts, write the plugin's folder layout, validate. Land-use rules are JSON files. The code was prototyped on the real data (Košice box and the whole kraj) and every file below passed its tests before being put in this plan.

**Tech Stack:** QGIS 3.44 LTR's bundled Python 3.12 (`$QGIS_PY`) with shapely 2, geopandas, pyproj, numpy and GDAL; `unittest`.

**Spec:** [docs/superpowers/specs/2026-10-18-sk-data-pipeline-design.md](../specs/2026-10-18-sk-data-pipeline-design.md)

## Global Constraints

- Work only on branch `feature/sk-data-pipeline`. Never commit to `master`. Never push or merge.
- Every commit message ends with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Commit with explicit paths, never `git add -A`.
- Run Python with QGIS's interpreter: `source tools/dev/qgis_env.sh` then `"$QGIS_PY"`. Do not run it with `-I`.
- Full test command, from the repository root: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -W error::ResourceWarning -m unittest discover -s tests -t .`. Tests use `unittest` only. Under plain `python3` the `tests/sk_data` package must be skipped, not fail.
- Sector size defaults are `min/target/max = 6 / 7 / 8` hectares (the user's request: 60,000-80,000 m2), configurable.
- Keep the Czech ZABAGED-style `typ` codes (`LPSTROM`, `ORNAPU`, `AREZAS`, …); `rules/classes.json` must equal the `types` table in `main/sectors.py:getReportItems` (a test checks it).
- Output CRS is EPSG:5514. WGS84 to S-JTSK uses the pinned operation EPSG:4836 "S-JTSK to WGS 84 (4)" (Košice must come out within 0.5 m of x -262580.66, y -1240038.58).
- Output layout: `<out>/vektor/ZABAGED/{sectors,cesta,lespru,vodtok}.shp`, `lastsectorid.txt` (1000000), `<out>/metadata.json` (`"version": "2020-01-01"`), `<out>/ATTRIBUTION.txt`, `<out>/places.csv`. Default `<out>` is `~/patracdata/kraje/<key>`. Region keys: `ba tt tn nr za bb po ke`.
- Do not change plugin code (`patrac.py`, `patracdockwidget.py`, `main/`, `ui/`) in this plan; that is sub-project 3.
- Downloaded data goes under `~/patracdata/source/`, never into the repository. Every output folder carries the OpenStreetMap (ODbL) and WorldCover (CC BY 4.0) attribution.

## Changes from the spec found while prototyping

- **WorldCover is not subtracted from OSM polygons.** The spec said the base layer is "reduced to the part not covered by OSM". Cutting 500,000 satellite polygons against the OSM union is far too slow. Instead both layers contribute boundary lines, a face is typed by OSM first and WorldCover second, and the merge step folds the extra small faces back together.
- **Split rule:** the spike rounded area / target to get the part count, which left 8-10.5 ha areas whole although the maximum is 8 ha. The rule is now "the fewest near-equal parts that keep every part under 98% of the maximum, or one more if that is closer to the target" (`_parts_for`).
- **Municipality list:** OSM Slovakia has municipality (`admin_level=8`) and district (`admin_level=6`) boundaries but no official municipality codes, so `places.csv` has placeholders `0` in the two code columns, which the plugin does not read (it uses columns 0, 1, 3, 5 and 6).
- **Validation:** area tolerance defaults to 2% (the whole kraj was off by 0.08% in the spike; a tiny test region is off by more), and the report always shows `area_ratio`. The size limit is the maximum plus `tiny_ha` (see the next point); the report shows `sectors_over_max` and `sectors_under_tiny`.
- **Tiny sectors:** the first whole-kraj run left 10,410 sectors under 1 ha (4,728 under 0.01 ha), all touching a bigger sector. Two causes, both fixed: (1) faces were only treated as neighbours when they shared at least 3 m of border, so 1-4 m2 slivers between nearly coincident OSM and satellite edges had no neighbours; tiny faces now merge into any touching neighbour (`MIN_CONTACT_M`), while ordinary merges keep the 3 m rule; (2) cutting clips small corner fragments off split pieces; the new `absorb_fragments` pass joins each into a touching sector, which can push a sector above the maximum by less than `tiny_ha`. After the fixes, two real 12 x 10 km windows had zero sectors under 1 ha.
- **Valid polygons:** the second whole-kraj run failed validation: 4 of 109,978 sectors were invalid MultiPolygons after being written to a shapefile and read back. Each contained a degenerate ring (four points, two distinct: a zero-width spike) that GEOS treats as a hole in memory but a shapefile reader turns into a nested shell. A first guess (unions along very short contacts) was wrong: it changed nothing in the next run. The fix is a final cleaning pass `finalize_sectors` that every sector goes through (repair invalid geometries, drop specks under 1 m2 and degenerate holes, split real multi-part sectors into separate sectors), plus `_union`, which accepts only one valid polygon when joining pieces, plus a guard in `export.sectors_frame` that refuses invalid or multi-part geometries. The validator still reads the written shapefile, so it checks the round trip.
- **Work folder:** each build extracts into its own temporary folder under `<data>/work` and removes it afterwards. A shared cache folder made two parallel builds of the same region corrupt each other (a crash seen in testing), and extraction takes under a minute, so the cache saved almost nothing.
- **Window mode (new):** `build --window LON,LAT --out DIR` builds only a 12 x 10 km area around a point in about 45 s, using its own work folder. It exists for quick inspection and for fast experiments on real data.

## File Structure

| File | Responsibility |
|---|---|
| `tools/__init__.py`, `tools/sk_data/__init__.py` | package markers |
| `tools/sk_data/config.py` | region table, `SectorSize`, data paths |
| `tools/sk_data/rules.py`, `rules/*.json` | OSM tag / WorldCover class -> `typ`; `typ` -> plugin class |
| `tools/sk_data/sectors.py` | polygonize, type, merge, split (pure geometry) |
| `tools/sk_data/crs.py` | pinned WGS84 -> S-JTSK transformation |
| `tools/sk_data/download.py` | fetch Geofabrik and WorldCover files, manifest |
| `tools/sk_data/extract.py` | read OSM with GDAL: boundary, lines, polygons, points |
| `tools/sk_data/landcover.py` | OSM cover polygons and WorldCover polygons |
| `tools/sk_data/layers.py` | barrier lines; cesta / lespru / vodtok |
| `tools/sk_data/places.py` | municipality list |
| `tools/sk_data/export.py` | write the plugin's folder layout |
| `tools/sk_data/validate.py` | checks and report |
| `tools/sk_data/pipeline.py` | `build_region` orchestration |
| `tools/sk_data/__main__.py` | command line |
| `tools/sk_data/qgis_project.py` | QGIS project to inspect results |
| `tests/sk_data/…` | unit tests and a pipeline test on a tiny OSM fixture |
| `docs/dev/sk-data.md` | how to run it |

---

### Task 1: Package, configuration and land-use rules

**Files:**
- Create: `tools/__init__.py`, `tools/sk_data/__init__.py`, `tools/sk_data/config.py`, `tools/sk_data/rules.py`, `tools/sk_data/rules/classes.json`, `tools/sk_data/rules/worldcover.json`, `tools/sk_data/rules/osm_landuse.json`
- Create: `tests/sk_data/__init__.py`, `tests/sk_data/test_config_rules.py`

**Interfaces:**
- Produces: `config.REGIONS: dict[str, str]`, `config.MARGIN_M: float`, `config.SectorSize` (frozen dataclass with `min_ha target_ha max_ha tiny_ha sliver_max_ha sliver_compactness building_share min_cover_m2` and properties `min_m2 target_m2 max_m2 tiny_m2 sliver_max_m2`), `config.data_root(environ=None, home=None) -> str`, `config.source_dir(root, *parts)`, `config.region_dir(root, key)`.
- Produces: `rules.Rules(osm, worldcover, classes)`, `rules.load_rules(rules_dir=RULES_DIR)`, `rules.osm_typ(rules, tags) -> str | None`, `rules.guessed_rows(rules)`, `rules.guessed_rules_text(rules=None) -> str`, `rules.check_rules(rules) -> list[str]`.

- [ ] **Step 1: Create the package markers and the tests**

Create `tools/__init__.py` and `tools/sk_data/__init__.py` (the second with the content below); `tools/__init__.py` is empty.

Create `tools/sk_data/__init__.py`:

```python
"""Pipeline that builds Patrac region data for Slovakia from OpenStreetMap and ESA WorldCover."""
```

Create `tests/sk_data/__init__.py`:

```python
"""Tests of tools/sk_data. They need the geo libraries bundled with QGIS (shapely, geopandas, pyproj, GDAL)."""

import unittest

try:
    import geopandas  # noqa: F401
    import osgeo  # noqa: F401
    import pyproj  # noqa: F401
    import shapely  # noqa: F401
except ImportError as error:
    raise unittest.SkipTest("sk_data tests need QGIS's Python (source tools/dev/qgis_env.sh): %s" % error)
```

Create `tests/sk_data/test_config_rules.py`:

```python
import ast
import unittest
from pathlib import Path

from tools.sk_data.config import MARGIN_M, REGIONS, SectorSize, data_root, region_dir, source_dir
from tools.sk_data.rules import check_rules, guessed_rows, load_rules, osm_typ

REPO = Path(__file__).resolve().parents[2]


class ConfigTest(unittest.TestCase):
    def test_regions_cover_the_eight_kraje(self):
        self.assertEqual(sorted(REGIONS), ["ba", "bb", "ke", "nr", "po", "tn", "tt", "za"])
        self.assertEqual(REGIONS["ke"], "Košický kraj")

    def test_sector_size_defaults_are_the_user_request(self):
        s = SectorSize()
        self.assertEqual((s.min_ha, s.target_ha, s.max_ha), (6.0, 7.0, 8.0))
        self.assertEqual(s.max_m2, 80000.0)
        self.assertEqual(s.min_m2, 60000.0)

    def test_sector_size_rejects_inconsistent_values(self):
        with self.assertRaises(ValueError):
            SectorSize(min_ha=9.0, target_ha=7.0, max_ha=8.0)

    def test_paths(self):
        self.assertEqual(data_root(environ={"PATRAC_DATA": "/x/pd"}, home="/h"), "/x/pd")
        self.assertEqual(data_root(environ={}, home="/h"), "/h/patracdata")
        self.assertEqual(source_dir("/r", "osm"), "/r/source/osm")
        self.assertEqual(region_dir("/r", "ke"), "/r/kraje/ke")
        self.assertEqual(MARGIN_M, 800.0)


class RulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules()

    def test_rules_are_consistent(self):
        self.assertEqual(check_rules(self.rules), [])

    def test_osm_examples(self):
        r = self.rules
        self.assertEqual(osm_typ(r, {"landuse": "forest"}), "LPSTROM")
        self.assertEqual(osm_typ(r, {"natural": "wood"}), "LPSTROM")
        self.assertEqual(osm_typ(r, {"landuse": "farmland", "natural": "wood"}), "ORNAPU")  # first matching row wins
        self.assertEqual(osm_typ(r, {"water": "lake"}), "VODPLO")                          # '*' matches any value
        self.assertIsNone(osm_typ(r, {"highway": "residential"}))

    def test_worldcover_covers_every_class_value(self):
        self.assertEqual(sorted(self.rules.worldcover), [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100])
        self.assertEqual(self.rules.worldcover[10], "LPSTROM")

    def test_guesses_are_listed_for_review(self):
        guesses = {(r["key"], r["value"]) for r in guessed_rows(self.rules)}
        self.assertIn(("natural", "wetland"), guesses)
        self.assertNotIn(("landuse", "forest"), guesses)

    def test_classes_match_the_plugin_report_code(self):
        """classes.json must agree with the `types` table in main/sectors.py getReportItems."""
        tree = ast.parse((REPO / "main" / "sectors.py").read_text(encoding="utf-8"))
        func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "getReportItems")
        assign = next(n for n in ast.walk(func) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "types")
        plugin = {}
        for cls, codes in enumerate(ast.literal_eval(assign.value), start=1):
            for code in codes:
                plugin[code] = cls
        self.assertEqual(self.rules.classes, plugin)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest tests.sk_data.test_config_rules 2>&1 | tail -5`
Expected: errors with `ModuleNotFoundError: No module named 'tools.sk_data.config'`.

- [ ] **Step 3: Create the modules and rules files**

Create `tools/sk_data/config.py`:

```python
# -*- coding: utf-8 -*-
"""Region table, sector-size settings and data locations for the Slovak data pipeline."""

import os
from dataclasses import dataclass

# Region key (lower-case ISO 3166-2:SK suffix, also the folder name under kraje/) -> OSM name of the admin_level=4 relation
REGIONS = {
    "ba": "Bratislavský kraj",
    "tt": "Trnavský kraj",
    "tn": "Trenčiansky kraj",
    "nr": "Nitriansky kraj",
    "za": "Žilinský kraj",
    "bb": "Banskobystrický kraj",
    "po": "Prešovský kraj",
    "ke": "Košický kraj",
}

MARGIN_M = 800.0  # data is cut this far outside the region so that sectors at the border are complete


@dataclass(frozen=True)
class SectorSize:
    """Sector size targets in hectares and the other thresholds of the sector builder."""
    min_ha: float = 6.0
    target_ha: float = 7.0
    max_ha: float = 8.0
    tiny_ha: float = 1.0           # faces smaller than this merge into any neighbour
    sliver_max_ha: float = 5.0     # thin faces up to this size merge into any neighbour
    sliver_compactness: float = 0.10
    building_share: float = 0.08   # unlabelled faces with this share of buildings become AREZAS
    min_cover_m2: float = 2500.0   # land-cover polygons smaller than this create no boundaries

    def __post_init__(self):
        if not 0 < self.min_ha <= self.target_ha <= self.max_ha:
            raise ValueError("need 0 < min_ha <= target_ha <= max_ha, got %s/%s/%s" % (self.min_ha, self.target_ha, self.max_ha))

    @property
    def min_m2(self):
        return self.min_ha * 1e4

    @property
    def target_m2(self):
        return self.target_ha * 1e4

    @property
    def max_m2(self):
        return self.max_ha * 1e4

    @property
    def tiny_m2(self):
        return self.tiny_ha * 1e4

    @property
    def sliver_max_m2(self):
        return self.sliver_max_ha * 1e4


def data_root(environ=None, home=None):
    """Patrac data folder (default ~/patracdata, override with $PATRAC_DATA), without a trailing slash."""
    from patrac_paths import default_data_path
    return default_data_path(environ, home).rstrip("/")


def source_dir(root, *parts):
    return os.path.join(root, "source", *parts)


def region_dir(root, key):
    return os.path.join(root, "kraje", key)
```

Create `tools/sk_data/rules.py`:

```python
# -*- coding: utf-8 -*-
"""Land-use rules: OSM tags and ESA WorldCover classes -> sector type ('typ'), and typ -> plugin class."""

import json
from dataclasses import dataclass
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent / "rules"


@dataclass(frozen=True)
class Rules:
    osm: tuple          # rows {"key", "value", "typ", "status"}, first match wins
    worldcover: dict    # int class value -> typ
    classes: dict       # typ -> plugin class 1..10


def load_rules(rules_dir=RULES_DIR):
    rules_dir = Path(rules_dir)

    def read(name):
        with open(rules_dir / name, encoding="utf-8") as f:
            return json.load(f)

    return Rules(
        osm=tuple(read("osm_landuse.json")["rows"]),
        worldcover={int(k): v for k, v in read("worldcover.json")["classes"].items()},
        classes=read("classes.json"),
    )


def osm_typ(rules, tags):
    """Sector type for a dict of OSM tags, or None when no rule matches."""
    for row in rules.osm:
        value = tags.get(row["key"])
        if value is None:
            continue
        if row["value"] == "*" or value == row["value"]:
            return row["typ"]
    return None


def guessed_rows(rules):
    """OSM rows that are marked as guesses, for review."""
    return [r for r in rules.osm if r.get("status") == "guess"]


def check_rules(rules):
    """List of problems in the rules (empty when they are consistent)."""
    problems = []
    for row in rules.osm:
        if row["typ"] not in rules.classes:
            problems.append("OSM rule %s=%s -> unknown typ %s" % (row["key"], row["value"], row["typ"]))
        if row.get("status") not in ("verified", "guess"):
            problems.append("OSM rule %s=%s has status %r" % (row["key"], row["value"], row.get("status")))
    for cls, typ in rules.worldcover.items():
        if typ not in rules.classes:
            problems.append("WorldCover class %s -> unknown typ %s" % (cls, typ))
    for typ, cls in rules.classes.items():
        if not 1 <= cls <= 10:
            problems.append("typ %s has class %s outside 1..10" % (typ, cls))
    return problems


def guessed_rules_text(rules=None):
    """Human-readable list of the OSM mappings marked as guesses."""
    rules = rules or load_rules()
    lines = ["OSM mappings marked as guesses (check them against the ground):"]
    lines += ["  %s=%s -> %s" % (r["key"], r["value"], r["typ"]) for r in guessed_rows(rules)]
    return "\n".join(lines)
```

Create `tools/sk_data/rules/classes.json`:

```json
{
  "TRTRPO": 1, "ODPOCI": 1, "OSPLSI": 1,
  "ORNAPU": 2, "SADZAH": 2,
  "KOLEJI": 3, "POTELO": 3, "SKLADK": 3,
  "LPSTROM": 4, "VINICE": 4, "CHMELN": 4,
  "LPKOSO": 5, "LPKROV": 5, "MAZCHU": 5,
  "AREZAS": 6, "ARUCZA": 6, "HRBITO": 6, "PRSTPR": 6, "ROZTRA": 6, "ROZZRI": 6, "ULOMIS": 6, "USNAOD": 6, "INTRAV": 6,
  "ZAHPAR": 7,
  "VODPLO": 9,
  "ELEKTR": 10, "LETISTE": 10, "OTHER": 10
}
```

Create `tools/sk_data/rules/worldcover.json`:

```json
{
  "source": "ESA WorldCover 2021 v200 class value -> typ",
  "classes": {
    "10": "LPSTROM",
    "20": "LPKROV",
    "30": "TRTRPO",
    "40": "ORNAPU",
    "50": "AREZAS",
    "60": "OTHER",
    "70": "OTHER",
    "80": "VODPLO",
    "90": "MAZCHU",
    "95": "OTHER",
    "100": "OTHER"
  }
}
```

Create `tools/sk_data/rules/osm_landuse.json`:

```json
{
 "comment": "First matching row wins. status 'guess' = a mapping the author could not confirm; review these.",
 "rows": [
  {
   "key": "landuse",
   "value": "forest",
   "typ": "LPSTROM",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "farmland",
   "typ": "ORNAPU",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "meadow",
   "typ": "TRTRPO",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "grass",
   "typ": "TRTRPO",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "village_green",
   "typ": "TRTRPO",
   "status": "guess"
  },
  {
   "key": "landuse",
   "value": "orchard",
   "typ": "SADZAH",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "allotments",
   "typ": "SADZAH",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "vineyard",
   "typ": "VINICE",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "residential",
   "typ": "AREZAS",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "commercial",
   "typ": "AREZAS",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "retail",
   "typ": "AREZAS",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "garages",
   "typ": "AREZAS",
   "status": "guess"
  },
  {
   "key": "landuse",
   "value": "construction",
   "typ": "AREZAS",
   "status": "guess"
  },
  {
   "key": "landuse",
   "value": "religious",
   "typ": "AREZAS",
   "status": "guess"
  },
  {
   "key": "landuse",
   "value": "education",
   "typ": "ARUCZA",
   "status": "guess"
  },
  {
   "key": "landuse",
   "value": "institutional",
   "typ": "ARUCZA",
   "status": "guess"
  },
  {
   "key": "landuse",
   "value": "industrial",
   "typ": "ARUCZA",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "military",
   "typ": "ARUCZA",
   "status": "guess"
  },
  {
   "key": "landuse",
   "value": "cemetery",
   "typ": "HRBITO",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "railway",
   "typ": "KOLEJI",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "landfill",
   "typ": "SKLADK",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "quarry",
   "typ": "ULOMIS",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "basin",
   "typ": "VODPLO",
   "status": "verified"
  },
  {
   "key": "landuse",
   "value": "reservoir",
   "typ": "VODPLO",
   "status": "verified"
  },
  {
   "key": "natural",
   "value": "wood",
   "typ": "LPSTROM",
   "status": "verified"
  },
  {
   "key": "natural",
   "value": "scrub",
   "typ": "LPKROV",
   "status": "verified"
  },
  {
   "key": "natural",
   "value": "heath",
   "typ": "LPKROV",
   "status": "guess"
  },
  {
   "key": "natural",
   "value": "grassland",
   "typ": "TRTRPO",
   "status": "verified"
  },
  {
   "key": "natural",
   "value": "wetland",
   "typ": "MAZCHU",
   "status": "guess"
  },
  {
   "key": "natural",
   "value": "water",
   "typ": "VODPLO",
   "status": "verified"
  },
  {
   "key": "leisure",
   "value": "park",
   "typ": "ZAHPAR",
   "status": "verified"
  },
  {
   "key": "leisure",
   "value": "garden",
   "typ": "ZAHPAR",
   "status": "verified"
  },
  {
   "key": "leisure",
   "value": "playground",
   "typ": "ZAHPAR",
   "status": "guess"
  },
  {
   "key": "leisure",
   "value": "pitch",
   "typ": "ZAHPAR",
   "status": "guess"
  },
  {
   "key": "leisure",
   "value": "sports_centre",
   "typ": "ZAHPAR",
   "status": "guess"
  },
  {
   "key": "leisure",
   "value": "stadium",
   "typ": "ZAHPAR",
   "status": "guess"
  },
  {
   "key": "amenity",
   "value": "school",
   "typ": "ARUCZA",
   "status": "guess"
  },
  {
   "key": "amenity",
   "value": "university",
   "typ": "ARUCZA",
   "status": "guess"
  },
  {
   "key": "amenity",
   "value": "college",
   "typ": "ARUCZA",
   "status": "guess"
  },
  {
   "key": "amenity",
   "value": "hospital",
   "typ": "ARUCZA",
   "status": "guess"
  },
  {
   "key": "amenity",
   "value": "kindergarten",
   "typ": "ARUCZA",
   "status": "guess"
  },
  {
   "key": "aeroway",
   "value": "aerodrome",
   "typ": "LETISTE",
   "status": "verified"
  },
  {
   "key": "power",
   "value": "plant",
   "typ": "ELEKTR",
   "status": "verified"
  },
  {
   "key": "water",
   "value": "*",
   "typ": "VODPLO",
   "status": "verified"
  },
  {
   "key": "waterway",
   "value": "riverbank",
   "typ": "VODPLO",
   "status": "verified"
  }
 ]
}
```

- [ ] **Step 4: Add a test for the guess list, then run all tests**

Append this test method to `class RulesTest` in `tests/sk_data/test_config_rules.py` (before the `if __name__` line):

```python
    def test_guess_report_text(self):
        from tools.sk_data.rules import guessed_rules_text
        text = guessed_rules_text()
        self.assertIn("natural=wetland -> MAZCHU", text)
        self.assertNotIn("landuse=forest", text)
```

Run: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest tests.sk_data.test_config_rules 2>&1 | tail -4`
Expected: `Ran 10 tests ... OK`. Also run plain Python: `python3 -m unittest discover -s tests -t . 2>&1 | tail -4`. Expected: OK, with the `sk_data` package skipped.

- [ ] **Step 5: Commit**

```bash
git add tools/__init__.py tools/sk_data tests/sk_data
git commit -m "Add sk_data package skeleton, region config and land-use rules

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Sector builder

**Files:**
- Create: `tools/sk_data/sectors.py`, `tests/sk_data/test_sectors.py`

**Interfaces:**
- Consumes: `config.SectorSize`, `rules.load_rules().classes` (typ -> class).
- Internal helpers used by tests: `_union(a, b) -> Polygon | None` (one valid polygon or None) and `_single_polygon(geom)`.
- Produces: `polygonize_faces(barrier_lines, boundary_lines, margin) -> list[Polygon]`; `assign_types(faces, osm_cover, base_cover, buildings, size) -> list[str]` (cover arguments are GeoDataFrames with `typ` and geometry); `merge_faces(faces, types, size, classes) -> list[(geometry, typ)]`; `split_oversized(sectors, size) -> list[(Polygon, typ)]`; `absorb_fragments(sectors, size) -> list[(geometry, typ)]`; `select_inside(sectors, region)`; `build_sectors(barrier_lines, boundary_lines, margin, region, osm_cover, base_cover, buildings, size, classes) -> list[(Polygon, typ)]`.

- [ ] **Step 1: Write the tests**

Create `tests/sk_data/test_sectors.py`:

```python
import unittest

import geopandas as gpd
import shapely
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from tools.sk_data.config import SectorSize
from tools.sk_data.rules import load_rules
from tools.sk_data.sectors import (_single_polygon, _union, absorb_fragments, assign_types, build_sectors,
                                   finalize_sectors, merge_faces, polygonize_faces, select_inside, split_oversized)

SIZE = SectorSize()
CLASSES = load_rules().classes
HA = 1e4


def square(x, y, ha):
    side = (ha * HA) ** 0.5
    return box(x, y, x + side, y + side)


def row_of_squares(n, ha):
    """n adjacent squares of `ha` hectares each, left to right."""
    side = (ha * HA) ** 0.5
    return [box(i * side, 0, (i + 1) * side, side) for i in range(n)]


def cover(typ, *geoms):
    return gpd.GeoDataFrame({"typ": [typ] * len(geoms)}, geometry=list(geoms), crs=5514)


def empty_cover():
    return gpd.GeoDataFrame({"typ": []}, geometry=[], crs=5514)


class PolygonizeTest(unittest.TestCase):
    def test_one_line_cuts_the_margin_into_two_faces(self):
        margin = box(0, 0, 200, 100)
        faces = polygonize_faces([LineString([(100, -10), (100, 110)])], [], margin)
        self.assertEqual(len(faces), 2)
        self.assertAlmostEqual(sum(f.area for f in faces), 20000.0, places=3)

    def test_faces_outside_the_margin_are_dropped(self):
        margin = box(0, 0, 100, 100)
        outside = box(500, 500, 600, 600).boundary
        faces = polygonize_faces([], [outside], margin)
        self.assertEqual(len(faces), 1)


class AssignTypesTest(unittest.TestCase):
    def setUp(self):
        self.face = box(0, 0, 100, 100)

    def test_osm_wins_over_base_even_when_the_base_polygon_is_smaller(self):
        osm = cover("LPSTROM", box(-10, -10, 200, 200))
        base = cover("ORNAPU", box(40, 40, 60, 60))
        self.assertEqual(assign_types([self.face], osm, base, [], SIZE), ["LPSTROM"])

    def test_base_used_when_osm_has_nothing(self):
        self.assertEqual(assign_types([self.face], empty_cover(), cover("ORNAPU", box(-10, -10, 200, 200)), [], SIZE), ["ORNAPU"])

    def test_smallest_enclosing_osm_polygon_wins(self):
        osm = cover("LPSTROM", box(-10, -10, 200, 200))
        pond = cover("VODPLO", box(30, 30, 70, 70))
        both = gpd.GeoDataFrame({"typ": ["LPSTROM", "VODPLO"]}, geometry=[osm.geometry.iloc[0], pond.geometry.iloc[0]], crs=5514)
        self.assertEqual(assign_types([self.face], both, empty_cover(), [], SIZE), ["VODPLO"])

    def test_uncovered_face_is_other(self):
        self.assertEqual(assign_types([self.face], empty_cover(), empty_cover(), [], SIZE), ["OTHER"])

    def test_buildings_turn_an_uncovered_face_into_built_up(self):
        houses = [box(10, 10, 40, 40)]  # 9% of the face
        self.assertEqual(assign_types([self.face], empty_cover(), empty_cover(), houses, SIZE), ["AREZAS"])
        few = [box(10, 10, 30, 30)]     # 4%
        self.assertEqual(assign_types([self.face], empty_cover(), empty_cover(), few, SIZE), ["OTHER"])

    def test_buildings_do_not_override_a_cover_type(self):
        osm = cover("ORNAPU", box(-10, -10, 200, 200))
        self.assertEqual(assign_types([self.face], osm, empty_cover(), [box(10, 10, 90, 90)], SIZE), ["ORNAPU"])


class MergeTest(unittest.TestCase):
    def test_same_class_squares_merge_up_to_the_maximum(self):
        faces = row_of_squares(6, 2.0)  # 12 ha in total
        result = merge_faces(faces, ["LPSTROM"] * 6, SIZE, CLASSES)
        areas = sorted(g.area / HA for g, _ in result)
        self.assertAlmostEqual(sum(areas), 12.0, places=6)
        self.assertTrue(all(a <= 8.0 + 1e-9 for a in areas), areas)
        self.assertLess(len(result), 6)

    def test_different_classes_stay_apart(self):
        faces = row_of_squares(2, 3.0)
        result = merge_faces(faces, ["LPSTROM", "ORNAPU"], SIZE, CLASSES)
        self.assertEqual(sorted(t for _, t in result), ["LPSTROM", "ORNAPU"])

    def test_same_class_different_typ_merge_and_take_the_larger_type(self):
        faces = [box(0, 0, 200, 200), box(200, 0, 350, 200)]  # 4 ha and 3 ha, adjacent along x=200
        result = merge_faces(faces, ["TRTRPO", "ODPOCI"], SIZE, CLASSES)  # both plugin class 1
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "TRTRPO")

    def test_tiny_face_merges_into_a_neighbour_of_another_class(self):
        big = box(0, 0, 300, 250)            # 7.5 ha, forest
        tiny = box(300, 0, 340, 100)         # 0.4 ha, field
        result = merge_faces([big, tiny], ["LPSTROM", "ORNAPU"], SIZE, CLASSES)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "LPSTROM")
        self.assertAlmostEqual(result[0][0].area, 75000 + 4000, places=3)

    def test_thin_sliver_merges_into_a_neighbour_of_another_class(self):
        big = box(0, 0, 300, 250)             # 7.5 ha, forest
        sliver = box(300, 0, 330, 1000)       # 3 ha, 30 x 1000 m: compactness 0.089 < 0.10, not tiny
        result = merge_faces([big, sliver], ["LPSTROM", "ORNAPU"], SIZE, CLASSES)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "LPSTROM")

    def test_compact_small_face_of_another_class_is_kept(self):
        big = box(0, 0, 300, 250)             # 7.5 ha, forest
        compact = box(300, 0, 470, 176)       # about 3 ha, nearly square
        result = merge_faces([big, compact], ["LPSTROM", "ORNAPU"], SIZE, CLASSES)
        self.assertEqual(len(result), 2)

    def test_isolated_small_face_is_kept(self):
        faces = [box(0, 0, 100, 100), box(5000, 5000, 5100, 5100)]
        result = merge_faces(faces, ["OTHER", "OTHER"], SIZE, CLASSES)
        self.assertEqual(len(result), 2)

    def test_empty_input(self):
        self.assertEqual(merge_faces([], [], SIZE, CLASSES), [])


class SplitTest(unittest.TestCase):
    def test_rectangle_is_cut_into_equal_parts(self):
        rect = box(0, 0, 800, 500)  # 40 ha
        parts = split_oversized([(rect, "LPSTROM")], SIZE)
        areas = [p.area / HA for p, _ in parts]
        self.assertEqual(len(parts), 6)
        self.assertAlmostEqual(sum(areas), 40.0, places=3)
        self.assertTrue(all(5.0 <= a <= 8.0 for a in areas), areas)
        self.assertTrue(all(t == "LPSTROM" for _, t in parts))

    def test_part_count_keeps_every_part_under_the_maximum(self):
        from tools.sk_data.sectors import _parts_for
        self.assertEqual(_parts_for(8.5 * HA, SIZE), 2)    # not left whole although it rounds to one 7 ha part
        self.assertEqual(_parts_for(10.0 * HA, SIZE), 2)
        self.assertEqual(_parts_for(24.0 * HA, SIZE), 4)   # 3 parts would be exactly at the maximum
        self.assertEqual(_parts_for(40.0 * HA, SIZE), 6)
        for ha in (8.01, 9.3, 15.9, 23.9, 57.0, 200.0):
            n = _parts_for(ha * HA, SIZE)
            self.assertLessEqual(ha / n, SIZE.max_ha * 0.98 + 1e-9, ha)

    def test_area_just_above_the_maximum_is_split(self):
        rect = box(0, 0, 400, 215)  # 8.6 ha
        parts = split_oversized([(rect, "ORNAPU")], SIZE)
        self.assertEqual(len(parts), 2)
        self.assertTrue(all(p.area <= SIZE.max_m2 for p, _ in parts))

    def test_small_sector_is_untouched(self):
        s = square(0, 0, 7.5)
        parts = split_oversized([(s, "ORNAPU")], SIZE)
        self.assertEqual(len(parts), 1)
        self.assertTrue(parts[0][0].equals(s))

    def test_l_shape_keeps_area_and_respects_the_maximum(self):
        l_shape = Polygon([(0, 0), (900, 0), (900, 200), (300, 200), (300, 700), (0, 700)])
        total = l_shape.area
        parts = split_oversized([(l_shape, "OTHER")], SIZE)
        self.assertAlmostEqual(sum(p.area for p, _ in parts), total, delta=total * 1e-4)
        self.assertTrue(all(p.area <= SIZE.max_m2 * 1.01 for p, _ in parts), [round(p.area / HA, 2) for p, _ in parts])
        union = unary_union([p for p, _ in parts])
        self.assertAlmostEqual(union.area, total, delta=total * 1e-4)  # no overlaps, no gaps


class UnionTest(unittest.TestCase):
    def test_adjacent_polygons_join_into_one(self):
        u = _union(box(0, 0, 10, 10), box(10, 0, 20, 10))
        self.assertEqual(u.geom_type, "Polygon")
        self.assertAlmostEqual(u.area, 200.0)

    def test_polygons_touching_at_a_point_do_not_join(self):
        self.assertIsNone(_union(box(0, 0, 10, 10), box(10, 10, 20, 20)))

    def test_single_polygon_drops_specks_and_rejects_real_multipolygons(self):
        speck = box(2, 2, 2.5, 2.5)                                   # 0.25 m2, inside nothing in particular
        self.assertEqual(_single_polygon(box(0, 0, 10, 10).union(speck)).area, 100.0)
        self.assertIsNone(_single_polygon(box(0, 0, 10, 10).union(box(50, 50, 60, 60))))
        bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])        # invalid, repairs into two triangles
        self.assertIsNone(_single_polygon(bowtie))

    def test_a_failed_union_leaves_the_fragment_alone(self):
        big = box(0, 0, 300, 250)
        corner_only = box(300, 250, 310, 260)                          # touches the big sector at one point only
        result = absorb_fragments([(big, "A"), (corner_only, "B")], SIZE)
        self.assertEqual(len(result), 2)


class FinalizeTest(unittest.TestCase):
    def test_a_degenerate_ring_is_removed(self):
        # a zero-width spike ring (two distinct points) as a hole: invalid, and it turned a sector into an
        # invalid MultiPolygon after a shapefile round trip in a real run
        spike = Polygon(box(0, 0, 100, 100).exterior, [[(40, 40), (50, 40), (50, 40), (40, 40)]])
        self.assertFalse(spike.is_valid)
        result = finalize_sectors([(spike, "LPSTROM")])
        self.assertEqual(len(result), 1)
        geom, typ = result[0]
        self.assertTrue(geom.is_valid)
        self.assertEqual(geom.geom_type, "Polygon")
        self.assertEqual(len(geom.interiors), 0)
        self.assertAlmostEqual(geom.area, 10000.0, places=3)
        self.assertEqual(typ, "LPSTROM")

    def test_a_tiny_hole_is_removed_but_a_real_hole_stays(self):
        tiny = Polygon(box(0, 0, 100, 100).exterior, [[(40, 40), (40.5, 40), (40.5, 40.5), (40, 40.5), (40, 40)]])   # 0.25 m2
        real = Polygon(box(0, 0, 100, 100).exterior, [box(40, 40, 50, 50).exterior.coords])
        self.assertEqual(len(finalize_sectors([(tiny, "A")])[0][0].interiors), 0)
        self.assertEqual(len(finalize_sectors([(real, "A")])[0][0].interiors), 1)

    def test_an_invalid_bowtie_becomes_valid_polygons_and_keeps_the_type(self):
        bowtie = Polygon([(0, 0), (100, 100), (100, 0), (0, 100)])
        result = finalize_sectors([(bowtie, "B")])
        self.assertEqual(len(result), 2)                       # two triangles
        self.assertTrue(all(g.is_valid and g.geom_type == "Polygon" and t == "B" for g, t in result))
        self.assertAlmostEqual(sum(g.area for g, _ in result), 5000.0, places=3)

    def test_a_multipolygon_is_split_into_separate_sectors(self):
        two = box(0, 0, 100, 100).union(box(500, 500, 600, 600))
        self.assertEqual(len(finalize_sectors([(two, "C")])), 2)

    def test_valid_polygons_pass_unchanged(self):
        b = box(0, 0, 300, 250)
        result = finalize_sectors([(b, "A")])
        self.assertTrue(result[0][0].equals(b))
        self.assertEqual(finalize_sectors([]), [])


class AbsorbFragmentsTest(unittest.TestCase):
    def test_a_fragment_joins_the_touching_sector(self):
        big = box(0, 0, 300, 250)            # 7.5 ha
        fragment = box(300, 0, 310, 5)       # 50 m2
        result = absorb_fragments([(big, "LPSTROM"), (fragment, "ORNAPU")], SIZE)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "LPSTROM")
        self.assertAlmostEqual(result[0][0].area, 75050.0, places=3)

    def test_prefers_a_neighbour_that_stays_within_the_maximum(self):
        full = box(0, 0, 400, 199.9)         # 7.996 ha, would overflow with the fragment
        roomy = box(400, 0, 600, 250)        # 5 ha
        fragment = box(390, -30, 410, 0)     # 600 m2, touching both sectors along 10 m each
        result = absorb_fragments([(full, "A"), (roomy, "B"), (fragment, "C")], SIZE)
        areas = sorted(round(g.area) for g, _ in result)
        self.assertEqual(len(result), 2)
        self.assertIn(round(roomy.area + fragment.area), areas)

    def test_falls_back_to_the_smallest_neighbour_when_none_fits(self):
        a = box(0, 0, 400, 197.5)            # 7.9 ha
        b = box(400, 0, 800, 199.0)          # 7.96 ha
        fragment = box(390, -60, 410, 0)     # 1200 m2 = 0.12 ha: too big for both (7.9 + 0.12 and 7.96 + 0.12 exceed 8)
        result = absorb_fragments([(a, "A"), (b, "B"), (fragment, "C")], SIZE)
        self.assertEqual(len(result), 2)
        merged = [g for g, t in result if t == "A"][0]
        self.assertAlmostEqual(merged.area, a.area + fragment.area, places=3)   # the smaller neighbour took it

    def test_isolated_fragment_is_kept_and_big_sectors_are_untouched(self):
        big = box(0, 0, 300, 250)
        lone = box(5000, 5000, 5010, 5005)
        result = absorb_fragments([(big, "A"), (lone, "B")], SIZE)
        self.assertEqual(len(result), 2)
        self.assertEqual(absorb_fragments([], SIZE), [])


class EndToEndTest(unittest.TestCase):
    def test_synthetic_landscape_is_partitioned(self):
        margin = box(0, 0, 1000, 1000)  # 100 ha
        road = LineString([(500, -10), (500, 1010)])
        forest = cover("LPSTROM", box(-50, -50, 500, 1050))
        sectors = build_sectors([road], [forest.geometry.iloc[0].boundary], margin, margin,
                                forest, empty_cover(), [], SIZE, CLASSES)
        geoms = [g for g, _ in sectors]
        areas = [g.area for g in geoms]
        self.assertAlmostEqual(sum(areas), margin.area, delta=margin.area * 1e-4)
        self.assertAlmostEqual(unary_union(geoms).area, sum(areas), delta=margin.area * 1e-4)  # no overlaps
        self.assertTrue(all(a <= SIZE.max_m2 * 1.01 for a in areas), sorted(a / HA for a in areas)[-3:])
        self.assertEqual({t for _, t in sectors}, {"LPSTROM", "OTHER"})
        left = sum(g.area for g, t in sectors if t == "LPSTROM")
        self.assertAlmostEqual(left, 500 * 1000, delta=500 * 1000 * 1e-3)

    def test_slivers_between_nearly_coincident_lines_leave_no_tiny_sectors(self):
        margin = box(0, 0, 1000, 1000)
        road = LineString([(500, -10), (500, 1010)])
        forest = cover("LPSTROM", box(-50, -50, 500.4, 1050))      # its edge runs 0.4 m beside the road
        sectors = build_sectors([road], [forest.geometry.iloc[0].boundary], margin, margin,
                                forest, empty_cover(), [], SIZE, CLASSES)
        self.assertTrue(all(g.area >= SIZE.tiny_m2 for g, _ in sectors), sorted(g.area for g, _ in sectors)[:3])
        self.assertAlmostEqual(sum(g.area for g, _ in sectors), margin.area, delta=margin.area * 1e-4)

    def test_select_inside_uses_the_representative_point(self):
        a, b = box(0, 0, 10, 10), box(100, 100, 110, 110)
        kept = select_inside([(a, "X"), (b, "Y")], box(-5, -5, 50, 50))
        self.assertEqual([t for _, t in kept], ["X"])
        self.assertEqual(select_inside([], box(0, 0, 1, 1)), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest tests.sk_data.test_sectors 2>&1 | tail -4`
Expected: `ModuleNotFoundError: No module named 'tools.sk_data.sectors'`.

- [ ] **Step 3: Write the module**

Create `tools/sk_data/sectors.py`:

```python
# -*- coding: utf-8 -*-
"""Sector builder: polygonize lines into faces, type them, merge small ones, split big ones.

All functions work on shapely geometries in a metric CRS (EPSG:5514) and need no files.
"""

import heapq
import logging
import math
from collections import Counter

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

log = logging.getLogger("sk_data")

MIN_SHARED_BORDER_M = 3.0  # ordinary merges need at least this much shared border
MIN_CONTACT_M = 0.01       # any real contact counts when a tiny face or sliver is absorbed


def polygonize_faces(barrier_lines, boundary_lines, margin):
    """Faces enclosed by the lines and the margin polygon's boundary, kept when inside the margin."""
    noded = unary_union(list(barrier_lines) + list(boundary_lines) + [margin.boundary])
    faces = [p for p in polygonize(noded) if p.is_valid and p.area > 1.0]
    if not faces:
        return []
    arr = np.array(faces, dtype=object)
    inside = shapely.contains(margin, shapely.point_on_surface(arr))
    return list(arr[inside])


def _smallest_enclosing_typ(points, cover):
    """{point index: typ of the smallest cover polygon containing the point}."""
    if len(cover) == 0 or len(points) == 0:
        return {}
    areas = cover.geometry.area.to_numpy()
    typs = cover["typ"].to_numpy()
    tree = STRtree(list(cover.geometry))
    point_idx, cover_idx = tree.query(points, predicate="within")
    best = {}
    for p, c in zip(point_idx, cover_idx):
        p, c = int(p), int(c)
        if p not in best or areas[c] < areas[best[p]]:
            best[p] = c
    return {p: str(typs[c]) for p, c in best.items()}


def assign_types(faces, osm_cover, base_cover, buildings, size):
    """Sector type per face: OSM cover first, then the base layer (WorldCover), else OTHER.

    osm_cover / base_cover: GeoDataFrames with columns 'typ' and geometry.
    buildings: sequence of building polygons. Faces still OTHER with enough buildings become AREZAS.
    """
    if not faces:
        return []
    arr = np.array(faces, dtype=object)
    points = shapely.point_on_surface(arr)
    from_osm = _smallest_enclosing_typ(points, osm_cover)
    from_base = _smallest_enclosing_typ(points, base_cover)
    types = [from_osm.get(i) or from_base.get(i) or "OTHER" for i in range(len(faces))]
    buildings = list(buildings)
    if buildings:
        barr = np.array(buildings, dtype=object)
        btree = STRtree(buildings)
        for i, typ in enumerate(types):
            if typ != "OTHER":
                continue
            candidates = btree.query(faces[i], predicate="intersects")
            if len(candidates) == 0:
                continue
            covered = shapely.area(shapely.intersection(barr[candidates], faces[i])).sum()
            if covered / faces[i].area >= size.building_share:
                types[i] = "AREZAS"
    return types


def _clean_polygons(geom):
    """The valid polygons in geom: an invalid geometry is repaired, specks under 1 m2 and degenerate holes are dropped."""
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    out = []
    for polygon in _polygons(geom):
        holes = [ring for ring in polygon.interiors if Polygon(ring).area >= 1.0]
        out.append(polygon if len(holes) == len(polygon.interiors) else Polygon(polygon.exterior, holes))
    return out


def _single_polygon(geom):
    """geom as one valid Polygon without degenerate parts, or None if it would be several real parts."""
    parts = _clean_polygons(geom)
    return parts[0] if len(parts) == 1 else None


def _union(a, b):
    """Union of two polygons as one valid Polygon, or None (touching only at a point, degenerate result)."""
    return _single_polygon(shapely.union(a, b))


def merge_faces(faces, types, size, classes):
    """Merge faces smaller than size.min_ha into neighbours. Returns [(geometry, typ)].

    A face merges with the neighbour of the same plugin class (classes: typ -> 1..10) that shares the
    longest border (at least MIN_SHARED_BORDER_M), as long as the result stays within size.max_ha.
    Faces under size.tiny_ha and thin slivers merge into any touching neighbour, however short the
    contact. A merged sector takes the type with the largest area.
    """
    geoms = {i: g for i, g in enumerate(faces)}
    ftyp = dict(enumerate(types))
    area = {i: g.area for i, g in geoms.items()}
    mix = {i: Counter({types[i]: faces[i].area}) for i in geoms}
    adj = {i: {} for i in geoms}
    if len(faces) > 1:
        arr = np.array(faces, dtype=object)
        a_idx, b_idx = STRtree(arr).query(arr, predicate="intersects")
        keep = a_idx < b_idx
        a_idx, b_idx = a_idx[keep], b_idx[keep]
        lengths = shapely.length(shapely.intersection(arr[a_idx], arr[b_idx]))
        for a, b, length in zip(a_idx, b_idx, lengths):
            if length >= MIN_CONTACT_M:
                adj[int(a)][int(b)] = float(length)
                adj[int(b)][int(a)] = float(length)

    heap = [(area[i], i) for i in geoms if area[i] < size.min_m2]
    heapq.heapify(heap)
    while heap:
        a, i = heapq.heappop(heap)
        if i not in geoms or abs(area[i] - a) > 1e-6 or area[i] >= size.min_m2:
            continue
        neighbours = adj[i]
        if not neighbours:
            continue
        same = [(length, -area[j], j) for j, length in neighbours.items()
                if length >= MIN_SHARED_BORDER_M and classes[ftyp[j]] == classes[ftyp[i]]
                and area[i] + area[j] <= size.max_m2]
        thin = (area[i] < size.sliver_max_m2
                and 4 * np.pi * area[i] / geoms[i].length ** 2 < size.sliver_compactness)
        if same:
            ranked = sorted(same, reverse=True)
        elif area[i] < size.tiny_m2 or thin:
            ranked = sorted(((length, -area[j], j) for j, length in neighbours.items()), reverse=True)
        else:
            continue
        for _, _, j in ranked:               # the best neighbour whose union is one valid polygon
            joined = _union(geoms[j], geoms[i])
            if joined is not None:
                break
        else:
            continue
        mix[j].update(mix[i])
        ftyp[j] = mix[j].most_common(1)[0][0]
        geoms[j] = joined
        area[j] = joined.area
        for k, length in adj[i].items():
            if k == j:
                continue
            adj[j][k] = adj[j].get(k, 0.0) + length
            adj[k][j] = adj[j][k]
            adj[k].pop(i, None)
        adj[j].pop(i, None)
        del geoms[i], adj[i], area[i], ftyp[i], mix[i]
        if area[j] < size.min_m2:
            heapq.heappush(heap, (area[j], j))
    return [(geoms[i], ftyp[i]) for i in geoms]


def _long_axis(g):
    xs, ys = g.minimum_rotated_rectangle.exterior.coords.xy
    e1 = (xs[1] - xs[0], ys[1] - ys[0])
    e2 = (xs[2] - xs[1], ys[2] - ys[1])
    v = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2
    return np.array(v) / np.hypot(*v)


def _side(g, axis, offset, lower):
    """Part of g on one side of the line {x: axis . x = offset}."""
    big = 20000.0
    perp = np.array([-axis[1], axis[0]])
    centre = np.array(g.centroid.coords[0])
    sign = -1.0 if lower else 1.0
    a = centre + axis * (offset - float(np.dot(axis, centre)))
    return g.intersection(Polygon([a + perp * big, a - perp * big,
                                   a - perp * big + sign * axis * big, a + perp * big + sign * axis * big]))


def _polygons(g):
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g] if g.area > 1.0 else []
    return [p for part in getattr(g, "geoms", []) for p in _polygons(part)]


def _parts_for(area, size):
    """Number of near-equal parts for an area above the maximum: the fewest that keep every part under
    max_m2 (with 2% safety), or one more if that gives parts closer to the target size."""
    fewest = int(math.ceil(area / (size.max_m2 * 0.98)))
    return min((fewest, fewest + 1), key=lambda n: (abs(area / n - size.target_m2), -n))


def _split(g, size, depth=0):
    if g.area <= size.max_m2 or depth > 14:
        return [g]
    parts = _parts_for(g.area, size)
    axis = _long_axis(g)
    projections = [float(np.dot(axis, c)) for c in np.array(g.convex_hull.exterior.coords)]
    low, high = min(projections), max(projections)
    wanted = g.area * (parts // 2) / parts
    for _ in range(40):  # bisection on the cut position so the lower side gets its share of the area
        mid = (low + high) / 2
        if _side(g, axis, mid, True).area < wanted:
            low = mid
        else:
            high = mid
    out = []
    for piece in _polygons(_side(g, axis, mid, True)) + _polygons(_side(g, axis, mid, False)):
        out.extend(_split(piece, size, depth + 1))
    return out


def split_oversized(sectors, size):
    """Cut sectors larger than size.max_ha into near-equal parts of about size.target_ha."""
    out = []
    for geom, typ in sectors:
        for polygon in _polygons(geom):
            out.extend((part, typ) for part in _split(polygon, size))
    return out


def absorb_fragments(sectors, size):
    """Merge every sector smaller than size.tiny_ha into a touching sector.

    Splitting leaves small corner fragments. Each one joins the neighbour it shares the longest border with
    when the result stays within size.max_ha, otherwise the smallest neighbour (so a sector can end up
    slightly above the maximum, by less than size.tiny_ha). A fragment without any neighbour is kept.
    """
    if not sectors:
        return []
    geoms = [g for g, _ in sectors]
    typs = [t for _, t in sectors]
    area = [g.area for g in geoms]
    parent = list(range(len(geoms)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tree = STRtree(np.array(geoms, dtype=object))
    for i in sorted((i for i in range(len(geoms)) if area[i] < size.tiny_m2), key=lambda i: area[i]):
        if parent[i] != i or area[i] >= size.tiny_m2:
            continue
        neighbours = {find(int(k)) for k in tree.query(geoms[i], predicate="intersects")} - {i}
        ranked = []
        for r in neighbours:
            length = geoms[i].intersection(geoms[r]).length
            if length >= MIN_CONTACT_M:
                fits = area[i] + area[r] <= size.max_m2
                ranked.append(((fits, length if fits else -area[r]), r))
        for _, r in sorted(ranked, reverse=True):   # the best neighbour whose union is one valid polygon
            joined = _union(geoms[r], geoms[i])
            if joined is not None:
                break
        else:
            continue
        if area[i] > area[r]:
            typs[r] = typs[i]
        geoms[r] = joined
        area[r] = joined.area
        parent[i] = r
    return [(geoms[i], typs[i]) for i in range(len(geoms)) if parent[i] == i]


def finalize_sectors(sectors):
    """Make every sector a valid single polygon: repair invalid geometries, drop specks and degenerate holes
    (a zero-width hole turned into an invalid MultiPolygon after a shapefile round trip), and turn a
    sector that is several real parts into separate sectors of the same type."""
    return [(polygon, typ) for geom, typ in sectors for polygon in _clean_polygons(geom)]


def select_inside(sectors, region):
    """Keep sectors whose representative point lies inside the region polygon."""
    if not sectors:
        return []
    arr = np.array([g for g, _ in sectors], dtype=object)
    inside = shapely.contains(region, shapely.point_on_surface(arr))
    return [sectors[i] for i in np.flatnonzero(inside)]


def build_sectors(barrier_lines, boundary_lines, margin, region, osm_cover, base_cover, buildings, size, classes):
    """Faces -> types -> merge -> split -> absorb fragments -> clean -> keep those inside the region. Returns [(Polygon, typ)]."""
    faces = polygonize_faces(barrier_lines, boundary_lines, margin)
    log.info("faces: %d", len(faces))
    types = assign_types(faces, osm_cover, base_cover, buildings, size)
    merged = merge_faces(faces, types, size, classes)
    log.info("sectors after merge: %d", len(merged))
    sectors = finalize_sectors(absorb_fragments(split_oversized(merged, size), size))
    log.info("sectors after split: %d", len(sectors))
    return select_inside(sectors, region)
```

- [ ] **Step 4: Run to verify they pass**

Run: the command of Step 2.
Expected: `Ran 37 tests ... OK`. A `RuntimeWarning` from shapely about `oriented_envelope` for degenerate shapes is acceptable only if it appears in the full-region runs, never in these tests; if it appears here, report it.

- [ ] **Step 5: Commit**

```bash
git add tools/sk_data/sectors.py tests/sk_data/test_sectors.py
git commit -m "Add sector builder: polygonize, type, merge and split faces

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Pinned coordinate transformation and downloads

**Files:**
- Create: `tools/sk_data/crs.py`, `tools/sk_data/download.py`, `tests/sk_data/test_crs_download.py`

**Interfaces:**
- Produces: `crs.wgs84_to_sjtsk() -> pyproj.Transformer` (lon, lat in; x, y out; Slovak operation), `crs.project_geometries(geoms, transformer=None) -> ndarray of geometries`, `crs.to_sjtsk(gdf) -> GeoDataFrame (EPSG:5514)`.
- Produces: `download.worldcover_tiles(bbox) -> list[str]`, `download.worldcover_url(tile) -> str`, `download.download(url, dest, opener=None) -> dict`, `download.fetch_sources(root, bbox, opener=None, include_worldcover=True) -> dict` (writes `<root>/source/sources.json`; `bbox=None` is allowed together with `include_worldcover=False`).

- [ ] **Step 1: Write the tests**

Create `tests/sk_data/test_crs_download.py`:

```python
import hashlib
import io
import os
import tempfile
import unittest

from shapely.geometry import Point

from tools.sk_data import download
from tools.sk_data.crs import project_geometries, to_sjtsk, wgs84_to_sjtsk


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class CrsTest(unittest.TestCase):
    def test_kosice_uses_the_slovak_operation(self):
        x, y = wgs84_to_sjtsk().transform(21.2611, 48.7164)
        # EPSG:4836 result; the generic fallback (3) would give x=-262576.1, y=-1240028.3
        self.assertAlmostEqual(x, -262580.66, delta=0.5)
        self.assertAlmostEqual(y, -1240038.58, delta=0.5)

    def test_project_geometries_and_to_sjtsk(self):
        import geopandas as gpd
        gdf = gpd.GeoDataFrame({"name": ["k"]}, geometry=[Point(21.2611, 48.7164)], crs=4326)
        out = to_sjtsk(gdf)
        self.assertEqual(out.crs.to_epsg(), 5514)
        self.assertEqual(list(out["name"]), ["k"])
        self.assertAlmostEqual(out.geometry.iloc[0].x, -262580.66, delta=0.5)
        self.assertEqual(len(project_geometries([Point(21.0, 48.5)])), 1)


class DownloadTest(unittest.TestCase):
    def test_worldcover_tiles(self):
        self.assertEqual(download.worldcover_tiles((20.161, 48.313, 22.408, 49.04)), ["N48E018", "N48E021"])
        self.assertEqual(download.worldcover_tiles((16.934, 47.759, 17.985, 48.878)), ["N45E015", "N48E015"])
        self.assertEqual(download.worldcover_tiles((21.0, 48.0, 24.0, 51.0)), ["N48E021"])  # edges on tile borders

    def test_worldcover_url(self):
        self.assertTrue(download.worldcover_url("N48E021").endswith("ESA_WorldCover_10m_2021_v200_N48E021_Map.tif"))

    def test_download_writes_file_and_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "sub", "f.bin")
            info = download.download("http://x/f", dest, opener=lambda u: FakeResponse(b"abc"))
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), b"abc")
            self.assertFalse(os.path.exists(dest + ".part"))
            self.assertEqual(info["sha256"], hashlib.sha256(b"abc").hexdigest())
            self.assertEqual(info["bytes"], 3)

    def test_fetch_sources_skips_existing_files_and_writes_manifest(self):
        calls = []

        def opener(url):
            calls.append(url)
            return FakeResponse(b"data")

        with tempfile.TemporaryDirectory() as d:
            m1 = download.fetch_sources(d, (21.0, 48.5, 21.5, 48.9), opener=opener)
            self.assertEqual(len(calls), 2)  # the OSM extract and tile N48E021
            self.assertIn("osm", m1)
            self.assertIn("worldcover-N48E021", m1)
            m2 = download.fetch_sources(d, (21.0, 48.5, 21.5, 48.9), opener=opener)
            self.assertEqual(len(calls), 2)  # nothing downloaded again
            self.assertEqual(set(m2), set(m1))
            self.assertTrue(os.path.exists(os.path.join(d, "source", "sources.json")))

    def test_fetch_sources_without_worldcover(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            download.fetch_sources(d, (21.0, 48.5, 21.5, 48.9), opener=lambda u: calls.append(u) or FakeResponse(b"x"), include_worldcover=False)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest tests.sk_data.test_crs_download 2>&1 | tail -4`
Expected: `ModuleNotFoundError: No module named 'tools.sk_data.crs'`.

- [ ] **Step 3: Write the modules**

Create `tools/sk_data/crs.py`:

```python
# -*- coding: utf-8 -*-
"""WGS84 -> S-JTSK (EPSG:5514) with the Slovak transformation pinned.

PROJ offers several operations for this pair. EPSG:4836 "S-JTSK to WGS 84 (4)" is the one defined for
Slovakia (1 m); the Czechoslovak fallback "(3)" is about 10 m away at Kosice and the Czech ones "(1)" and
"(5)" do not cover eastern Slovakia. Pinning it makes the output independent of PROJ's choice.
"""

import geopandas as gpd
import numpy as np
import shapely
from pyproj.transformer import TransformerGroup

OPERATION_NAME = "S-JTSK to WGS 84 (4)"
_cache = {}


def wgs84_to_sjtsk():
    """pyproj Transformer EPSG:4326 -> EPSG:5514 (lon, lat in; x, y out) using the Slovak operation."""
    if "t" not in _cache:
        for transformer in TransformerGroup(4326, 5514, always_xy=True).transformers:
            if OPERATION_NAME in transformer.description:
                _cache["t"] = transformer
                break
        else:
            raise RuntimeError("PROJ has no operation named %r; check the PROJ database of this QGIS" % OPERATION_NAME)
    return _cache["t"]


def project_geometries(geoms, transformer=None):
    """Transform an array-like of WGS84 shapely geometries to EPSG:5514."""
    transformer = transformer or wgs84_to_sjtsk()

    def apply(coords):
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(np.asarray(list(geoms), dtype=object), apply)


def to_sjtsk(gdf):
    """Copy of a WGS84 GeoDataFrame with geometries in EPSG:5514."""
    geoms = project_geometries(gdf.geometry.values)
    return gpd.GeoDataFrame(gdf.drop(columns=gdf.geometry.name), geometry=geoms, crs=5514)
```

Create `tools/sk_data/download.py`:

```python
# -*- coding: utf-8 -*-
"""Download the source data (Geofabrik OSM extract, ESA WorldCover tiles) and record where it came from."""

import hashlib
import json
import logging
import math
import os
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("sk_data")

GEOFABRIK_URL = "https://download.geofabrik.de/europe/slovakia-latest.osm.pbf"
WORLDCOVER_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
USER_AGENT = "patrac-sk-data/1.0"


def worldcover_tiles(bbox):
    """Names of the 3 x 3 degree WorldCover tiles (e.g. 'N48E021') covering bbox = (minx, miny, maxx, maxy) lon/lat."""
    minx, miny, maxx, maxy = bbox
    tiles = []
    lat = int(math.floor(miny / 3) * 3)
    while lat < maxy:
        lon = int(math.floor(minx / 3) * 3)
        while lon < maxx:
            tiles.append("%s%02d%s%03d" % ("N" if lat >= 0 else "S", abs(lat), "E" if lon >= 0 else "W", abs(lon)))
            lon += 3
        lat += 3
    return tiles


def worldcover_url(tile):
    return WORLDCOVER_URL.format(tile=tile)


def download(url, dest, opener=None, chunk=1 << 20):
    """Download url to dest (via dest + '.part'). Returns {'url', 'path', 'bytes', 'sha256', 'downloaded'}."""
    opener = opener or (lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": USER_AGENT})))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    digest = hashlib.sha256()
    size = 0
    with opener(url) as response, open(part, "wb") as out:
        while True:
            block = response.read(chunk)
            if not block:
                break
            out.write(block)
            digest.update(block)
            size += len(block)
    os.replace(part, dest)
    return {"url": url, "path": dest, "bytes": size, "sha256": digest.hexdigest(),
            "downloaded": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def fetch_sources(root, bbox, opener=None, include_worldcover=True):
    """Make sure the OSM extract and the WorldCover tiles for bbox exist under <root>/source. Returns the manifest.

    Files that already exist are kept (their manifest entry is kept too); delete a file to download it again.
    The manifest is written to <root>/source/sources.json.
    """
    source = os.path.join(root, "source")
    manifest_path = os.path.join(source, "sources.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    wanted = [("osm", GEOFABRIK_URL, os.path.join(source, "osm-slovakia", "slovakia-latest.osm.pbf"))]
    if include_worldcover:
        for tile in worldcover_tiles(bbox):
            wanted.append(("worldcover-" + tile, worldcover_url(tile),
                           os.path.join(source, "esa-worldcover", os.path.basename(worldcover_url(tile)))))
    for name, url, dest in wanted:
        if os.path.exists(dest):
            manifest.setdefault(name, {"url": url, "path": dest, "bytes": os.path.getsize(dest), "sha256": None, "downloaded": None})
            continue
        log.info("downloading %s", url)
        manifest[name] = download(url, dest, opener)
    os.makedirs(source, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    return manifest
```

- [ ] **Step 4: Run to verify they pass**

Run: the command of Step 2 with `-W error::ResourceWarning` added after `"$QGIS_PY"`.
Expected: `Ran 7 tests ... OK`.

- [ ] **Step 5: Commit**

```bash
git add tools/sk_data/crs.py tools/sk_data/download.py tests/sk_data/test_crs_download.py
git commit -m "Add pinned S-JTSK transformation and source downloads

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: OSM extraction

**Files:**
- Create: `tools/sk_data/extract.py`, `tests/sk_data/osm_fixture.py`, `tests/sk_data/test_extract.py`

**Interfaces:**
- Produces: `extract.parse_tags(other_tags) -> dict`; `extract.with_tags(gdf)`; `extract.region_boundary(pbf, osm_name, work_dir, admin_level=4) -> GeoDataFrame` (one row, EPSG:4326, columns `name geometry`); `extract.bbox_of(boundary, pad=0.02) -> (minx, miny, maxx, maxy)`; `extract.extract(pbf, bbox, out_dir) -> {'lines','polygons','points': path}`; `extract.read_lines(path)` and `extract.read_points(path)` -> GeoDataFrame with a `tags` dict column; `extract.read_polygons(path) -> (GeoDataFrame with tags excluding buildings, GeoSeries of building geometries)`.
- Produces for tests: `tests.sk_data.osm_fixture.write_fixture(path) -> path`, a tiny `.osm` XML file around Košice (a forest polygon, a road, a stream, a building, a village node, and a level-4 boundary named "Test kraj").

- [ ] **Step 1: Write the fixture and the tests**

Create `tests/sk_data/osm_fixture.py`:

```python
"""A tiny hand-written OSM XML file around Kosice (about 3 x 3 km) for tests."""

OSM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" lat="48.700" lon="21.200"/>
  <node id="2" lat="48.700" lon="21.210"/>
  <node id="3" lat="48.710" lon="21.210"/>
  <node id="4" lat="48.710" lon="21.200"/>
  <node id="5" lat="48.695" lon="21.205"/>
  <node id="6" lat="48.715" lon="21.205"/>
  <node id="7" lat="48.705" lon="21.195"/>
  <node id="8" lat="48.705" lon="21.215"/>
  <node id="9" lat="48.7020" lon="21.2020"/>
  <node id="10" lat="48.7020" lon="21.2030"/>
  <node id="11" lat="48.7030" lon="21.2030"/>
  <node id="12" lat="48.7030" lon="21.2020"/>
  <node id="20" lat="48.705" lon="21.205"><tag k="place" v="village"/><tag k="name" v="Testov"/></node>
  <node id="31" lat="48.690" lon="21.190"/>
  <node id="32" lat="48.690" lon="21.220"/>
  <node id="33" lat="48.720" lon="21.220"/>
  <node id="34" lat="48.720" lon="21.190"/>
  <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="landuse" v="forest"/><tag k="name" v="A &quot;quoted&quot; wood"/></way>
  <way id="11"><nd ref="5"/><nd ref="6"/><tag k="highway" v="residential"/><tag k="name" v="Hlavna"/></way>
  <way id="12"><nd ref="7"/><nd ref="8"/><tag k="waterway" v="stream"/></way>
  <way id="13"><nd ref="9"/><nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="9"/><tag k="building" v="yes"/></way>
  <way id="14"><nd ref="31"/><nd ref="32"/><nd ref="33"/><nd ref="34"/><nd ref="31"/></way>
  <relation id="100"><member type="way" ref="14" role="outer"/>
    <tag k="type" v="boundary"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="4"/><tag k="name" v="Test kraj"/></relation>
</osm>
"""


def write_fixture(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(OSM_XML)
    return path
```

Create `tests/sk_data/test_extract.py`:

```python
import os
import tempfile
import unittest

from tests.sk_data.osm_fixture import write_fixture
from tools.sk_data import extract


class ParseTagsTest(unittest.TestCase):
    def test_plain_and_escaped_values(self):
        tags = extract.parse_tags('"railway"=>"rail","name"=>"A \\"quoted\\" b","ref"=>"x\\\\y"')
        self.assertEqual(tags, {"railway": "rail", "name": 'A "quoted" b', "ref": "x\\y"})

    def test_missing_value(self):
        self.assertEqual(extract.parse_tags(None), {})
        self.assertEqual(extract.parse_tags(float("nan")), {})


class ExtractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.osm = write_fixture(os.path.join(cls.tmp.name, "mini.osm"))
        cls.boundary = extract.region_boundary(cls.osm, "Test kraj", os.path.join(cls.tmp.name, "w"))
        cls.paths = extract.extract(cls.osm, extract.bbox_of(cls.boundary), os.path.join(cls.tmp.name, "x"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_region_boundary(self):
        self.assertEqual(len(self.boundary), 1)
        self.assertEqual(self.boundary.crs.to_epsg(), 4326)
        minx, miny, maxx, maxy = self.boundary.total_bounds
        self.assertAlmostEqual(minx, 21.19, places=3)
        self.assertAlmostEqual(maxy, 48.72, places=3)

    def test_unknown_region_raises(self):
        with self.assertRaises(ValueError):
            extract.region_boundary(self.osm, "Nowhere kraj", os.path.join(self.tmp.name, "w2"))

    def test_bbox_is_padded(self):
        minx, miny, maxx, maxy = extract.bbox_of(self.boundary)
        self.assertAlmostEqual(minx, 21.17, places=3)
        self.assertAlmostEqual(maxy, 48.74, places=3)

    def test_lines_have_tags(self):
        lines = extract.read_lines(self.paths["lines"])
        kinds = sorted((t.get("highway") or t.get("waterway")) for t in lines["tags"])
        self.assertEqual(kinds, ["residential", "stream"])

    def test_polygons_split_buildings_from_the_rest(self):
        polygons, buildings = extract.read_polygons(self.paths["polygons"])
        self.assertEqual(len(buildings), 1)
        forest = [t for t in polygons["tags"] if t.get("landuse") == "forest"]
        self.assertEqual(len(forest), 1)
        self.assertEqual(forest[0]["name"], 'A "quoted" wood')

    def test_points_include_the_village_node(self):
        points = extract.read_points(self.paths["points"])
        villages = [t for t in points["tags"] if t.get("place") == "village"]
        self.assertEqual([v["name"] for v in villages], ["Testov"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest tests.sk_data.test_extract 2>&1 | tail -4`
Expected: `ModuleNotFoundError: No module named 'tools.sk_data.extract'`.

- [ ] **Step 3: Write the module**

Create `tools/sk_data/extract.py`:

```python
# -*- coding: utf-8 -*-
"""Read OpenStreetMap data with GDAL's OSM driver: region boundary, lines, polygons and place nodes."""

import logging
import os
import re

import geopandas as gpd
from osgeo import gdal

gdal.UseExceptions()
log = logging.getLogger("sk_data")

_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')
_SKIP_COLUMNS = {"geometry", "other_tags", "osm_id", "osm_way_id", "z_order"}
BBOX_PAD_DEG = 0.02


def parse_tags(other_tags):
    """Dict from the hstore text GDAL puts in the other_tags column."""
    if not isinstance(other_tags, str):
        return {}
    unescape = lambda s: s.replace('\\"', '"').replace("\\\\", "\\")
    return {unescape(k): unescape(v) for k, v in _PAIR.findall(other_tags)}


def with_tags(gdf):
    """Copy of gdf with a 'tags' column: all OSM tags of a feature (columns and other_tags) as one dict."""
    columns = [c for c in gdf.columns if c not in _SKIP_COLUMNS]
    tags = []
    for row in gdf[columns + ["other_tags"]].to_dict("records"):
        t = parse_tags(row.pop("other_tags"))
        t.update({k: v for k, v in row.items() if isinstance(v, str)})
        tags.append(t)
    out = gdf[["geometry"]].copy()
    out["tags"] = tags
    return out


def _translate(dest, pbf, layer, **kwargs):
    if os.path.exists(dest):
        os.remove(dest)
    gdal.PushErrorHandler("CPLQuietErrorHandler")  # cut-off relations at the border warn about unclosed rings
    try:
        gdal.VectorTranslate(dest, pbf, format="GPKG", layers=[layer],
                             geometryType="PROMOTE_TO_MULTI" if layer == "multipolygons" else None, **kwargs)
    finally:
        gdal.PopErrorHandler()
    return dest


def region_boundary(pbf, osm_name, work_dir, admin_level=4):
    """Boundary of an administrative relation as a one-row GeoDataFrame (EPSG:4326)."""
    os.makedirs(work_dir, exist_ok=True)
    where = "boundary='administrative' AND admin_level='%d' AND name='%s'" % (admin_level, osm_name.replace("'", "''"))
    dest = _translate(os.path.join(work_dir, "boundary.gpkg"), pbf, "multipolygons", where=where)
    gdf = gpd.read_file(dest)
    if gdf.empty:
        raise ValueError("no administrative boundary named %r (admin_level=%d) in %s" % (osm_name, admin_level, pbf))
    return gdf.iloc[[0]][["name", "geometry"]].reset_index(drop=True)


def bbox_of(boundary, pad=BBOX_PAD_DEG):
    minx, miny, maxx, maxy = boundary.total_bounds
    return (minx - pad, miny - pad, maxx + pad, maxy + pad)


def extract(pbf, bbox, out_dir):
    """Cut lines, multipolygons, points and administrative areas inside bbox (lon/lat) out of the OSM file.

    Returns {'lines', 'polygons', 'points'} -> GeoPackage paths in out_dir.
    """
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for name, layer in (("lines", "lines"), ("polygons", "multipolygons"), ("points", "points")):
        log.info("extracting OSM %s", layer)
        paths[name] = _translate(os.path.join(out_dir, name + ".gpkg"), pbf, layer, spatFilter=tuple(bbox))
    return paths


def read_lines(path):
    """OSM lines as a GeoDataFrame with a 'tags' column (EPSG:4326)."""
    return with_tags(gpd.read_file(path))


def read_polygons(path):
    """OSM polygons split into (everything except buildings with a 'tags' column, building geometries)."""
    gdf = gpd.read_file(path)
    is_building = gdf["building"].notna() if "building" in gdf.columns else gdf.index.to_series().map(lambda _: False)
    buildings = gdf.loc[is_building, "geometry"].reset_index(drop=True)
    return with_tags(gdf.loc[~is_building]), buildings


def read_points(path):
    """OSM nodes with tags as a GeoDataFrame with a 'tags' column (EPSG:4326)."""
    return with_tags(gpd.read_file(path))
```

- [ ] **Step 4: Run to verify they pass**

Run: the command of Step 2 with `-W error::ResourceWarning` after `"$QGIS_PY"`.
Expected: `Ran 8 tests ... OK`.

- [ ] **Step 5: Commit**

```bash
git add tools/sk_data/extract.py tests/sk_data/osm_fixture.py tests/sk_data/test_extract.py
git commit -m "Add OSM extraction with GDAL and a tiny OSM test fixture

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Land cover (OSM polygons and WorldCover)

**Files:**
- Create: `tools/sk_data/landcover.py`, `tests/sk_data/test_landcover.py`

**Interfaces:**
- Consumes: `rules.Rules`, `config.SectorSize`, `crs.project_geometries`.
- Produces: `landcover.osm_cover(polygons, rules, size) -> GeoDataFrame[typ, geometry]` (input: EPSG:5514 GeoDataFrame with a `tags` column); `landcover.worldcover_cover(tif_paths, bbox, rules, size, sieve_ha=0.5) -> GeoDataFrame[typ, geometry]` (EPSG:5514; `bbox` is lon/lat).
- Produces for tests: `tests.sk_data.test_landcover.write_raster(path, array, origin=(21.200, 48.706), pixel=0.0001)` writes a Byte GeoTIFF in EPSG:4326.

- [ ] **Step 1: Write the tests**

Create `tests/sk_data/test_landcover.py`:

```python
import math
import os
import tempfile
import unittest

import geopandas as gpd
import numpy as np
from osgeo import gdal, osr
from shapely.geometry import box

from tools.sk_data.config import SectorSize
from tools.sk_data.landcover import osm_cover, worldcover_cover
from tools.sk_data.rules import load_rules

RULES = load_rules()
SIZE = SectorSize()


class OsmCoverTest(unittest.TestCase):
    def test_keeps_typed_polygons_of_sufficient_area_only(self):
        polygons = gpd.GeoDataFrame(
            {"tags": [{"landuse": "forest"}, {"landuse": "forest"}, {"highway": "pedestrian"}, {"natural": "water"}]},
            geometry=[box(0, 0, 100, 100), box(0, 0, 20, 20), box(0, 0, 100, 100), box(0, 0, 60, 60)], crs=5514)
        cover = osm_cover(polygons, RULES, SIZE)
        self.assertEqual(sorted(cover["typ"]), ["LPSTROM", "VODPLO"])  # 400 m2 forest and the untyped polygon are dropped
        self.assertEqual(cover.crs.to_epsg(), 5514)


def write_raster(path, array, origin=(21.200, 48.706), pixel=0.0001):
    ds = gdal.GetDriverByName("GTiff").Create(path, array.shape[1], array.shape[0], 1, gdal.GDT_Byte)
    ds.SetGeoTransform((origin[0], pixel, 0, origin[1], 0, -pixel))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(array)
    ds.FlushCache()
    ds = None


class WorldCoverTest(unittest.TestCase):
    def test_classes_become_typed_polygons_and_speckles_are_removed(self):
        array = np.full((60, 100), 10, dtype=np.uint8)   # trees
        array[:, 50:] = 40                                # cropland on the right half
        array[10:13, 10:13] = 30                          # a 3 x 3 pixel grass speckle inside the trees
        with tempfile.TemporaryDirectory() as d:
            tif = os.path.join(d, "wc.tif")
            write_raster(tif, array)
            cover = worldcover_cover([tif], (21.200, 48.700, 21.210, 48.706), RULES, SIZE)
        self.assertEqual(sorted(cover["typ"]), ["LPSTROM", "ORNAPU"])
        self.assertEqual(cover.crs.to_epsg(), 5514)
        expected = (0.01 * 111320 * math.cos(math.radians(48.703))) * (0.006 * 110574)  # 0.01 x 0.006 degrees in m2
        self.assertAlmostEqual(cover.geometry.area.sum(), expected, delta=expected * 0.02)
        areas = dict(zip(cover["typ"], cover.geometry.area))
        self.assertAlmostEqual(areas["LPSTROM"], areas["ORNAPU"], delta=areas["LPSTROM"] * 0.02)  # the speckle is gone

    def test_unmapped_values_are_dropped(self):
        array = np.zeros((60, 100), dtype=np.uint8)       # 0 = no data in WorldCover
        array[:, :50] = 80                                # water
        with tempfile.TemporaryDirectory() as d:
            tif = os.path.join(d, "wc.tif")
            write_raster(tif, array)
            cover = worldcover_cover([tif], (21.200, 48.700, 21.210, 48.706), RULES, SIZE)
        self.assertEqual(list(cover["typ"]), ["VODPLO"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest tests.sk_data.test_landcover 2>&1 | tail -4`
Expected: `ModuleNotFoundError: No module named 'tools.sk_data.landcover'`.

- [ ] **Step 3: Write the module**

Create `tools/sk_data/landcover.py`:

```python
# -*- coding: utf-8 -*-
"""Land-cover polygons with a sector type: OSM polygons (precise) and ESA WorldCover (complete, 10 m)."""

import logging
import math
import os
import tempfile

import geopandas as gpd
import shapely
from osgeo import gdal, ogr, osr

from tools.sk_data.crs import project_geometries
from tools.sk_data.rules import osm_typ

gdal.UseExceptions()
log = logging.getLogger("sk_data")


def osm_cover(polygons, rules, size):
    """OSM polygons (EPSG:5514, with a 'tags' column) that map to a sector type and are big enough to matter."""
    typs = [osm_typ(rules, tags) for tags in polygons["tags"]]
    gdf = gpd.GeoDataFrame({"typ": typs}, geometry=shapely.make_valid(polygons.geometry.values), crs=5514)
    gdf = gdf[gdf["typ"].notna() & gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
    return gdf[gdf.geometry.area >= size.min_cover_m2].reset_index(drop=True)


def _pixel_area_m2(geotransform, lat):
    """Approximate area of one pixel of a lon/lat raster at latitude lat."""
    width_m = abs(geotransform[1]) * 111320.0 * math.cos(math.radians(lat))
    height_m = abs(geotransform[5]) * 110574.0
    return width_m * height_m


def worldcover_cover(tif_paths, bbox, rules, size, sieve_ha=0.5):
    """ESA WorldCover polygons (EPSG:5514) with a sector type, for the lon/lat bbox.

    Raster regions smaller than sieve_ha are merged into their neighbours, then the classes are
    polygonized. The polygons keep their exact pixel edges, so neighbouring polygons share borders.
    """
    vrt = gdal.BuildVRT("", [str(p) for p in tif_paths])
    clipped = gdal.Warp("", vrt, outputBounds=tuple(bbox), format="MEM", resampleAlg="near")
    gt = clipped.GetGeoTransform()
    pixels = max(1, int(round(sieve_ha * 1e4 / _pixel_area_m2(gt, (bbox[1] + bbox[3]) / 2))))
    log.info("WorldCover: %d x %d pixels, sieve threshold %d pixels", clipped.RasterXSize, clipped.RasterYSize, pixels)
    sieved = gdal.GetDriverByName("MEM").Create("", clipped.RasterXSize, clipped.RasterYSize, 1, gdal.GDT_Byte)
    sieved.SetGeoTransform(gt)
    sieved.SetProjection(clipped.GetProjection())
    gdal.SieveFilter(clipped.GetRasterBand(1), None, sieved.GetRasterBand(1), pixels, 4)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "wc.gpkg")
        ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        layer = ds.CreateLayer("wc", srs, ogr.wkbPolygon)
        layer.CreateField(ogr.FieldDefn("cls", ogr.OFTInteger))
        gdal.Polygonize(sieved.GetRasterBand(1), None, layer, 0, ["8CONNECTED=NO"])
        ds = layer = None  # flush
        gdf = gpd.read_file(path)
    typs = gdf["cls"].map(rules.worldcover)
    gdf = gdf[typs.notna()].copy()
    out = gpd.GeoDataFrame({"typ": typs[typs.notna()].to_numpy()},
                           geometry=project_geometries(gdf.geometry.values), crs=5514)
    return out[out.geometry.area >= size.min_cover_m2].reset_index(drop=True)
```

- [ ] **Step 4: Run to verify they pass**

Run: the command of Step 2 with `-W error::ResourceWarning` after `"$QGIS_PY"`.
Expected: `Ran 3 tests ... OK`.

- [ ] **Step 5: Commit**

```bash
git add tools/sk_data/landcover.py tests/sk_data/test_landcover.py
git commit -m "Add land-cover polygons from OSM and ESA WorldCover

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Reference layers, municipality list, export and validation

**Files:**
- Create: `tools/sk_data/layers.py`, `tools/sk_data/places.py`, `tools/sk_data/export.py`, `tools/sk_data/validate.py`, `tests/sk_data/test_layers_places_export.py`

**Interfaces:**
- Produces: `layers.barrier_lines(lines) -> list[geometry]`; `layers.output_layers(lines, sectors, region) -> {'cesta','lespru','vodtok': GeoDataFrame}` (`lines` has a `tags` column, EPSG:5514).
- Produces: `places.admin_areas(polygons, level) -> GeoDataFrame[name, geometry]`; `places.build_places(municipalities, districts, points, region, region_code, transformer=None) -> list[tuple]`; `places.write_csv(rows, path)`.
- Produces: `export.sectors_frame(sectors) -> GeoDataFrame`; `export.zabaged_dir(out_dir)`; `export.write_region(out_dir, sectors, layers, metadata)`; constants `PLUGIN_DATA_VERSION`, `LAST_SECTOR_ID`, `ATTRIBUTION`.
- Produces: `validate.validate(out_dir, region, size, classes, area_tolerance=0.02) -> (problems: list[str], report: dict)`.

- [ ] **Step 1: Write the tests**

Create `tests/sk_data/test_layers_places_export.py`:

```python
import csv
import json
import os
import tempfile
import unittest

import geopandas as gpd
from shapely.geometry import LineString, Point, box

from tools.sk_data import export, layers, places
from tools.sk_data.crs import wgs84_to_sjtsk
from tools.sk_data.config import SectorSize
from tools.sk_data.rules import load_rules
from tools.sk_data.validate import validate


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def line_frame(rows):
    """rows: [(tags, coords)] -> GeoDataFrame in EPSG:5514."""
    return gpd.GeoDataFrame({"tags": [t for t, _ in rows]}, geometry=[LineString(c) for _, c in rows], crs=5514)


class LayersTest(unittest.TestCase):
    def setUp(self):
        self.lines = line_frame([
            ({"highway": "residential", "name": "Hlavna"}, [(0, 0), (100, 0)]),
            ({"highway": "residential", "tunnel": "yes"}, [(0, 10), (100, 10)]),
            ({"highway": "footway"}, [(0, 20), (100, 20)]),
            ({"highway": "track"}, [(1000, 1000), (1100, 1000)]),    # in the forest sector
            ({"highway": "track"}, [(0, 500), (100, 500)]),          # in a field
            ({"railway": "rail"}, [(0, 30), (100, 30)]),
            ({"waterway": "stream", "name": "Potok"}, [(0, 40), (100, 40)]),
            ({"waterway": "ditch"}, [(0, 50), (100, 50)]),
            ({"railway": "abandoned"}, [(0, 60), (100, 60)]),
        ])
        self.sectors = gpd.GeoDataFrame({"typ": ["LPSTROM", "ORNAPU"]},
                                        geometry=[box(900, 900, 1200, 1100), box(-50, 400, 200, 600)], crs=5514)

    def test_barrier_lines_are_main_roads_rail_and_streams_without_tunnels(self):
        self.assertEqual(len(layers.barrier_lines(self.lines)), 3)  # residential, rail, stream

    def test_output_layers(self):
        out = layers.output_layers(self.lines, self.sectors, box(-1e4, -1e4, 1e4, 1e4))
        self.assertEqual(sorted(out), ["cesta", "lespru", "vodtok"])
        self.assertEqual(len(out["lespru"]), 1)                       # the track in the forest
        self.assertEqual(len(out["cesta"]), 3)                        # residential, footway, track in the field
        self.assertEqual(len(out["vodtok"]), 2)                       # stream and ditch
        self.assertEqual(list(out["cesta"].columns), ["highway", "name", "geometry"])
        self.assertEqual(out["cesta"].crs.to_epsg(), 5514)

    def test_lines_outside_the_region_are_dropped(self):
        out = layers.output_layers(self.lines, self.sectors, box(900, 900, 1200, 1100))
        self.assertEqual(len(out["lespru"]), 1)
        self.assertEqual(len(out["cesta"]), 0)


class PlacesTest(unittest.TestCase):
    def setUp(self):
        self.region = box(21.0, 48.5, 21.5, 48.9)
        self.munis = gpd.GeoDataFrame({"name": ["Testov", "Bezuzla", "Cudzie"]},
                                      geometry=[box(21.20, 48.70, 21.21, 48.71), box(21.30, 48.70, 21.31, 48.71), box(25.0, 48.7, 25.1, 48.8)], crs=4326)
        self.districts = gpd.GeoDataFrame({"name": ["Okres Test"]}, geometry=[box(21.1, 48.6, 21.4, 48.8)], crs=4326)
        self.points = gpd.GeoDataFrame(
            {"tags": [{"place": "village", "name": "Testov"}, {"place": "hamlet", "name": "Testov"}, {"amenity": "pub", "name": "X"}]},
            geometry=[Point(21.205, 48.705), Point(21.202, 48.702), Point(21.305, 48.705)], crs=4326)

    def test_rows(self):
        rows = places.build_places(self.munis, self.districts, self.points, self.region, "ke")
        self.assertEqual([r[3] for r in rows], ["Bezuzla", "Testov"])          # the one outside the region is skipped
        testov = rows[1]
        x, y = wgs84_to_sjtsk().transform(21.205, 48.705)                       # the village node, not the hamlet
        self.assertEqual((testov[0], testov[1]), (round(x), round(y)))
        self.assertEqual(testov[2:], (0, "Testov", 0, "Okres Test", "KE"))

    def test_municipality_without_a_place_node_uses_a_point_inside_it(self):
        rows = places.build_places(self.munis, self.districts, self.points, self.region, "ke")
        bezuzla = rows[0]
        x, y = wgs84_to_sjtsk().transform(21.305, 48.705)
        self.assertAlmostEqual(bezuzla[0], x, delta=600)
        self.assertAlmostEqual(bezuzla[1], y, delta=600)

    def test_admin_areas_and_csv(self):
        polygons = gpd.GeoDataFrame(
            {"tags": [{"boundary": "administrative", "admin_level": "8", "name": "Testov"},
                      {"boundary": "administrative", "admin_level": "6", "name": "Okres Test"},
                      {"landuse": "forest"}]},
            geometry=[box(0, 0, 1, 1)] * 3, crs=4326)
        self.assertEqual(list(places.admin_areas(polygons, "8")["name"]), ["Testov"])
        self.assertEqual(list(places.admin_areas(polygons, "6")["name"]), ["Okres Test"])
        rows = [(-1, -2, 0, "Šaľa", 0, "Okres", "KE")]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.csv")
            places.write_csv(rows, path)
            self.assertEqual(read_text(path), "-1;-2;0;Šaľa;0;Okres;KE\n")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(next(csv.reader(f, delimiter=";"))[3], "Šaľa")


class ExportValidateTest(unittest.TestCase):
    def build(self, d, sectors, region_geom):
        frame = export.sectors_frame(sectors)
        lines = {"cesta": gpd.GeoDataFrame({"highway": ["x"], "name": [None]}, geometry=[LineString([(0, 0), (1, 1)])], crs=5514),
                 "lespru": gpd.GeoDataFrame({"highway": [], "name": []}, geometry=[], crs=5514),
                 "vodtok": gpd.GeoDataFrame({"waterway": ["stream"], "name": ["p"]}, geometry=[LineString([(0, 0), (1, 1)])], crs=5514)}
        export.write_region(d, frame, lines, {"landcover": "osm"})
        return validate(d, region_geom, SectorSize(), load_rules().classes)

    def test_sectors_frame_refuses_invalid_or_multipart_geometries(self):
        from shapely.geometry import Polygon
        bowtie = Polygon([(0, 0), (100, 100), (100, 0), (0, 100)])
        with self.assertRaises(ValueError):
            export.sectors_frame([(bowtie, "A")])
        with self.assertRaises(ValueError):
            export.sectors_frame([(box(0, 0, 1, 1).union(box(5, 5, 6, 6)), "A")])

    def test_good_output_passes(self):
        sectors = [(box(0, 0, 300, 250), "LPSTROM"), (box(300, 0, 600, 250), "ORNAPU")]  # 7.5 ha each
        with tempfile.TemporaryDirectory() as d:
            problems, report = self.build(d, sectors, box(0, 0, 600, 250))
            self.assertEqual(problems, [])
            self.assertEqual(report["sectors"], 2)
            self.assertEqual(report["share_in_min_max"], 1.0)
            self.assertEqual(report["area_ratio"], 1.0)
            self.assertEqual(json.loads(read_text(os.path.join(d, "metadata.json")))["version"], "2020-01-01")
            self.assertEqual(read_text(os.path.join(d, "vektor", "ZABAGED", "lastsectorid.txt")), "1000000")
            self.assertIn("OpenStreetMap", read_text(os.path.join(d, "ATTRIBUTION.txt")))

    def test_a_sector_slightly_over_the_maximum_is_allowed_but_counted(self):
        sectors = [(box(0, 0, 300, 250), "LPSTROM"), (box(300, 0, 600, 283), "ORNAPU")]   # 7.5 ha and 8.49 ha
        with tempfile.TemporaryDirectory() as d:
            region = sectors[0][0].union(sectors[1][0])
            problems, report = self.build(d, sectors, region)
            self.assertEqual(problems, [])
            self.assertEqual(report["sectors_over_max"], 1)
            self.assertEqual(report["sectors_under_tiny"], 0)

    def test_problems_are_reported(self):
        sectors = [(box(0, 0, 300, 250), "NOPE"), (box(200, 0, 700, 400), "ORNAPU")]   # unknown typ, overlap, one too big
        with tempfile.TemporaryDirectory() as d:
            problems, _ = self.build(d, sectors, box(0, 0, 300, 250))
            text = " | ".join(problems)
            self.assertIn("unknown typ", text)
            self.assertIn("overlap", text)
            self.assertIn("larger than", text)
            self.assertIn("differs from the region area", text)

    def test_missing_files_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            problems, _ = validate(d, box(0, 0, 1, 1), SectorSize(), load_rules().classes)
            self.assertIn("missing sectors.shp", problems)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest tests.sk_data.test_layers_places_export 2>&1 | tail -4`
Expected: `ModuleNotFoundError: No module named 'tools.sk_data.layers'`.

- [ ] **Step 3: Write the modules**

Create `tools/sk_data/layers.py`:

```python
# -*- coding: utf-8 -*-
"""Line layers from OSM: the lines that bound sectors, and the cesta / lespru / vodtok reference layers."""

import geopandas as gpd
import numpy as np
import shapely
from shapely.strtree import STRtree

BARRIER_HIGHWAYS = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
                    "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street"}
BARRIER_RAILWAYS = {"rail", "light_rail"}
BARRIER_WATERWAYS = {"river", "stream", "canal"}
TRACK_HIGHWAYS = {"track", "path", "bridleway"}
OUTPUT_WATERWAYS = {"river", "stream", "canal", "drain", "ditch"}
FOREST_TYPES = ("LPSTROM", "LPKROV")
TUNNEL_VALUES = {"yes", "culvert", "building_passage"}


def _is_tunnel(tags):
    return tags.get("tunnel") in TUNNEL_VALUES


def barrier_lines(lines):
    """Geometries of the roads, railways and waterways that bound sectors (lines: GeoDataFrame with 'tags')."""
    keep = np.array([
        (t.get("highway") in BARRIER_HIGHWAYS or t.get("railway") in BARRIER_RAILWAYS
         or t.get("waterway") in BARRIER_WATERWAYS) and not _is_tunnel(t)
        for t in lines["tags"]], dtype=bool)
    return list(lines.geometry.values[keep])


def output_layers(lines, sectors, region):
    """The cesta (roads and paths), lespru (tracks in forest) and vodtok (streams) layers for the region.

    lines: GeoDataFrame with 'tags' (EPSG:5514); sectors: GeoDataFrame with 'typ'; region: polygon.
    Lines that touch the region are kept whole (the plugin clips by extent itself).
    """
    lines = lines[shapely.intersects(lines.geometry.values, region)]
    tags = list(lines["tags"])
    frame = gpd.GeoDataFrame({"highway": [t.get("highway") for t in tags],
                              "waterway": [t.get("waterway") for t in tags],
                              "name": [t.get("name") for t in tags]},
                             geometry=lines.geometry.values, crs=5514)
    tunnel = np.array([_is_tunnel(t) for t in tags], dtype=bool)
    is_road = frame["highway"].notna().to_numpy() & ~tunnel
    is_track = frame["highway"].isin(TRACK_HIGHWAYS).to_numpy()
    in_forest = np.zeros(len(frame), dtype=bool)
    forest = sectors[sectors["typ"].isin(FOREST_TYPES)]
    if len(forest) and is_track.any():
        midpoints = shapely.line_interpolate_point(frame.geometry.values, 0.5, normalized=True)
        hits = STRtree(list(forest.geometry)).query(midpoints, predicate="within")[0]
        in_forest[np.unique(hits)] = True
    in_forest_track = is_road & is_track & in_forest
    return {
        "cesta": frame[is_road & ~in_forest_track][["highway", "name", "geometry"]].reset_index(drop=True),
        "lespru": frame[in_forest_track][["highway", "name", "geometry"]].reset_index(drop=True),
        "vodtok": frame[frame["waterway"].isin(OUTPUT_WATERWAYS).to_numpy() & ~tunnel][["waterway", "name", "geometry"]].reset_index(drop=True),
    }
```

Create `tools/sk_data/places.py`:

```python
# -*- coding: utf-8 -*-
"""Municipality list in the format of the plugin's ui/*.csv: x;y;code;name;okres code;okres;REGION."""

import csv

import shapely
from shapely.strtree import STRtree

from tools.sk_data.crs import wgs84_to_sjtsk

PLACE_TYPES = {"city", "town", "village"}
MUNICIPALITY_LEVEL = "8"
DISTRICT_LEVEL = "6"


def admin_areas(polygons, level):
    """Name + geometry of the administrative areas of an admin_level (polygons: GeoDataFrame with 'tags')."""
    keep = [t.get("boundary") == "administrative" and t.get("admin_level") == level and bool(t.get("name"))
            for t in polygons["tags"]]
    selected = polygons[keep]
    out = selected[["geometry"]].copy()
    out["name"] = [t["name"] for t in selected["tags"]]
    return out.reset_index(drop=True)


def build_places(municipalities, districts, points, region, region_code, transformer=None):
    """Rows (x, y, 0, name, 0, district, REGION) in S-JTSK for the municipalities inside the region.

    All inputs are in EPSG:4326. The position is the OSM place node (city, town or village) inside the
    municipality, preferring one with the same name; without one, a point inside the boundary.
    The two zero columns are codes the plugin does not read.
    """
    transformer = transformer or wgs84_to_sjtsk()
    nodes = [(g, t["name"]) for g, t in zip(points.geometry, points["tags"])
             if t.get("place") in PLACE_TYPES and t.get("name")]
    node_tree = STRtree([g for g, _ in nodes]) if nodes else None
    district_tree = STRtree(list(districts.geometry)) if len(districts) else None
    rows = []
    for name, polygon in zip(municipalities["name"], municipalities.geometry):
        representative = polygon.representative_point()
        if not shapely.contains(region, representative):
            continue
        inside = [nodes[i] for i in node_tree.query(polygon, predicate="contains")] if node_tree else []
        same_name = [g for g, n in inside if n == name]
        centre = (same_name or [g for g, _ in inside] or [representative])[0]
        district = ""
        if district_tree is not None:
            hits = district_tree.query(centre, predicate="within")
            if len(hits):
                district = districts["name"].iloc[int(hits[0])]
        x, y = transformer.transform(centre.x, centre.y)
        rows.append((int(round(x)), int(round(y)), 0, name, 0, district, region_code.upper()))
    rows.sort(key=lambda r: (r[3], r[5]))
    return rows


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter=";", lineterminator="\n").writerows(rows)
```

Create `tools/sk_data/export.py`:

```python
# -*- coding: utf-8 -*-
"""Write a region in the folder layout the plugin reads: kraje/<key>/vektor/ZABAGED/*.shp and metadata."""

import json
import os
from datetime import datetime, timezone

import geopandas as gpd

PLUGIN_DATA_VERSION = "2020-01-01"  # what Project.checkRegion in the plugin requires of metadata.json
LAST_SECTOR_ID = 1000000            # the plugin's own fallback when lastsectorid.txt is missing
ATTRIBUTION = """Data attribution

Sectors, roads, tracks and streams were derived from:
  OpenStreetMap data, (c) OpenStreetMap contributors, licensed under the ODbL
  (https://www.openstreetmap.org/copyright).
  ESA WorldCover 2021 v200, (c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data
  (2021) processed by ESA WorldCover consortium, licensed under CC BY 4.0
  (https://creativecommons.org/licenses/by/4.0/). Only when the data was built with --landcover osm+worldcover.

Share-alike: publishing this derived data requires ODbL handling. Keep this notice with the data.
"""


def sectors_frame(sectors):
    """GeoDataFrame (EPSG:5514) with the string field 'typ' from [(Polygon, typ)]. Every geometry must be a valid Polygon."""
    broken = sum(1 for g, _ in sectors if g.geom_type != "Polygon" or not g.is_valid)
    if broken:
        raise ValueError("%d sectors are not valid single polygons" % broken)
    return gpd.GeoDataFrame({"typ": [t for _, t in sectors]}, geometry=[g for g, _ in sectors], crs=5514)


def zabaged_dir(out_dir):
    return os.path.join(out_dir, "vektor", "ZABAGED")


def write_region(out_dir, sectors, layers, metadata):
    """Write sectors.shp, cesta/lespru/vodtok.shp, lastsectorid.txt, metadata.json and ATTRIBUTION.txt."""
    folder = zabaged_dir(out_dir)
    os.makedirs(folder, exist_ok=True)
    sectors.to_file(os.path.join(folder, "sectors.shp"), encoding="utf-8")
    for name, frame in layers.items():
        frame.to_file(os.path.join(folder, name + ".shp"), encoding="utf-8")
    with open(os.path.join(folder, "lastsectorid.txt"), "w") as f:
        f.write(str(LAST_SECTOR_ID))
    meta = {"version": PLUGIN_DATA_VERSION, "built": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    meta.update(metadata)
    with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, "ATTRIBUTION.txt"), "w", encoding="utf-8") as f:
        f.write(ATTRIBUTION)
```

Create `tools/sk_data/validate.py`:

```python
# -*- coding: utf-8 -*-
"""Checks of a written region against what the plugin expects. Returns problems and a report."""

import json
import os

import geopandas as gpd
import numpy as np
import shapely
from shapely.strtree import STRtree

from tools.sk_data.crs import wgs84_to_sjtsk
from tools.sk_data.export import PLUGIN_DATA_VERSION, zabaged_dir

KOSICE = (21.2611, 48.7164)          # lon, lat
KOSICE_SJTSK = (-262580.66, -1240038.58)  # EPSG:4836 result


def validate(out_dir, region, size, classes, area_tolerance=0.02):
    """Return (problems, report). problems is empty when the output is usable by the plugin.

    region: the region polygon in EPSG:5514.
    """
    problems = []
    folder = zabaged_dir(out_dir)
    for name in ("sectors", "cesta", "lespru", "vodtok"):
        if not os.path.exists(os.path.join(folder, name + ".shp")):
            problems.append("missing %s.shp" % name)
    if problems:
        return problems, {}
    sectors = gpd.read_file(os.path.join(folder, "sectors.shp"))
    report = {"sectors": len(sectors)}

    if sectors.crs is None or sectors.crs.to_epsg() != 5514:
        problems.append("sectors.shp is not EPSG:5514")
    if "typ" not in sectors.columns:
        problems.append("sectors.shp has no 'typ' field")
    else:
        unknown = sorted(set(sectors["typ"]) - set(classes))
        if unknown:
            problems.append("unknown typ values: %s" % unknown)
    if not (sectors.geometry.geom_type == "Polygon").all():
        problems.append("sectors.shp has geometries that are not single polygons")
    invalid = int((~sectors.geometry.is_valid).sum())
    if invalid:
        problems.append("%d invalid sector geometries" % invalid)

    areas = sectors.geometry.area.to_numpy()
    total = float(areas.sum())
    report["total_ha"] = round(total / 1e4)
    report["region_ha"] = round(region.area / 1e4)
    report["area_ratio"] = round(total / region.area, 4)
    report["area_ha_percentiles_5_25_50_75_95"] = [round(float(np.percentile(areas, q)) / 1e4, 1) for q in (5, 25, 50, 75, 95)]
    in_range = (areas >= size.min_m2) & (areas <= size.max_m2 * 1.01)
    report["share_in_min_max"] = round(float(in_range.mean()), 3)
    report["share_of_area_in_min_max"] = round(float(areas[in_range].sum() / total), 3)
    report["sectors_over_max"] = int((areas > size.max_m2 * 1.01).sum())   # fragments absorbed after splitting
    report["sectors_under_tiny"] = int((areas < size.tiny_m2).sum())
    limit = size.max_m2 + size.tiny_m2                                      # an absorbed fragment adds less than tiny_ha
    too_big = int((areas > limit).sum())
    if too_big:
        problems.append("%d sectors are larger than %.1f ha" % (too_big, limit / 1e4))
    if abs(total / region.area - 1) > area_tolerance:
        problems.append("sector area %.0f ha differs from the region area %.0f ha by more than %.1f%%"
                        % (total / 1e4, region.area / 1e4, area_tolerance * 100))

    geoms = np.array(sectors.geometry.values, dtype=object)
    a_idx, b_idx = STRtree(geoms).query(geoms, predicate="intersects")
    keep = a_idx < b_idx
    overlap = shapely.area(shapely.intersection(geoms[a_idx[keep]], geoms[b_idx[keep]]))
    overlapping = int((overlap > 1.0).sum())
    if overlapping:
        problems.append("%d pairs of sectors overlap by more than 1 m2" % overlapping)

    by_typ = sectors.groupby("typ")["typ"].count().to_dict() if "typ" in sectors.columns else {}
    report["count_by_typ"] = {k: int(v) for k, v in sorted(by_typ.items())}
    if "typ" in sectors.columns:
        report["other_share_of_area"] = round(float(areas[(sectors["typ"] == "OTHER").to_numpy()].sum() / total), 3)

    try:
        with open(os.path.join(folder, "lastsectorid.txt")) as f:
            int(f.read())
    except (OSError, ValueError):
        problems.append("lastsectorid.txt is missing or not an integer")
    try:
        with open(os.path.join(out_dir, "metadata.json"), encoding="utf-8") as f:
            if json.load(f).get("version") != PLUGIN_DATA_VERSION:
                problems.append("metadata.json version is not %s" % PLUGIN_DATA_VERSION)
    except (OSError, ValueError):
        problems.append("metadata.json is missing or invalid")

    x, y = wgs84_to_sjtsk().transform(*KOSICE)
    if abs(x - KOSICE_SJTSK[0]) > 1.0 or abs(y - KOSICE_SJTSK[1]) > 1.0:
        problems.append("the WGS84 -> S-JTSK transformation does not give the Slovak result at Kosice (%.1f, %.1f)" % (x, y))
    return problems, report
```

- [ ] **Step 4: Run to verify they pass**

Run: the command of Step 2 with `-W error::ResourceWarning` after `"$QGIS_PY"`.
Expected: `Ran 11 tests ... OK`.

- [ ] **Step 5: Commit**

```bash
git add tools/sk_data/layers.py tools/sk_data/places.py tools/sk_data/export.py tools/sk_data/validate.py tests/sk_data/test_layers_places_export.py
git commit -m "Add reference layers, municipality list, region export and validation

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Pipeline, command line and QGIS project

**Files:**
- Create: `tools/sk_data/pipeline.py`, `tools/sk_data/__main__.py`, `tools/sk_data/qgis_project.py`, `tests/sk_data/test_pipeline.py`, `tests/sk_data/test_qgis_project.py`

**Interfaces:**
- Consumes: everything from Tasks 1-6.
- Produces: `pipeline.build_region(key, root, size=None, landcover_mode="osm+worldcover", out_dir=None, osm_pbf=None, worldcover_paths=None, region_name=None, area_tolerance=0.02, window=None) -> (problems, report, out_dir)` (`window=(lon, lat)` builds a 12 x 10 km area); `pipeline.LANDCOVER_MODES`; `qgis_project.init_qgis(qgis_app=None)`; `qgis_project.build_project(region_dirs, out_path, locale="en", styles_dir=STYLES_DIR, bookmarks=()) -> list[str]` (layer names; `bookmarks` is `[(name, lon, lat)]`), `qgis_project.TYPE_STYLE` (typ -> colour and English name, 18 entries) and `qgis_project.typ_renderer()`; the commands `download`, `build` (with `--window LON,LAT`), `rules`, `project` (with repeatable `--bookmark NAME=LON,LAT`) of `python -m tools.sk_data`.

- [ ] **Step 1: Write the tests**

Create `tests/sk_data/test_pipeline.py`:

```python
import contextlib
import io
import json
import os
import tempfile
import unittest

import numpy as np
from osgeo import gdal, osr

from tests.sk_data.osm_fixture import write_fixture
from tests.sk_data.test_landcover import write_raster
from tools.sk_data import pipeline
from tools.sk_data.__main__ import main
from tools.sk_data.config import SectorSize
from tools.sk_data.rules import guessed_rules_text


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.osm = write_fixture(os.path.join(self.root, "mini.osm"))

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, **kwargs):
        return pipeline.build_region("ke", self.root, osm_pbf=self.osm, region_name="Test kraj",
                                     area_tolerance=0.15, **kwargs)  # tiny region: whole sectors at the border weigh a lot

    def test_osm_only(self):
        problems, report, out_dir = self.build(landcover_mode="osm")
        self.assertEqual(problems, [])
        self.assertGreater(report["sectors"], 50)
        self.assertEqual(set(report["count_by_typ"]), {"LPSTROM", "OTHER"})   # the fixture forest, everything else unlabelled
        for name in ("sectors", "cesta", "lespru", "vodtok"):
            self.assertTrue(os.path.exists(os.path.join(out_dir, "vektor", "ZABAGED", name + ".shp")), name)
        self.assertEqual(read_json(os.path.join(out_dir, "metadata.json"))["landcover"], "osm")
        self.assertTrue(os.path.exists(os.path.join(out_dir, "places.csv")))

    def test_worldcover_fills_the_gaps(self):
        tif = os.path.join(self.root, "wc.tif")
        write_raster(tif, np.full((700, 700), 40, dtype=np.uint8), origin=(21.17, 48.75))  # cropland everywhere, 0.07 deg square
        problems, report, _ = self.build(landcover_mode="osm+worldcover", worldcover_paths=[tif])
        self.assertEqual(problems, [])
        self.assertEqual(set(report["count_by_typ"]), {"LPSTROM", "ORNAPU"})
        self.assertEqual(report["other_share_of_area"], 0.0)

    def test_window_builds_a_12_by_10_km_area_around_a_point(self):
        problems, report, out_dir = self.build(landcover_mode="osm", window=(21.205, 48.705))
        self.assertEqual(problems, [])
        self.assertAlmostEqual(report["region_ha"], 12000, delta=10)     # 12 x 10 km
        self.assertGreater(report["sectors"], 1000)
        self.assertEqual(report["places"], 0)                            # no municipality list for a window
        self.assertIn("LPSTROM", report["count_by_typ"])                 # the fixture forest is inside the window
        self.assertEqual(os.listdir(os.path.join(self.root, "work")), [])     # the temporary work folder is removed

    def test_each_build_uses_its_own_work_folder_that_is_removed_afterwards(self):
        self.build(landcover_mode="osm")
        self.assertEqual(os.listdir(os.path.join(self.root, "work")), [])
        with self.assertRaises(ValueError):
            self.build(landcover_mode="satellite")                           # also cleaned up when the build fails
        self.assertEqual(os.listdir(os.path.join(self.root, "work")), [])

    def test_unknown_landcover_mode(self):
        with self.assertRaises(ValueError):
            self.build(landcover_mode="satellite")

    def test_missing_worldcover_tiles_explain_what_to_do(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            self.build(landcover_mode="osm+worldcover")
        self.assertIn("download", str(ctx.exception))

    def test_custom_sector_size_is_respected(self):
        problems, report, _ = self.build(landcover_mode="osm", size=SectorSize(min_ha=2.0, target_ha=3.0, max_ha=4.0))
        self.assertEqual(problems, [])
        self.assertGreater(report["sectors"], 200)


class CliTest(unittest.TestCase):
    def test_rules_command_lists_guesses(self):
        self.assertIn("natural=wetland -> MAZCHU", guessed_rules_text())

    def run_expecting_usage_error(self, argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            main(argv)
        self.assertEqual(ctx.exception.code, 2)
        return err.getvalue()

    def test_window_needs_an_output_folder(self):
        self.assertIn("--window needs --out", self.run_expecting_usage_error(["build", "--region", "ke", "--window", "21.26,48.72"]))

    def test_window_value_must_be_lon_comma_lat(self):
        self.assertIn("LON,LAT", self.run_expecting_usage_error(["build", "--region", "ke", "--window", "nonsense", "--out", "/tmp/x"]))

    def test_help_exits_cleanly(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            main(["build", "--help"])
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
```

Create `tests/sk_data/test_qgis_project.py`:

```python
import os
import tempfile
import unittest

try:
    import qgis.core  # noqa: F401
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

from tests.sk_data.osm_fixture import write_fixture


@unittest.skipUnless(HAVE_QGIS, "needs QGIS's Python (source tools/dev/qgis_env.sh)")
class QgisProjectTest(unittest.TestCase):
    def test_project_contains_a_valid_basemap_and_all_layers(self):
        from qgis.core import QgsProject
        from tools.sk_data import pipeline, qgis_project
        with tempfile.TemporaryDirectory() as d:
            osm = write_fixture(os.path.join(d, "mini.osm"))
            problems, _, out_dir = pipeline.build_region("ke", d, osm_pbf=osm, region_name="Test kraj",
                                                         landcover_mode="osm", area_tolerance=0.15)
            self.assertEqual(problems, [])
            app = qgis_project.init_qgis()
            try:
                out = os.path.join(d, "p.qgz")
                names = qgis_project.build_project([("test", out_dir)], out, bookmarks=[("Fixture forest", 21.205, 48.705)])
                self.assertEqual(names[0], "OpenStreetMap")
                self.assertIn("Sectors: test", names)
                project = QgsProject()
                self.assertTrue(project.read(out))
                loaded = {layer.name(): layer.isValid() for layer in project.mapLayers().values()}
                self.assertEqual(len(loaded), 5)
                self.assertTrue(all(loaded.values()), loaded)   # an invalid basemap used to vanish silently
                self.assertFalse(project.viewSettings().defaultViewExtent().isEmpty())
                bookmarks = project.bookmarkManager().bookmarks()
                self.assertEqual([b.name() for b in bookmarks], ["Fixture forest"])
                sectors = project.mapLayersByName("Sectors: test")[0]
                renderer = sectors.renderer()
                self.assertEqual(renderer.classAttribute(), "typ")
                self.assertEqual({c.value() for c in renderer.categories()}, set(qgis_project.TYPE_STYLE))
                labels = {c.value(): c.label() for c in renderer.categories()}
                self.assertIn("Unclassified", labels["OTHER"])
                del bookmarks, renderer, sectors
                project.clear()
                del project  # QGIS objects must be gone before exitQgis(), or the process crashes
            finally:
                app.exitQgis()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest tests.sk_data.test_pipeline 2>&1 | tail -4`
Expected: `ModuleNotFoundError: No module named 'tools.sk_data.pipeline'`.

- [ ] **Step 3: Write the modules**

Create `tools/sk_data/pipeline.py`:

```python
# -*- coding: utf-8 -*-
"""Build one region: OSM (+ WorldCover) -> sectors, reference layers, municipality list -> plugin folder layout."""

import dataclasses
import json
import logging
import os
import shutil
import tempfile
import time

import geopandas as gpd
import shapely
from pyproj import Transformer
from shapely.geometry import box

from tools.sk_data import download, export, extract, landcover, layers, places
from tools.sk_data.config import MARGIN_M, REGIONS, SectorSize, region_dir, source_dir
from tools.sk_data.crs import project_geometries, to_sjtsk, wgs84_to_sjtsk
from tools.sk_data.rules import check_rules, load_rules
from tools.sk_data.sectors import build_sectors
from tools.sk_data.validate import validate

log = logging.getLogger("sk_data")
LANDCOVER_MODES = ("osm", "osm+worldcover")
WINDOW_WIDTH_M, WINDOW_HEIGHT_M = 12000.0, 10000.0   # the area the plugin clips for one search


def default_osm_path(root):
    return os.path.join(source_dir(root, "osm-slovakia"), "slovakia-latest.osm.pbf")


def default_worldcover_paths(root, bbox):
    paths = [os.path.join(source_dir(root, "esa-worldcover"), os.path.basename(download.worldcover_url(t)))
             for t in download.worldcover_tiles(bbox)]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError("missing WorldCover tiles %s; run: python -m tools.sk_data download --region <key>" % missing)
    return paths


def _within(geoms, margin):
    shapely.prepare(margin)
    return shapely.intersects(geoms, margin)


def build_region(key, root, size=None, landcover_mode="osm+worldcover", out_dir=None, osm_pbf=None,
                 worldcover_paths=None, region_name=None, area_tolerance=0.02, window=None):
    """Build and validate a region. Returns (problems, report, out_dir).

    window=(lon, lat) builds only a 12 x 10 km area around that point (fast, for inspecting a place);
    the region boundary is then not needed and no municipality list is written.
    Every call extracts into its own temporary folder under <root>/work, so builds can run side by side.
    """
    os.makedirs(os.path.join(root, "work"), exist_ok=True)
    work = tempfile.mkdtemp(prefix=key + "-", dir=os.path.join(root, "work"))
    try:
        return _build_region(key, root, work, size, landcover_mode, out_dir, osm_pbf, worldcover_paths,
                             region_name, area_tolerance, window)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _build_region(key, root, work, size, landcover_mode, out_dir, osm_pbf, worldcover_paths, region_name,
                  area_tolerance, window):
    if landcover_mode not in LANDCOVER_MODES:
        raise ValueError("landcover must be one of %s" % (LANDCOVER_MODES,))
    size = size or SectorSize()
    rules = load_rules()
    bad = check_rules(rules)
    if bad:
        raise ValueError("inconsistent rules: %s" % bad)
    name = region_name or REGIONS[key]
    pbf = osm_pbf or default_osm_path(root)
    out_dir = out_dir or region_dir(root, key)
    t0 = time.time()

    def step(message):
        log.info("[%4.0fs] %s", time.time() - t0, message)

    if window:
        cx, cy = wgs84_to_sjtsk().transform(*window)
        region = box(cx - WINDOW_WIDTH_M / 2, cy - WINDOW_HEIGHT_M / 2, cx + WINDOW_WIDTH_M / 2, cy + WINDOW_HEIGHT_M / 2)
        margin = region.buffer(MARGIN_M)
        bbox = Transformer.from_crs(5514, 4326, always_xy=True).transform_bounds(*margin.bounds)
        region_wgs = None
    else:
        boundary = extract.region_boundary(pbf, name, work)
        bbox = extract.bbox_of(boundary)
        region_wgs = shapely.union_all(boundary.geometry.values)
        region = shapely.make_valid(shapely.union_all(project_geometries(boundary.geometry.values)))
        margin = region.buffer(MARGIN_M)
    paths = extract.extract(pbf, bbox, work)
    step("region %s extracted" % (name if not window else "window %s,%s" % window))

    lines = to_sjtsk(extract.read_lines(paths["lines"]))
    lines = lines[_within(lines.geometry.values, margin)]
    polygons_wgs, buildings_wgs = extract.read_polygons(paths["polygons"])
    polygons = to_sjtsk(polygons_wgs)
    polygons = polygons[_within(polygons.geometry.values, margin)]
    buildings = shapely.make_valid(project_geometries(buildings_wgs.values))
    buildings = list(buildings[_within(buildings, margin)])
    step("loaded %d lines, %d polygons, %d buildings" % (len(lines), len(polygons), len(buildings)))

    osm = landcover.osm_cover(polygons, rules, size)
    if landcover_mode == "osm+worldcover":
        tifs = worldcover_paths or default_worldcover_paths(root, bbox)
        base = landcover.worldcover_cover(tifs, bbox, rules, size)
    else:
        base = gpd.GeoDataFrame({"typ": []}, geometry=[], crs=5514)
    step("land cover: %d OSM polygons, %d WorldCover polygons" % (len(osm), len(base)))

    boundary_lines = list(osm.geometry.boundary) + list(base.geometry.boundary)
    sector_list = build_sectors(layers.barrier_lines(lines), boundary_lines, margin, region, osm, base, buildings, size, rules.classes)
    sectors = export.sectors_frame(sector_list)
    step("%d sectors" % len(sectors))

    output = layers.output_layers(lines, sectors, region)
    rows = []
    if region_wgs is not None:
        municipalities = places.admin_areas(polygons_wgs, places.MUNICIPALITY_LEVEL)
        districts = places.admin_areas(polygons_wgs, places.DISTRICT_LEVEL)
        points = extract.read_points(paths["points"])
        rows = places.build_places(municipalities, districts, points, region_wgs, key)

    manifest_path = os.path.join(root, "source", "sources.json")
    sources = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            sources = json.load(f)
    export.write_region(out_dir, sectors, output, {
        "region": key, "region_name": name, "landcover": landcover_mode, "window": window,
        "sector_size": dataclasses.asdict(size), "sources": sources})
    places.write_csv(rows, os.path.join(out_dir, "places.csv"))
    step("written to %s (%d places)" % (out_dir, len(rows)))

    problems, report = validate(out_dir, region, size, rules.classes, area_tolerance)
    report["places"] = len(rows)
    report["seconds"] = round(time.time() - t0)
    return problems, report, out_dir
```

Create `tools/sk_data/qgis_project.py`:

```python
# -*- coding: utf-8 -*-
"""Build a QGIS project to inspect one or more built regions, with the plugin's own layer styles."""

import os
from pathlib import Path

STYLES_DIR = Path(__file__).resolve().parents[2] / "styles"
OSM_TILES = "type=xyz&url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19&zmin=0"


# typ -> (fill colour, English legend name). The plugin's own style (styles/sectors_unique_*.qml) lacks most of
# these types (built-up, gardens, parks, cemeteries, wetland), so the inspection project uses this one.
TYPE_STYLE = {
    "LPSTROM": ("#1b7837", "Forest"),
    "LPKROV": ("#7fbf7b", "Shrubs"),
    "ORNAPU": ("#e6c15a", "Arable land"),
    "TRTRPO": ("#b8e186", "Grassland"),
    "SADZAH": ("#f4a582", "Orchard, garden, allotment"),
    "VINICE": ("#c51b7d", "Vineyard"),
    "AREZAS": ("#bdbdbd", "Built-up area"),
    "ARUCZA": ("#7b7b7b", "Industrial, institutional"),
    "HRBITO": ("#8c6bb1", "Cemetery"),
    "ZAHPAR": ("#41ab5d", "Park, sports ground"),
    "VODPLO": ("#3182bd", "Water"),
    "KOLEJI": ("#252525", "Railway land"),
    "MAZCHU": ("#41b6c4", "Wetland"),
    "SKLADK": ("#a6611a", "Landfill"),
    "ULOMIS": ("#bf812d", "Quarry"),
    "ELEKTR": ("#e31a1c", "Power plant"),
    "LETISTE": ("#fdae61", "Airport"),
    "OTHER": ("#ff7f00", "Unclassified (no land-use data)"),
}
BOOKMARK_SIZE_M = (12000.0, 8000.0)   # width, height of the area a bookmark zooms to


def init_qgis(qgis_app=None):
    """Start QGIS without a GUI, with the data-provider plugins loaded (needed for the web basemap)."""
    from qgis.core import QgsApplication
    qgis_app = qgis_app or os.environ.get("QGIS_APP", "/Applications/QGIS-LTR.app")
    QgsApplication.setPrefixPath(os.path.join(qgis_app, "Contents", "MacOS"), True)
    QgsApplication.setPluginPath(os.path.join(qgis_app, "Contents", "PlugIns", "qgis"))
    app = QgsApplication([], False)
    app.initQgis()
    return app


def typ_renderer():
    """Categorized renderer on 'typ' with the colours and English names of TYPE_STYLE."""
    from qgis.core import QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsRendererCategory
    categories = []
    for typ, (colour, name) in TYPE_STYLE.items():
        symbol = QgsFillSymbol.createSimple({"color": colour, "outline_color": "#555555", "outline_width": "0.1"})
        categories.append(QgsRendererCategory(typ, symbol, "%s (%s)" % (name, typ)))
    return QgsCategorizedSymbolRenderer("typ", categories)


def build_project(region_dirs, out_path, locale="en", styles_dir=STYLES_DIR, bookmarks=()):
    """Write a .qgz with an OpenStreetMap basemap, streams, roads, forest tracks and one sectors layer per region.

    region_dirs: [(label, region folder)]; streams, roads and tracks come from the first folder.
    bookmarks: [(name, lon, lat)]: spatial bookmarks (a 12 x 8 km view); the project opens on the first one.
    Returns the list of layer names written. Raises if a layer is invalid (an invalid basemap is dropped
    silently by QGIS otherwise).
    """
    from qgis.core import (QgsBookmark, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject,
                           QgsRasterLayer, QgsReferencedRectangle, QgsRectangle, QgsVectorLayer)
    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    basemap = QgsRasterLayer(OSM_TILES, "OpenStreetMap", "wms")
    if not basemap.isValid():
        raise RuntimeError("the OpenStreetMap basemap layer is invalid (data provider plugins not loaded?)")
    first = region_dirs[0][1]
    shp = lambda folder, name: os.path.join(folder, "vektor", "ZABAGED", name + ".shp")
    entries = [(basemap, None)]
    for name, label in (("vodtok", "Streams (vodtok)"), ("cesta", "Roads and paths (cesta)"), ("lespru", "Forest tracks (lespru)")):
        entries.append((QgsVectorLayer(shp(first, name), label, "ogr"), "%s_%s.qml" % (name, locale)))
    for label, folder in region_dirs:
        entries.append((QgsVectorLayer(shp(folder, "sectors"), "Sectors: " + label, "ogr"), "sectors_unique_%s.qml" % locale))
    for layer, style in entries:
        if not layer.isValid():
            raise RuntimeError("invalid layer: %s" % layer.name())
        if style and style.startswith("sectors_"):
            layer.setRenderer(typ_renderer())
        elif style:
            layer.loadNamedStyle(str(Path(styles_dir) / style))
        project.addMapLayer(layer)
    layers = [layer for layer, _ in entries]
    root = project.layerTreeRoot()
    root.setHasCustomLayerOrder(True)
    root.setCustomLayerOrder(list(reversed(layers)))
    root.findLayer(layers[2].id()).setItemVisibilityChecked(False)       # 35,000 road lines: hidden by default
    for layer in layers[4:]:
        layer.setOpacity(0.7)
    for layer in layers[5:]:
        root.findLayer(layer.id()).setItemVisibilityChecked(False)        # show one sectors layer at a time
    extent = QgsCoordinateTransform(layers[4].crs(), project.crs(), project).transformBoundingBox(layers[4].extent())
    extent.scale(1.05)
    to_map = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), project.crs(), project)
    for name, lon, lat in bookmarks:
        centre = to_map.transform(QgsPointXY(lon, lat))
        view = QgsRectangle(centre.x() - BOOKMARK_SIZE_M[0] / 2, centre.y() - BOOKMARK_SIZE_M[1] / 2,
                            centre.x() + BOOKMARK_SIZE_M[0] / 2, centre.y() + BOOKMARK_SIZE_M[1] / 2)
        bookmark = QgsBookmark()
        bookmark.setName(name)
        bookmark.setExtent(QgsReferencedRectangle(view, project.crs()))
        project.bookmarkManager().addBookmark(bookmark)
        if name == bookmarks[0][0]:
            extent = view
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent, project.crs()))
    project.viewSettings().setPresetFullExtent(QgsReferencedRectangle(extent, project.crs()))
    if not project.write(str(out_path)):
        raise RuntimeError("could not write %s" % out_path)
    return [layer.name() for layer in layers]
```

Create `tools/sk_data/__main__.py`:

```python
# -*- coding: utf-8 -*-
"""Command line: python -m tools.sk_data <download|build|rules|project> ... (run with QGIS's Python)."""

import argparse
import json
import logging
import os
import sys

from tools.sk_data import download, extract, pipeline, qgis_project
from tools.sk_data.config import REGIONS, SectorSize, data_root, source_dir
from tools.sk_data.rules import guessed_rules_text


def _size(args):
    return SectorSize(min_ha=args.min_ha, target_ha=args.target_ha, max_ha=args.max_ha)


def cmd_download(args):
    root = data_root()
    download.fetch_sources(root, None, include_worldcover=False)
    boundary = extract.region_boundary(pipeline.default_osm_path(root), REGIONS[args.region], os.path.join(root, "work", args.region))
    manifest = download.fetch_sources(root, extract.bbox_of(boundary), include_worldcover=not args.no_worldcover)
    print(json.dumps({k: {"bytes": v["bytes"], "path": v["path"]} for k, v in manifest.items()}, indent=1))
    return 0


def _window(parser, value):
    try:
        lon, lat = (float(part) for part in value.split(","))
    except ValueError:
        parser.error("--window must be LON,LAT, for example 21.2611,48.7164")
    return lon, lat


def cmd_build(args):
    root = data_root()
    problems, report, out_dir = pipeline.build_region(
        args.region, root, size=_size(args), landcover_mode=args.landcover, out_dir=args.out, window=args.window)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if problems:
        print("\nVALIDATION FAILED:", *problems, sep="\n  - ")
        return 1
    print("\nvalidation passed; output in", out_dir)
    return 0


def cmd_rules(args):
    print(guessed_rules_text())
    return 0


def cmd_project(args):
    app = qgis_project.init_qgis()
    pairs = [tuple(item.split("=", 1)) for item in args.region_dir]
    bookmarks = []
    for item in args.bookmark or []:
        name, _, where = item.partition("=")
        lon, lat = (float(v) for v in where.split(","))
        bookmarks.append((name, lon, lat))
    names = qgis_project.build_project(pairs, args.out, bookmarks=bookmarks)
    print("wrote", args.out, "with layers:", names)
    app.exitQgis()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tools.sk_data", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, help_ in (("download", cmd_download, "download the OSM extract and WorldCover tiles"),
                              ("build", cmd_build, "build and validate a region"),
                              ("rules", cmd_rules, "list the OSM mappings that are guesses"),
                              ("project", cmd_project, "write a QGIS project to inspect built regions")):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(func=func)
        if name in ("download", "build"):
            p.add_argument("--region", required=True, choices=sorted(REGIONS))
        if name == "download":
            p.add_argument("--no-worldcover", action="store_true")
        if name == "build":
            p.add_argument("--landcover", choices=pipeline.LANDCOVER_MODES, default="osm+worldcover")
            p.add_argument("--out", help="output folder (default <data>/kraje/<region>)")
            p.add_argument("--window", metavar="LON,LAT", help="build only a 12 x 10 km area around this point (needs --out)")
            d = SectorSize()
            p.add_argument("--min-ha", type=float, default=d.min_ha)
            p.add_argument("--target-ha", type=float, default=d.target_ha)
            p.add_argument("--max-ha", type=float, default=d.max_ha)
        if name == "project":
            p.add_argument("--region-dir", action="append", required=True, metavar="LABEL=DIR")
            p.add_argument("--bookmark", action="append", metavar="NAME=LON,LAT",
                           help="add a spatial bookmark; the project opens on the first one (repeatable)")
            p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "build" and args.window:
        if not args.out:
            parser.error("--window needs --out (a window must not overwrite the region folder)")
        args.window = _window(parser, args.window)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the full test suite**

Run: `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -W error::ResourceWarning -m unittest discover -s tests -t . 2>&1 | tail -6; echo "exit: ${PIPESTATUS[0]}"`
Expected: `OK` and `exit: 0` (all earlier tests of the repository plus the new ones). If the process dies with exit code 139 in `test_qgis_project`, QGIS objects were destroyed after `exitQgis()`: the test must delete them first, as written.

Also run: `python3 -m unittest discover -s tests -t . 2>&1 | tail -4`
Expected: OK with the `sk_data` package skipped.

- [ ] **Step 5: Commit**

```bash
git add tools/sk_data/pipeline.py tools/sk_data/qgis_project.py tools/sk_data/__main__.py tests/sk_data/test_pipeline.py tests/sk_data/test_qgis_project.py
git commit -m "Add region pipeline, command line and QGIS inspection project

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation

**Files:**
- Create: `docs/dev/sk-data.md`

- [ ] **Step 1: Write the document** with exactly this content

Create `docs/dev/sk-data.md`:

````markdown
# Slovak data pipeline

`tools/sk_data/` builds the data Patrac reads for a region (sectors with a land-use type, roads, forest
tracks, streams and a municipality list) from open data. It runs with QGIS's bundled Python.

Design: [docs/superpowers/specs/2026-10-18-sk-data-pipeline-design.md](../superpowers/specs/2026-10-18-sk-data-pipeline-design.md).

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

A window has no municipality list and must be written to its own `--out` folder.

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

1. Main roads, railways, rivers/streams/canals and the edges of land-cover polygons are drawn together
   and polygonized into small faces.
2. Each face gets a type: the smallest OSM polygon containing it, else the WorldCover class, else `OTHER`
   (faces with at least 8% buildings become `AREZAS`).
3. Faces smaller than the minimum merge with the neighbour of the same plugin class that shares the
   longest border. Tiny faces (< 1 ha) and thin slivers merge into any neighbour.
4. Areas above the maximum are cut into near-equal parts along their long axis.
5. Fragments smaller than 1 ha (left by the cutting) join the neighbour they share the longest border with.
   That can push a sector slightly above the maximum, by less than 1 ha; validation allows that and
   reports how many sectors are over the maximum.

## Tests

```bash
source tools/dev/qgis_env.sh
QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest discover -s tests -t .
```

Under plain `python3` the `tests/sk_data` package is skipped (it needs the geo libraries bundled with QGIS).
````

- [ ] **Step 2: Check the commands in it match the code**

Run: `source tools/dev/qgis_env.sh && "$QGIS_PY" -m tools.sk_data --help 2>&1 | grep -v "Application path"; "$QGIS_PY" -m tools.sk_data rules 2>&1 | grep -v "Application path" | head -4`
Expected: the four commands `download build rules project` are listed, and the guess list starts with `OSM mappings marked as guesses`.

- [ ] **Step 3: Commit**

```bash
git add docs/dev/sk-data.md
git commit -m "Document the Slovak data pipeline

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Build Košický kraj and hand over for review

This task runs the tool on the real data. A prototype of this exact code already produced both builds and passed validation; `~/patracdata/build/ke-osm-proto` and `~/patracdata/build/ke-proto4` and the project `ke-compare.qgz` from them exist and are what the user is reviewing, so the results of this task should reproduce them. It produces data outside the repository and ends with a manual review by the user; it does not change code unless a run reveals a defect, in which case fix it test-first and commit each fix separately as `Fix <what> in sk_data`.

**Files:**
- Modify (only if a defect is found): files of Tasks 1-8 and their tests.

- [ ] **Step 1: Download the sources**

Run: `source tools/dev/qgis_env.sh && "$QGIS_PY" -m tools.sk_data download --region ke 2>&1 | grep -v "Application path"`
Expected: a JSON list with `osm` (about 346 MB) and `worldcover-N48E018`, `worldcover-N48E021` (about 96 MB and 90 MB). Files that already exist under `~/patracdata/source/` are kept. The download needs no login.

- [ ] **Step 2: Build one window first (quick check)**

Run: `source tools/dev/qgis_env.sh && "$QGIS_PY" -m tools.sk_data build --region ke --window 21.2611,48.7164 --out "$HOME/patracdata/build/ke-kosice-window" 2>&1 | grep -v "Application path\|RuntimeWarning\|return lib"`
Expected: about 1 minute, then a report and `validation passed`. Roughly: `sectors` 1,900-2,300, `region_ha` 12000, `area_ratio` 0.98-1.02, `sectors_under_tiny` 0, `sectors_over_max` 0 or very few, `places` 0, `other_share_of_area` 0.0 (the satellite layer is on by default). If this fails, fix it before the long builds.

- [ ] **Step 3: Build the whole kraj with OSM only and validate**

Run: `source tools/dev/qgis_env.sh && "$QGIS_PY" -m tools.sk_data build --region ke --landcover osm --out "$HOME/patracdata/build/ke-osm" 2>&1 | grep -v "Application path\|RuntimeWarning\|return lib"`
Expected: about 6 minutes, then a report and `validation passed`. In the prototype run: `sectors` 106,419, `area_ratio` 0.9999, `share_in_min_max` 0.80, `sectors_under_tiny` 3, `other_share_of_area` 0.5, `places` 439. Expect values in those neighbourhoods (within a few percent).

- [ ] **Step 4: Build the whole kraj with OSM + WorldCover and validate**

Run: `source tools/dev/qgis_env.sh && "$QGIS_PY" -m tools.sk_data build --region ke --landcover osm+worldcover --out "$HOME/patracdata/build/ke-osm-worldcover" 2>&1 | grep -v "Application path\|RuntimeWarning\|return lib"`
Expected: about 20 minutes and up to 8 GB of memory, then `validation passed`. In the prototype run: `sectors` 109,978, `area_ratio` 0.9999, `share_in_min_max` 0.748, `sectors_over_max` 14, `sectors_under_tiny` 3, `other_share_of_area` 0.0, `places` 439. Expect values in those neighbourhoods (within a few percent).

If a build fails validation, read the problem list, find the cause and fix it test-first; do not loosen a check to make it pass. Run long builds in the background and wait for them; do not poll.

- [ ] **Step 5: Build the comparison project**

Run:
```bash
source tools/dev/qgis_env.sh
B="$HOME/patracdata/build"
"$QGIS_PY" -m tools.sk_data project --out "$B/ke-compare.qgz" \
  --region-dir "OSM only=$B/ke-osm" --region-dir "OSM + WorldCover=$B/ke-osm-worldcover" \
  --bookmark "1 Nálepkovo: OSM gap, satellite says forest=20.621,48.812" \
  --bookmark "2 Slančík: OSM gap, satellite says forest=21.530,48.680" \
  --bookmark "3 Opátka: OSM gap, satellite says forest=21.033,48.773" \
  --bookmark "4 Lastomír: OSM gap, satellite says farmland=21.937,48.691" \
  --bookmark "5 Remetské Hámre: OSM gap, satellite says forest=22.173,48.858" \
  --bookmark "6 Rochovce: OSM gap, forest and meadow=20.305,48.692" \
  --bookmark "7 Košice city: both builds similar=21.2611,48.7164" 2>&1 | grep -v "Application path"
```
Expected: `wrote .../ke-compare.qgz with layers: ['OpenStreetMap', 'Streams (vodtok)', ...]`. The six places are where the prototype's OSM-only build had 2,600-3,600 ha (of 3,600) unclassified while the satellite build said forest or farmland; they need no recomputation.

- [ ] **Step 6: Record the results**

Write a short note `docs/dev/sk-data-results-ke.md` with the two reports (counts, `area_ratio`, `share_in_min_max`, `other_share_of_area`, run time) copied from the command output, and a "Review" section left for the user's verdict. Commit it:

```bash
git add docs/dev/sk-data-results-ke.md
git commit -m "Record Kosicky kraj build results

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Hand over to the user (manual)**

Tell the user: open `~/patracdata/build/ke-compare.qgz` (choose transformation (4) when asked; the project opens zoomed to Košice and shows one sectors layer at a time), compare the two sector layers, decide whether `osm+worldcover` stays the default, and say whether to install the chosen build into `~/patracdata/kraje/ke` with `"$QGIS_PY" -m tools.sk_data build --region ke --landcover <chosen>`. Do not install it into `kraje/ke` before the user decides.

---

## Acceptance for this plan (from the spec)

- [ ] `python -m tools.sk_data build --region ke` runs on the downloaded data and `validate` passes, for both land-cover modes.
- [ ] The user has compared `osm` with `osm+worldcover` in QGIS and decided the default.
- [ ] The full test suite passes under QGIS's Python, and the `sk_data` tests are skipped under plain `python3`.

## Known issues deliberately left for later plans

- The plugin does not read the Slovak municipality list, uses the generic S-JTSK transformation, and still points at Czech basemaps (sub-project 3).
- Nine Czech type codes have no mapping (listed in `docs/dev/sk-data.md`); the OSM rows marked `guess` need the user's review.
- `lespru` is approximated as tracks and paths inside forest sectors.
- The other seven kraje are not built; the code is region-agnostic and the same command builds them.
