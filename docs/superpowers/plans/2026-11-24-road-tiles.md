# Road tiles in the service bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m tools.sk_data service-bundle` also writes the roads and tracks of a region as road pieces (`roads/<tx>_<ty>.jsonl.gz` plus a `roads` entry in the manifest), read straight from the OSM extract, so the SAR Planner can list and plan roads.

**Architecture:** A new module `tools/sk_data/roads.py` turns OSM lines (with tags, in EPSG:5514) into road pieces: select and classify by tags, cut the ways at junctions, chain the stretches between junctions that have the same tags, cut chains longer than 5 km into equal parts, drop tiny stubs, number them with an `r` prefix. `service_bundle.write_bundle` gets an optional `roads` frame and writes the tiles and the manifest entry in the same staging folder as the sector tiles, so a version stays complete-or-absent. `bundle_region` and the CLI read the OSM file for the roads (the built region folder has no `tracktype`, `surface` or `access`). One small change in the other repository (`sar-planner`, `scripts/upload_bundle.py`) lets the uploader accept road tiles. The last task builds the real Kosicky kraj bundle and tests it with the SAR Planner itself.

**Tech Stack:** Python of QGIS (`source tools/dev/qgis_env.sh`, then `$QGIS_PY`), GDAL OSM driver, geopandas, shapely 2, numpy, pandas, unittest (pytest is not installed there).

**Spec:** `/Users/marketasolanikova/Development/sar-planner/docs/superpowers/specs/2026-11-24-s4-roads-design.md` (decisions 1, 2, 4 and the "Constraints" section; this plan is the "fork" part of it). The reader side is already merged in sar-planner main (`src/sar_planner/bundle.py`, `load_roads_near`, `_parse_road`); the road tile contract is repeated below so nobody needs to open that repository except Task 5.

## Global Constraints

Run every test with `source tools/dev/qgis_env.sh && $QGIS_PY -m unittest discover -s tests/sk_data -t .` (one module: `$QGIS_PY -m unittest tests.sk_data.test_roads -v`). The whole suite stays green after every task. Work on a feature branch; never commit to master. Do not touch the working tree while another build of the real data runs (Task 6 reads `~/patracdata`, it does not write into it except the new bundle folder).

**Road tile contract** (the reader in sar-planner enforces it; bundle format stays `"format": 1`, additive):
- Folder `<out>/<region>/<version>/roads/`, file `<tx>_<ty>.jsonl.gz`, gzip, UTF-8, one JSON object per line, `ensure_ascii=False`. Tile of a piece = the 10 km S-JTSK tile (`TILE_M = 10000`, `floor(x / TILE_M)`, same as sectors) of the **midpoint** of its line (`line_interpolate_point(0.5, normalized=True)`).
- Fields of a line: `id` (string, non-empty, starts with `r`, unique in the whole bundle), `name` (string or `null`), `highway` (string), `tracktype` (string or `null`), `surface` (string or `null`), `worse` (JSON boolean), `length_m` (number, finite, >= 0, one decimal), `wkt` (a single non-empty LINESTRING in EPSG:5514, 2 decimals), `outline` (list of `[lon, lat]` in WGS84, 6 decimals, the same vertices as the line, at least 2 points).
- Manifest: `"roads": {"count": N, "tiles": {"<tx>_<ty>": n, ...}}` where the tile counts equal the number of lines in each tile file and sum to `count`; extra keys are allowed and ignored by the reader. A bundle built without roads has **no** `roads` key and no `roads/` folder.
- Road tiles ship only in a **new bundle version**, never into an existing one (a case stores its bundle version; a re-plan of a case made before roads would find road rows and get a conflict). `write_bundle` already refuses an existing version unless `overwrite` is true; the CLI help must say not to overwrite a version cases were made on.

**Road piece rules** (the owner's and my calls from the spec; every number is a guess the owner may change, so each is one named constant in `tools/sk_data/roads.py`):
- Included `highway` values (`INCLUDED_HIGHWAYS`): track, path, bridleway, service, unclassified, residential, living_street, tertiary, cycleway, footway. Never included: motorway, trunk, primary, secondary, their `_link`s, steps, anything else.
- Excluded by tags even when the highway value is included (my calls, to keep sidewalks and driveways out of the list): `tunnel` in `layers.TUNNEL_VALUES` (reuse `layers._is_tunnel`); `footway` in {sidewalk, crossing}; `service` in {parking_aisle, driveway, drive-through, emergency_access}; `access` in {no, private}.
- `worse` (decision 2): `highway` in track, path, bridleway, **or** `surface` (split on `;`, any part) in `UNPAVED_SURFACES` = {unpaved, compacted, fine_gravel, gravel, pebblestone, dirt, earth, ground, grass, mud, sand, woodchips, clay, rock, ice, snow, salt}. A track of any `tracktype` is worse.
- `MAX_PIECE_M = 5000.0`: a chain longer than this is cut into `ceil(length / MAX_PIECE_M)` parts of equal length; a chain of exactly 5000 m stays whole. `MIN_PIECE_M = 30.0`: pieces shorter than this are dropped (junction stubs, connectors); 30 m is kept.
- Junctions are shared vertices: an OSM node shared by two different ways is a junction (identical lon/lat gives identical projected coordinates). Ways that cross without a shared node (a bridge, an overpass) are neither cut nor joined there.
- Chaining: stretches that meet at a point where exactly two stretches end are joined when they have the same `(highway, name, tracktype, surface, worse)`.
- Name shown is `name`, else `ref`, else `null`. `tracktype` and `surface` are copied from the OSM tags as they are (strings or `null`).
- A piece belongs to the region when its midpoint lies within the region polygon (EPSG:5514); pieces are not clipped.
- Ids: after sorting pieces by (rounded midpoint x, rounded midpoint y, length_m), `r1`, `r2`, ... in that order, and each piece's line is oriented so that its first vertex is not after its last in (x, y) order. The result must not depend on the order or direction of the input lines.
- CRS: S-JTSK EPSG:5514 for geometry (`tools.sk_data.crs`), WGS84 outlines through `sjtsk_to_wgs84()`; the pinned transformation is not to be replaced.

## Review Focus

Most likely first; each has a test in the task named in brackets.
1. Two ways that cross without a shared node (an overpass) must stay whole and unjoined; a junction in the middle of a way must cut it. [Task 2]
2. A closed way (a ring track, a roundabout) gives a ring piece with at least 2 points and no crash; a 12 km ring is cut like any other line. [Task 2]
3. A region with no roads at all: no `roads` key, no folder when roads were not asked for; an empty roads frame gives `count: 0`, and neither breaks the sector tiles. [Task 3]
4. The same input in a different row order or line direction gives the same ids and geometries (gzip headers may differ, content may not). [Task 2]
5. Tags the OSM data really has: `surface=asphalt;gravel`, `name` with quotes or non-ASCII characters, a way with only `highway`, `tracktype` without `surface`, duplicate consecutive vertices, a zero-length way. [Tasks 1, 2, 4]

---

### Task 1: Classify OSM ways (`classify`, `display_name`)

**Files:**
- Create: `tools/sk_data/roads.py`
- Create: `tests/sk_data/test_roads.py`
- Modify: `.gitignore` (add the line `.superpowers/`, the ledger workspace of the subagent workflow)

**Interfaces:**
- Consumes: `tools.sk_data.layers._is_tunnel(tags) -> bool`.
- Produces in `tools/sk_data/roads.py`: constants `INCLUDED_HIGHWAYS: frozenset[str]`, `WORSE_HIGHWAYS: frozenset[str]` (= track, path, bridleway), `UNPAVED_SURFACES: frozenset[str]`, `MAX_PIECE_M = 5000.0`, `MIN_PIECE_M = 30.0`; `classify(tags: dict) -> bool | None` (None = not a road piece; otherwise the `worse` flag); `display_name(tags: dict) -> str | None`.

- [ ] **Step 1: Write the failing tests** in `tests/sk_data/test_roads.py`, class `ClassifyTest` (`unittest.TestCase`), with a small helper that builds a tag dict. Assertions, table-driven with `subTest`:
  - `classify({"highway": h})` is `False` for residential, unclassified, tertiary, service, living_street, cycleway, footway; `True` for track, path, bridleway.
  - `classify` is `None` for motorway, trunk, primary, secondary, tertiary_link, secondary_link, steps, construction, `{}` (no highway), and for `{"waterway": "stream"}`.
  - `{"highway": "residential", "surface": "gravel"}` is `True`; `"asphalt"` is `False`; `"asphalt;gravel"` is `True`; `"asphalt;paved"` is `False`; `{"highway": "track", "surface": "asphalt", "tracktype": "grade1"}` is `True`.
  - Excluded: `{"highway": "residential", "tunnel": "yes"}`, `"culvert"`; `{"highway": "footway", "footway": "sidewalk"}`, `"crossing"`; `{"highway": "service", "service": "driveway"}`, `"parking_aisle"`; `{"highway": "track", "access": "private"}`, `"no"` are `None`; `{"highway": "track", "access": "yes"}`, `{"highway": "service", "service": "alley"}`, `{"highway": "footway", "footway": "path"}` are kept.
  - `display_name({"name": "Hlavná", "ref": "III/3345"})` is `"Hlavná"`; with only `ref` it is `"III/3345"`; with neither it is `None`; an empty `name` string counts as missing.

- [ ] **Step 2: Run the tests** (`$QGIS_PY -m unittest tests.sk_data.test_roads -v`); expected: they fail with an ImportError of `tools.sk_data.roads`.

- [ ] **Step 3: Implement** `classify` and `display_name` in `tools/sk_data/roads.py` with the constants from the Global Constraints (module docstring in the style of the other modules: what the module does, in plain words). Split `surface` on `;` and strip blanks.

- [ ] **Step 4: Run the whole suite**; expected: all green.

- [ ] **Step 5: Commit** (`git add .gitignore tools/sk_data/roads.py tests/sk_data/test_roads.py`; message "Classify OSM ways as road pieces and as worse or good").

### Task 2: Road pieces from lines (`road_pieces`)

**Files:**
- Modify: `tools/sk_data/roads.py`
- Modify: `tests/sk_data/test_roads.py`

**Interfaces:**
- Consumes: `classify`, `display_name`, constants from Task 1; a GeoDataFrame like `extract.read_lines` gives after `crs.to_sjtsk`: EPSG:5514 `LineString` or `MultiLineString` geometries and a `tags` column of dicts.
- Produces: `road_pieces(lines: GeoDataFrame, region) -> GeoDataFrame`, where `region` is a shapely (Multi)Polygon in EPSG:5514. The result is in EPSG:5514 with columns `id`, `name`, `highway`, `tracktype`, `surface`, `worse` (bool), `length_m` (float, rounded to 1 decimal), `geometry` (LineString), sorted as in the Global Constraints, `id` = `"r1"`, `"r2"`, ...; an empty input or no piece gives an empty frame with the same columns and CRS.

- [ ] **Step 1: Write the failing tests**, class `RoadPiecesTest`, with a helper `lines_gdf(*rows)` taking `(tags, [(x, y), ...])` in metres relative to a base point near Kosice (-262000, -1245000) and a `REGION = box(...)` that contains all test lines. Tests and assertions:
  - `test_a_junction_in_the_middle_of_a_way_cuts_it`: way A `(0,0) (1000,0) (2000,0)`, way B `(1000,0) (1000,1500)`, all `{"highway": "track"}`; three pieces with `length_m` 1000.0, 1000.0 and 1500.0; each carries `worse` True.
  - `test_two_stretches_with_the_same_tags_are_chained_through_a_plain_node`: A `(0,0)-(1000,0)`, B `(1000,0)-(2000,0)`, both `{"highway": "residential", "name": "Hlavná"}`: one piece of 2000.0 m; with `surface` `gravel` on B only, two pieces; with a different `name` on B, two pieces.
  - `test_ways_that_cross_without_a_shared_node_are_not_cut_or_joined`: A `(0,0)-(2000,0)`, B `(1000,-500)-(1000,500)`: two pieces, 2000.0 and 1000.0.
  - `test_a_chain_longer_than_five_km_is_cut_into_equal_parts`: one straight way of 12000 m gives three pieces of 4000.0 m that touch end to end; 5000 m gives one piece; 5001 m gives two of 2500.5 m.
  - `test_pieces_shorter_than_thirty_metres_are_dropped`: a lone 29.9 m way is dropped, a 30.0 m way is kept; a 10 m connector between two long ways at a three-way junction is dropped and the long ways are still returned.
  - `test_a_closed_way_gives_a_ring_piece`: a 500 m square ring (2000 m) gives one piece whose geometry has at least 2 distinct points and equal first and last coordinate; a 12 km ring gives three pieces and no exception.
  - `test_a_zero_length_way_and_duplicate_vertices_do_no_harm`: a way `(0,0) (0,0)` is dropped; `(0,0) (0,0) (1000,0)` gives one piece of 1000.0 m.
  - `test_excluded_ways_give_no_pieces_and_tags_are_copied`: a motorway, a tunnel, a sidewalk and a private track among normal lines give none of their own; a track with `tracktype` `grade3`, `surface` `ground`, `name` None gives `tracktype == "grade3"`, `surface == "ground"`, `name is None`, `highway == "track"`; a `residential` way with `surface=asphalt;gravel` has `worse` True and `surface == "asphalt;gravel"`; a way with only `{"highway": "path"}` has `tracktype` and `surface` None.
  - `test_pieces_belong_to_the_region_by_their_midpoint`: a region box covering x up to 1500; a way `(1000,0)-(1900,0)` has its midpoint at 1450 and stays whole (length 900.0); a way `(1400,100)-(2400,100)` has its midpoint at 1900 and is dropped.
  - `test_a_multilinestring_is_handled_like_its_parts` (two parts that touch at a junction cut like two ways).
  - `test_ids_are_r_numbers_in_midpoint_order_and_do_not_depend_on_input_order`: five lines; ids are `r1`..`r5`, unique; the frame built from the reversed rows with every line reversed in direction is equal (`geometry` compared with `equals_exact` to 1 mm, other columns equal); each piece's first vertex is not after its last in (x, y) order; `length_m` equals `round(geometry.length, 1)`.
  - `test_an_empty_input_gives_an_empty_frame_with_the_columns`.

- [ ] **Step 2: Run them**; expected: AttributeError or ImportError for `road_pieces`.

- [ ] **Step 3: Implement `road_pieces(lines, region)`** in `tools/sk_data/roads.py`. Approach: (a) explode multi-lines, keep rows with `classify(tags) is not None`, drop lines with fewer than 2 distinct points; (b) junction detection with numpy/pandas over all vertices (one row per vertex with its way index; coordinates rounded to 3 decimals; a vertex is a junction when it occurs in at least two different ways) and cut every way at its junction vertices and ends; (c) group the resulting stretches: build node degrees (count of stretch ends per point) and join stretches with `shapely.line_merge` per group of stretches linked through degree-2 points with equal `(highway, name, tracktype, surface, worse)` (union-find over the stretches; if `line_merge` returns more than one line for a group, keep each part as its own piece); (d) cut chains longer than `MAX_PIECE_M` with `shapely.ops.substring` into equal parts; (e) drop pieces shorter than `MIN_PIECE_M` and pieces whose midpoint is not within `region` (use `shapely.prepare(region)`); (f) orient, sort, number. The loops must stay vectorised or linear in the number of stretches: the real region has some hundred thousand stretches and the whole function must run in well under a few minutes (Task 6 measures it).

- [ ] **Step 4: Run the whole suite**; expected: green.

- [ ] **Step 5: Commit** ("Cut OSM roads and tracks into road pieces").

### Task 3: Write road tiles and the manifest entry (`write_bundle(roads=)`)

**Files:**
- Modify: `tools/sk_data/service_bundle.py`
- Modify: `tests/sk_data/test_service_bundle.py`

**Interfaces:**
- Consumes: the frame `road_pieces` returns (columns `id`, `name`, `highway`, `tracktype`, `surface`, `worse`, `length_m`, `geometry`, EPSG:5514); `service_bundle._tile_groups`-like tile logic; `_outlines`-like transformation (the existing `_outlines` takes polygon exteriors; add a line variant, do not change it).
- Produces: `write_bundle(sectors, out_dir, region, version, classes, attribution, sources, overwrite=False, roads=None)` where `roads` is `None` (no roads, bundle exactly as before) or a frame as above (possibly empty). With a frame, the staging folder gets `roads/<tx>_<ty>.jsonl.gz` for every non-empty tile and the manifest gets `"roads": {"count": N, "tiles": {...}}` (tile keys sorted like the sector tiles). Extra keys in the `roads` entry may be passed as `roads_info: dict | None = None` and are merged into it (used in Task 4 for `osm_bytes` and the two limits). All checks run before anything is written.

- [ ] **Step 1: Write the failing tests** in a new class `RoadTilesTest` in `tests/sk_data/test_service_bundle.py` with a helper `roads_gdf()` (three pieces, ids `r1`..`r3`, one `worse`, one with `name` None, one with a name containing a quote and a non-ASCII character, midpoints in two different tiles including one with negative tile indices, plus one line that starts in one tile and has its midpoint in the next):
  - `test_without_roads_nothing_changes`: `write_bundle(..., roads=None)` has no `roads` key in the manifest and no `roads` folder; the manifest keys equal exactly the keys the existing test already expects.
  - `test_road_tiles_and_manifest_entry`: folder `roads` holds one file per tile the pieces fall into (named with floor of the midpoint, negative numbers kept); the manifest `roads` equals `{"count": 3, "tiles": {...}}` and each tile count equals the lines in its file; the manifest on disk equals the returned manifest; no staging folder is left over.
  - `test_a_road_line_has_the_contract_fields`: read one tile with the existing `read_tile`-style helper (give it a folder argument); keys are exactly `id, name, highway, tracktype, surface, worse, length_m, wkt, outline`; `worse` is a JSON boolean (`is True` / `is False`), `name`, `tracktype` and `surface` may be `None`; `wkt` loads as a shapely `LineString` whose coordinates have at most 2 decimals; `outline` has as many points as the line, each `[lon, lat]` equals `sjtsk_to_wgs84().transform(x, y)` rounded to 6 decimals, and its length is at least 2; the non-ASCII name is written unescaped (check the raw bytes after gunzip contain the UTF-8 character).
  - `test_roads_do_not_touch_the_sector_tiles`: sector tiles and `sector_count`, `tiles` and `coverage_wkt` are identical with and without roads.
  - `test_an_empty_roads_frame_gives_count_zero`: manifest `roads == {"count": 0, "tiles": {}}`, no `roads` folder, and the bundle is otherwise complete.
  - `test_roads_info_is_merged_into_the_entry`: `roads_info={"osm_bytes": 5}` appears next to `count` and `tiles`.
  - Refusals, each raising `ValueError` before anything is written (version folder absent afterwards) and naming the road id: an id without the `r` prefix; a duplicate id; a geometry that is not a single non-empty `LineString`; a frame not in EPSG:5514; a line that rounds to fewer than 2 distinct points at 2 decimals; a `worse` that is not boolean.
  - `test_a_failing_overwrite_with_roads_keeps_the_old_version` (copy the pattern of the existing atomicity test with roads in the new data).

- [ ] **Step 2: Run them**; expected: TypeError for the unknown `roads` argument.

- [ ] **Step 3: Implement** in `service_bundle.py`: the module docstring gets the road tile format (same plain style as the sector part); a `_check_roads(roads)` that raises as listed; `_write_road_tiles(folder, roads)` writing one gzip file per tile; the line coordinates are snapped to 2 decimals with `shapely.set_precision(geom, 0.01)` (fall back to the original coordinates rounded if that changes the type, then raise if still not a valid LineString of at least 2 distinct points) and `wkt` written with `rounding_precision=2`; `outline` from the snapped coordinates with 6 decimals; the entry in the manifest; the roads folder is created only when there is at least one piece. Do not change the behaviour of the sector code.

- [ ] **Step 4: Run the whole suite**; expected: green (the old service-bundle tests unchanged).

- [ ] **Step 5: Commit** ("Write road tiles and the roads entry of the manifest").

### Task 4: Roads from the OSM file: extraction, `bundle_region`, CLI, docs

**Files:**
- Modify: `tools/sk_data/extract.py`, `tools/sk_data/roads.py`, `tools/sk_data/service_bundle.py`, `tools/sk_data/__main__.py`
- Modify: `tests/sk_data/osm_fixture.py` (a second fixture, do not change `OSM_XML`), `tests/sk_data/test_roads.py`, `tests/sk_data/test_service_bundle.py`, `tests/sk_data/test_extract.py` only if its layout needs it
- Modify: `docs/dev/sk-data.md` (the section of `service-bundle`: roads, `--no-roads`, `--osm`, the new-version rule, the list of guesses)

**Interfaces:**
- Consumes: `extract.region_boundary`, `extract.bbox_of`, `extract.read_lines`, `crs.to_sjtsk`, `crs.project_geometries`, `pipeline._region_boundary(pbf, name, work) -> (boundary, region_wgs, region_sjtsk, bbox)`, `pipeline.default_osm_path(root)`, `road_pieces` (Task 2), `write_bundle(roads=, roads_info=)` (Task 3).
- Produces:
  - `extract.extract_roads(pbf, bbox, out_dir) -> str`: GeoPackage path of the `lines` layer cut to `bbox`, with an OGR `where` that keeps only `highway IN (<INCLUDED_HIGHWAYS>)`.
  - `roads.region_roads(pbf: str, region_name: str, work_dir: str) -> GeoDataFrame`: the road pieces of the administrative area named `region_name` (the Task 2 frame); `work_dir` must exist and is only used for temporary GeoPackages.
  - `service_bundle.bundle_region(root, region, version, out_dir, overwrite=False, roads=False, osm_pbf=None, region_name=None)`; with `roads=True` it builds the pieces from `osm_pbf` (default `pipeline.default_osm_path(root)`) and the area named `region_name` (default `config.REGIONS[region]`) in its own temporary folder under `<root>/work` (removed afterwards, as `pipeline` does), passes `roads_info={"osm_bytes": <size of the pbf>, "max_piece_m": ..., "min_piece_m": ...}`, and logs a warning when the pbf size differs from `sources.osm.bytes` in the region's `metadata.json` (the roads then come from another OSM snapshot than the sectors). A missing pbf raises `FileNotFoundError` naming the path.
  - CLI `service-bundle`: roads are on by default; `--no-roads` turns them off; `--osm PATH` overrides the pbf; a missing pbf prints `error: ...` and returns 2; the summary line also prints the number of road pieces and tiles; the `--overwrite` help says it must not be used on a version that cases were made on once roads are involved.

- [ ] **Step 1: Write the failing tests.** In `tests/sk_data/osm_fixture.py` add `ROADS_OSM_XML` and `write_roads_fixture(path)`: a hand-written area near Kosice (same style as `OSM_XML`) with an administrative level-4 relation named `"Road kraj"` around about 4 x 3 km and these ways: a `track` (`tracktype=grade2`, no surface, no name) that ends at a junction node on a `residential` street `name="Hlavná \"stará\""`, so the street is cut in two there; an `unclassified` way with `surface=gravel` that continues the street through a plain node (different tags, so not chained); a `motorway`; a `residential` way with `tunnel=yes`; a `footway` with `footway=sidewalk`; a `service` with `service=driveway`; a `track` with `access=private`; a `path` crossing the street on a separate node (no junction); a `track` entirely outside the relation (its midpoint outside); a closed `track` ring. Then tests:
  - `test_extract_roads_keeps_only_included_highways` (in `test_extract.py` or `test_roads.py`): the GeoPackage lines have `highway` values only from `INCLUDED_HIGHWAYS`; the motorway is absent.
  - `test_region_roads_on_the_fixture`: `roads.region_roads(pbf, "Road kraj", work)` returns exactly the expected pieces: count, the `worse` flags (track, path, gravel unclassified True; the street False), `tracktype == "grade2"` on the track, the street name with its quotes intact, none of the excluded ways, the outside track absent, the ring present, ids `r1..rN`.
  - `test_bundle_region_with_roads`: `bundle_region(root, "ke", "v1", out, roads=True, osm_pbf=fixture, region_name="Road kraj")` (the region folder is made as `RegionAndCommandTest.setUp` does) gives a manifest `roads.count` equal to the number of lines in all road tiles, `osm_bytes` equal to the fixture file size, and the sector tiles unchanged; without `roads=True` there is no `roads` key.
  - `test_a_missing_pbf_raises_and_writes_nothing` (`FileNotFoundError`, no version folder); `test_a_different_osm_size_logs_a_warning` (`assertLogs("sk_data", "WARNING")` when `metadata.json` says another byte count).
  - CLI: `test_command_writes_roads_by_default` (patch `data_root` and `pipeline.default_osm_path` or pass `--osm`), `test_command_no_roads`, `test_command_missing_osm_returns_2`. The existing CLI tests keep passing unchanged except that they must pass `--no-roads` (their fake root has no OSM file); say so in the commit message.

- [ ] **Step 2: Run them**; expected: failures for the missing functions and options.

- [ ] **Step 3: Implement** the interfaces. In `extract_roads` use the same `_translate` helper (add `where` through its existing keyword arguments). `region_roads`: boundary and bbox through `pipeline._region_boundary` (import it lazily inside the function to avoid an import cycle if there is one), read the lines with `extract.read_lines`, project with `crs.to_sjtsk`, call `road_pieces(lines, region)`. Log one info line with the counts, as `pipeline` does.

- [ ] **Step 4: Run the whole suite**; expected: green.

- [ ] **Step 5: Update `docs/dev/sk-data.md`** (what the command writes now, the three guesses lists: included highways, unpaved surfaces, the two lengths, the exclusion tags; the new-version rule; how to run it) and commit ("Build the road tiles of a bundle from the OSM file").

### Task 5: sar-planner: the uploader accepts road tiles

This task runs in the other repository: working tree `~/Development/sar-planner`, new branch `feature/upload-road-tiles` from main (never commit to main); tests with `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t .`.

**Files:**
- Modify: `scripts/upload_bundle.py`, `tests/test_upload_bundle.py`, `README.md` (the paragraph "The road tiles are written by the fork's `service-bundle` command; that part is still to do, so the current bundle has none." now says the command writes them, and the version rule), `docs/superpowers/specs/2026-11-24-s4-roads-design.md` (the status line: the fork part is implemented on branch `feature/road-tiles-plan` of the fork once Task 6 is done; leave the wording to the builder, one line)

**Interfaces:**
- Consumes: `_read_manifest`, `_TILE`, `plan_upload` as they are today; the manifest `roads` entry from the contract above.
- Produces: `plan_upload(source_dir, bundle_region, version)` returns `[(local path, key)]` with the sector tiles sorted, then the road tiles (`roads/<name>.jsonl.gz` for each key of `manifest["roads"]["tiles"]`) sorted, then `manifest.json` last. A folder with a file that neither list names is still refused ("files ... that the manifest does not list"); a road tile named in the manifest but missing is refused naming it; a malformed `roads` entry (not an object, `tiles` not an object, a tile name not matching `_TILE`) raises `ValueError`; a manifest without `roads` and a folder with `roads/` files is refused as before.

- [ ] **Step 1: Write the failing tests** in `tests/test_upload_bundle.py` (use its existing helper that builds a bundle folder; extend it with an optional roads argument): the plan of a bundle with two sector tiles and two road tiles has the keys in the order sector tiles, road tiles, manifest, all under `<region>/<version>/`; a missing listed road tile raises ValueError naming `roads/<name>.jsonl.gz`; an unlisted road file raises; a manifest without `roads` but with a `roads/` folder raises; `"roads": []` raises; a road tile name `"../x"` raises; `run_upload` verifies the key count including road tiles (use the existing fake S3 client).

- [ ] **Step 2: Run them**; expected: failures for road tiles being reported as extra files.

- [ ] **Step 3: Implement** the change; update the module docstring ("the tiles, then the road tiles, manifest.json last") and the dry-run output stays as is.

- [ ] **Step 4: Run the whole Python suite** of sar-planner; expected: green (1069 plus the new tests).

- [ ] **Step 5: Commit** on the branch ("Upload road tiles with the bundle"); do not merge or push (the owner decides).

### Task 6: Build the real Kosicky kraj bundle with roads and test it with the SAR Planner

Runs in the fork after Tasks 1 to 4 (and in sar-planner for the checks). No new code is expected; any fix found here goes back through the usual test-first steps in the task that owns it. Nothing is uploaded or deployed in this task.

**Files:**
- Create (outside git): `~/patracdata/service-bundles/ke/<VERSION>/` with `VERSION` = `2026-11-24-roads` (any name not yet used in `~/patracdata/service-bundles/ke/` and in the bundle bucket; the existing `2026-11-22` and `2026-11-24` stay untouched)
- Create: `.superpowers/sdd/2026-11-24-road-tiles/task-6-report.md` (git-ignored workspace; the numbers below)

- [ ] **Step 1: Build.** `source tools/dev/qgis_env.sh && time $QGIS_PY -m tools.sk_data service-bundle --region ke --version 2026-11-24-roads`. Expected: exit 0, a summary line with the sector count (110118 as in `2026-11-24`) and the number of road pieces and tiles. Note the run time and peak memory (`/usr/bin/time -l`). Check that the sector tiles of the new version equal those of `2026-11-24` line by line (same ids, same `wkt`) and the manifest differs only by the `roads` entry, `version` and the order of the keys.

- [ ] **Step 2: Numbers for the report:** pieces in total, kilometres in total, pieces and kilometres by `highway` and by `worse`, the biggest tile (pieces, file size), the longest piece, the shortest, the count of pieces without a name, the total size of `roads/`. Look at the largest and smallest values for sense (no piece over 5000.0 m plus rounding, none under 30.0 m).

- [ ] **Step 3: Read it back with the real reader.** With sar-planner's `.venv` and `PYTHONPATH=src`, call `sar_planner.bundle.load_manifest` and `load_roads_near` for every listed road tile centre (radius 1 m is enough to read a tile; use the Kosice point -262580, -1240038 with radius 10000 too): no exception, tile counts match the manifest, ids unique, every id starts with `r` and none equals a sector id of the sector tiles (read all sector ids once into a set).

- [ ] **Step 4: Run the Kosice test case with roads.** Use the test case files in `~/Development/sar-planner/test-data` and the command line in the sar-planner README (`sar_planner.cli`), pointing at the new bundle: record the number of roads found, the time of the case, then a plan with units like the field test (for example 4 ground, 1 dog team, 1 drone, 2 ATV) and one without ATVs; record time, roads assigned and uncovered, ATV hours, and check by eye that worse roads go to the ATV and good ones to ground teams. If a case takes longer than 10 s or lists more than 5000 roads, write down which and stop: the options are the include list in `roads.py` (drop `residential` and `service` in built-up areas) or `case.MAX_ROADS`; the owner decides.

- [ ] **Step 5: Visual check.** Write the combined GPX of that case and one road file to `.superpowers/sdd/2026-11-24-road-tiles/` for the owner to open in CalTopo or Locus (the owner does the opening); report the paths.

- [ ] **Step 6: Report** in `task-6-report.md`: all numbers, timings, anything surprising, and the upload and deploy commands for the owner's go-ahead, not executed: `python scripts/upload_bundle.py --bundle-region ke --version 2026-11-24-roads --dry-run`, then without `--dry-run` (after Task 5 is merged), then the deploy with `-c bundle_version=2026-11-24-roads` (without `--skip-lambda` only if the Lambda code changed since the last deploy; the S4 code is not deployed yet, so it did).

## After the plan (owner's decisions, not tasks)

Merge the fork branch to master and push; merge `feature/upload-road-tiles` in sar-planner; upload the bundle; deploy sar-planner (S4 code and `bundle_version`); live smoke test with roads; the owner's check of the road GPX in CalTopo and Locus and of the lists on the phone.
