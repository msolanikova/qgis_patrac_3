import gzip
import json
import os
import tempfile
import unittest
from unittest import mock

import geopandas as gpd
import shapely
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.wkt import loads as load_wkt

from tools.sk_data import __main__ as cli
from tools.sk_data import service_bundle
from tools.sk_data.crs import OPERATION_NAME, sjtsk_to_wgs84, wgs84_to_sjtsk
from tools.sk_data.export import write_region
from tools.sk_data.rules import load_rules

KOSICE_X, KOSICE_Y = -262580.0, -1240038.0   # tile (-27, -125); the centroid x of the third sector is in tile (-26, -125)
CLASSES = load_rules().classes
SOURCES = [{"name": "osm", "detail": "https://example.org/osm.pbf"}]


def square(cx, cy, side=100.0):
    return box(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)


def sectors_gdf():
    ring_with_hole = Polygon([(-255100, -1244900), (-254900, -1244900), (-254900, -1245100), (-255100, -1245100)],
                             holes=[[(-255050, -1245050), (-254950, -1245050), (-254950, -1244950), (-255050, -1244950)]])
    return gpd.GeoDataFrame(
        {"id": ["1", "2", "3"], "label": ["K1", "K2", "K10"], "typ": ["LPSTROM", "LPSTROM", "OTHER"]},
        geometry=[square(KOSICE_X, KOSICE_Y), square(-262400.0, -1245000.0), ring_with_hole], crs=5514)


def read_tile(version_dir, key, folder="tiles"):
    with gzip.open(os.path.join(version_dir, folder, key + ".jsonl.gz"), "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


class InverseTransformTest(unittest.TestCase):
    def test_inverse_transform_round_trips_kosice_within_a_centimetre(self):
        x, y = wgs84_to_sjtsk().transform(21.2611, 48.7164)
        lon, lat = sjtsk_to_wgs84().transform(x, y)
        self.assertAlmostEqual(lon, 21.2611, delta=1e-7)   # the two directions are the same operation, inverted
        self.assertAlmostEqual(lat, 48.7164, delta=1e-7)
        x2, y2 = wgs84_to_sjtsk().transform(lon, lat)
        # PROJ's inverse Krovak is not the exact inverse: the round trip is off by about 5 mm at Kosice
        self.assertAlmostEqual(x2, x, delta=0.01)
        self.assertAlmostEqual(y2, y, delta=0.01)
        self.assertIn(OPERATION_NAME, sjtsk_to_wgs84().description)
        self.assertIs(sjtsk_to_wgs84(), sjtsk_to_wgs84())   # cached


class WriteBundleTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = tmp.name

    def write(self, gdf=None, **kwargs):
        return service_bundle.write_bundle(sectors_gdf() if gdf is None else gdf, self.out, "ke", "v1", CLASSES,
                                           "Attribution text", SOURCES, **kwargs)

    def test_write_bundle_layout_and_manifest(self):
        manifest = self.write()
        version_dir = os.path.join(self.out, "ke", "v1")
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "ke"))), ["v1"])   # no staging folder left over
        self.assertEqual(sorted(os.listdir(version_dir)), ["manifest.json", "tiles"])
        self.assertEqual(sorted(os.listdir(os.path.join(version_dir, "tiles"))), ["-26_-125.jsonl.gz", "-27_-125.jsonl.gz"])
        with open(os.path.join(version_dir, "manifest.json"), encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk, manifest)
        self.assertEqual(manifest["format"], 1)
        self.assertEqual((manifest["region"], manifest["version"]), ("ke", "v1"))
        self.assertEqual(manifest["crs"], "EPSG:5514")
        self.assertEqual(manifest["tile_m"], 10000)
        self.assertEqual(manifest["sector_count"], 3)
        self.assertEqual(manifest["tiles"], {"-27_-125": 2, "-26_-125": 1})
        self.assertEqual(sum(manifest["tiles"].values()), manifest["sector_count"])
        self.assertEqual(manifest["transform"], "S-JTSK to WGS 84 (4)")
        self.assertEqual(manifest["sources"], SOURCES)
        self.assertEqual(manifest["attribution"], "Attribution text")
        for key, count in manifest["tiles"].items():
            self.assertEqual(len(read_tile(version_dir, key)), count)

    def test_manifest_carries_the_coverage_of_the_sectors(self):
        manifest = self.write()
        self.assertIn("coverage_wkt", manifest)
        coverage = load_wkt(manifest["coverage_wkt"])
        self.assertIn(coverage.geom_type, ("Polygon", "MultiPolygon"))
        self.assertTrue(coverage.is_valid)
        self.assertFalse(coverage.is_empty)
        for geometry in sectors_gdf().geometry:
            self.assertTrue(coverage.contains(geometry.representative_point()))
        self.assertFalse(coverage.intersects(shapely.Point(KOSICE_X + 20000, KOSICE_Y + 20000)))
        self.assertFalse(coverage.intersects(shapely.Point(-258000, -1242000)))   # between the sectors, far from all
        # 0 decimals: every number in the WKT is an integer
        numbers = manifest["coverage_wkt"].replace("(", " ").replace(")", " ").replace(",", " ").split()[1:]
        self.assertTrue(all(n.lstrip("-").isdigit() for n in numbers), manifest["coverage_wkt"][:200])

    def test_tile_lines_carry_class_area_and_a_closed_wgs84_outline(self):
        self.write()
        version_dir = os.path.join(self.out, "ke", "v1")
        first = read_tile(version_dir, "-27_-125")[0]
        self.assertEqual(set(first), {"id", "label", "typ", "cls", "area_ha", "wkt", "outline"})
        self.assertEqual((first["id"], first["label"], first["typ"]), ("1", "K1", "LPSTROM"))
        self.assertEqual(first["cls"], 4)
        self.assertEqual(first["cls"], CLASSES["LPSTROM"])
        self.assertEqual(first["area_ha"], 1.0)
        outline = first["outline"]
        self.assertEqual(outline[0], outline[-1])
        self.assertEqual(len(outline), 5)
        for lon, lat in outline:
            self.assertTrue(48 < lat < 49 and 21 < lon < 22, (lon, lat))
        # the outline is the inverse transform of the exterior ring, rounded to 6 decimals
        xs, ys = zip(*square(KOSICE_X, KOSICE_Y).exterior.coords)
        lons, lats = sjtsk_to_wgs84().transform(list(xs), list(ys))
        for (lon, lat), exp_lon, exp_lat in zip(outline, lons, lats):
            self.assertAlmostEqual(lon, exp_lon, delta=1e-6)
            self.assertAlmostEqual(lat, exp_lat, delta=1e-6)
            self.assertEqual(lon, round(lon, 6))
            self.assertEqual(lat, round(lat, 6))
        geometry = load_wkt(first["wkt"])
        self.assertIsInstance(geometry, Polygon)
        self.assertAlmostEqual(geometry.area, 10000.0, places=1)

    def test_a_polygon_with_a_hole_keeps_the_hole_in_wkt_and_only_the_exterior_in_the_outline(self):
        self.write()
        record = read_tile(os.path.join(self.out, "ke", "v1"), "-26_-125")[0]
        geometry = load_wkt(record["wkt"])
        self.assertEqual(len(geometry.interiors), 1)
        self.assertEqual(record["area_ha"], 3.0)   # 200x200 minus 100x100 m
        self.assertEqual(len(record["outline"]), 5)
        self.assertEqual(record["cls"], CLASSES["OTHER"])

    def test_wkt_is_rounded_to_two_decimals(self):
        gdf = gpd.GeoDataFrame({"id": ["9"], "label": ["X"], "typ": ["LPSTROM"]}, crs=5514,
                               geometry=[box(-262580.123456, -1240038.987654, -262480.123456, -1239938.987654)])
        service_bundle.write_bundle(gdf, self.out, "ke", "round", CLASSES, "a", SOURCES)
        record = read_tile(os.path.join(self.out, "ke", "round"), "-27_-124")[0]
        self.assertIn("-262580.12 -1240038.99", record["wkt"])
        self.assertNotIn("123456", record["wkt"])

    def wkt_of_single_sector(self, geometry):
        gdf = gpd.GeoDataFrame({"id": ["7"], "label": ["X"], "typ": ["OTHER"]}, geometry=[geometry], crs=5514)
        service_bundle.write_bundle(gdf, self.out, "ke", "single", CLASSES, "a", SOURCES)
        (key,) = os.listdir(os.path.join(self.out, "ke", "single", "tiles"))
        return read_tile(os.path.join(self.out, "ke", "single"), key.replace(".jsonl.gz", ""))[0]["wkt"]

    def test_rounding_to_centimetres_keeps_the_polygon_valid(self):
        # valid in the source, but the vertex (99.998, 0.0185) rounds onto the edge: plain rounding gives a self-intersection
        polygon = Polygon([(0, 0), (100, 0), (100, 10), (99.998, 0.0185), (94.103, 10), (0, 10)])
        self.assertFalse(load_wkt(shapely.to_wkt(polygon, rounding_precision=2)).is_valid)
        back = load_wkt(self.wkt_of_single_sector(polygon))
        self.assertIsInstance(back, Polygon)
        self.assertTrue(back.is_valid)
        self.assertAlmostEqual(back.area, polygon.area, delta=0.1)

    def test_a_hairline_notch_that_rounding_would_split_stays_one_polygon_at_a_finer_grid(self):
        polygon = Polygon([(0, 0), (100, 0), (100, 10), (50.006, 0.0049), (50.004, 10)])   # the notch tip is 4.9 mm from the edge
        self.assertTrue(polygon.is_valid)
        back = load_wkt(self.wkt_of_single_sector(polygon))
        self.assertIsInstance(back, Polygon)
        self.assertTrue(back.is_valid)
        self.assertAlmostEqual(back.area, polygon.area, delta=0.01)

    def test_tile_index_floors_negative_coordinates(self):
        gdf = gpd.GeoDataFrame(
            {"id": ["a", "b", "c"], "label": ["A", "B", "C"], "typ": ["OTHER"] * 3}, crs=5514,
            geometry=[square(-0.5, -0.5, 0.5), square(9999.9, 10000.1, 0.1), square(-10000.1, -9999.9, 0.1)])
        manifest = service_bundle.write_bundle(gdf, self.out, "ke", "edge", CLASSES, "a", SOURCES)
        self.assertEqual(manifest["tiles"], {"-1_-1": 1, "0_1": 1, "-2_-1": 1})

    def test_refuses_to_overwrite_and_unknown_typ_raises(self):
        self.write()
        marker = os.path.join(self.out, "ke", "v1", "manifest.json")
        with open(marker, encoding="utf-8") as f:
            before = f.read()
        with self.assertRaises(FileExistsError):
            self.write()
        with open(marker, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "ke"))), ["v1"])

        bad = sectors_gdf()
        bad.loc[1, "typ"] = "NOSUCHTYP"
        with self.assertRaisesRegex(ValueError, "NOSUCHTYP"):
            service_bundle.write_bundle(bad, self.out, "ke", "v2", CLASSES, "a", SOURCES)
        self.assertFalse(os.path.exists(os.path.join(self.out, "ke", "v2")))

    def test_a_geometry_that_is_not_a_single_polygon_raises_naming_the_sector(self):
        gdf = sectors_gdf()
        gdf.loc[1, "geometry"] = MultiPolygon([box(0, 0, 1, 1), box(5, 5, 6, 6)])
        with self.assertRaisesRegex(ValueError, "sector 2 "):
            service_bundle.write_bundle(gdf, self.out, "ke", "v3", CLASSES, "a", SOURCES)
        self.assertFalse(os.path.exists(os.path.join(self.out, "ke", "v3")))

    def test_overwrite_replaces_the_version_and_leaves_no_staging_folder(self):
        self.write()
        two = sectors_gdf().iloc[:2]
        manifest = self.write(gdf=two, overwrite=True)
        self.assertEqual(manifest["sector_count"], 2)
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "ke"))), ["v1"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "ke", "v1", "tiles"))), ["-27_-125.jsonl.gz"])

    def test_a_failing_overwrite_keeps_the_old_version(self):
        self.write()
        bad = sectors_gdf()
        bad.loc[0, "typ"] = "NOSUCHTYP"
        with self.assertRaises(ValueError):
            self.write(gdf=bad, overwrite=True)
        with open(os.path.join(self.out, "ke", "v1", "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["sector_count"], 3)

    def test_wrong_crs_is_refused(self):
        with self.assertRaisesRegex(ValueError, "5514"):
            self.write(gdf=sectors_gdf().set_crs(4326, allow_override=True))


def roads_gdf():
    """Three road pieces: r1 in tile (-27, -125); r2 and r3 in tile (-26, -125). r3 starts in tile -27 (x < -260000)
    but its midpoint is in tile -26; r2 has no name, no tracktype and no surface; r3 has a quote and non-ASCII letters."""
    return gpd.GeoDataFrame(
        {"id": ["r1", "r2", "r3"],
         "name": ["Hlavn\u00e1", None, 'Ulica "Q" \u013dudov\u00edta'],
         "highway": ["residential", "track", "service"],
         "tracktype": [None, None, "grade2"],
         "surface": ["asphalt", None, "gravel"],
         "worse": [False, True, True],
         "length_m": [1500.04, 200.0, 3000.27]},
        geometry=[LineString([(-262580.123, -1240038.456), (-262500.0, -1240100.0), (-262400.0, -1240200.5)]),
                  LineString([(-255000.0, -1245000.0), (-254900.0, -1245000.0)]),
                  LineString([(-261000.0, -1245000.0), (-258000.0, -1245000.0)])], crs=5514)


class RoadTilesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = tmp.name
        self.version_dir = os.path.join(self.out, "ke", "v1")

    def write(self, roads, **kwargs):
        return service_bundle.write_bundle(sectors_gdf(), self.out, "ke", "v1", CLASSES, "Attribution text", SOURCES,
                                           roads=roads, **kwargs)

    def test_without_roads_nothing_changes(self):
        manifest = self.write(None)
        self.assertEqual(set(manifest), {"format", "region", "version", "crs", "tile_m", "sector_count", "tiles",
                                         "transform", "sources", "attribution", "coverage_wkt"})
        self.assertEqual(sorted(os.listdir(self.version_dir)), ["manifest.json", "tiles"])

    def test_road_tiles_and_manifest_entry(self):
        manifest = self.write(roads_gdf())
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "ke"))), ["v1"])   # no staging folder left over
        self.assertEqual(sorted(os.listdir(self.version_dir)), ["manifest.json", "roads", "tiles"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.version_dir, "roads"))),
                         ["-26_-125.jsonl.gz", "-27_-125.jsonl.gz"])
        self.assertEqual(manifest["roads"], {"count": 3, "tiles": {"-27_-125": 1, "-26_-125": 2}})
        for key, count in manifest["roads"]["tiles"].items():
            self.assertEqual(len(read_tile(self.version_dir, key, "roads")), count)
        self.assertEqual([r["id"] for r in read_tile(self.version_dir, "-26_-125", "roads")], ["r2", "r3"])
        with open(os.path.join(self.version_dir, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), manifest)

    def test_a_road_line_has_the_contract_fields(self):
        self.write(roads_gdf())
        first = read_tile(self.version_dir, "-27_-125", "roads")[0]
        self.assertEqual(list(first), ["id", "name", "highway", "tracktype", "surface", "worse", "length_m", "wkt", "outline"])
        self.assertEqual((first["id"], first["name"], first["highway"], first["tracktype"], first["surface"]),
                         ("r1", "Hlavn\u00e1", "residential", None, "asphalt"))
        self.assertIs(first["worse"], False)
        self.assertEqual(first["length_m"], 1500.0)
        line = load_wkt(first["wkt"])
        self.assertIsInstance(line, LineString)
        self.assertEqual(list(line.coords), [(-262580.12, -1240038.46), (-262500.0, -1240100.0), (-262400.0, -1240200.5)])
        for x, y in line.coords:
            self.assertEqual((x, y), (round(x, 2), round(y, 2)))
        outline = first["outline"]
        self.assertEqual(len(outline), len(line.coords))
        self.assertGreaterEqual(len(outline), 2)
        for (lon, lat), (x, y) in zip(outline, line.coords):
            exp_lon, exp_lat = sjtsk_to_wgs84().transform(x, y)
            self.assertEqual((lon, lat), (round(exp_lon, 6), round(exp_lat, 6)))
            self.assertTrue(48 < lat < 49 and 21 < lon < 22, (lon, lat))
        r2, r3 = read_tile(self.version_dir, "-26_-125", "roads")
        self.assertIs(r2["worse"], True)
        self.assertEqual((r2["name"], r2["tracktype"], r2["surface"]), (None, None, None))
        self.assertEqual((r3["name"], r3["tracktype"], r3["length_m"]), ('Ulica "Q" \u013dudov\u00edta', "grade2", 3000.3))
        with gzip.open(os.path.join(self.version_dir, "roads", "-26_-125.jsonl.gz"), "rb") as f:
            raw = f.read()
        self.assertIn("\u013dudov\u00edta".encode("utf-8"), raw)   # not written as an \\u escape

    def test_roads_do_not_touch_the_sector_tiles(self):
        with_roads = self.write(roads_gdf())
        tiles = {key: read_tile(self.version_dir, key) for key in with_roads["tiles"]}
        without = service_bundle.write_bundle(sectors_gdf(), self.out, "ke", "v2", CLASSES, "Attribution text", SOURCES)
        for key in without["tiles"]:
            self.assertEqual(read_tile(os.path.join(self.out, "ke", "v2"), key), tiles[key])
        for key in ("sector_count", "tiles", "coverage_wkt"):
            self.assertEqual(with_roads[key], without[key])
        self.assertEqual(sorted(os.listdir(os.path.join(self.version_dir, "tiles"))),
                         sorted(os.listdir(os.path.join(self.out, "ke", "v2", "tiles"))))

    def test_an_empty_roads_frame_gives_count_zero(self):
        manifest = self.write(roads_gdf().iloc[:0])
        self.assertEqual(manifest["roads"], {"count": 0, "tiles": {}})
        self.assertEqual(sorted(os.listdir(self.version_dir)), ["manifest.json", "tiles"])
        self.assertEqual(manifest["sector_count"], 3)
        with open(os.path.join(self.version_dir, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), manifest)

    def test_roads_info_is_merged_into_the_entry(self):
        manifest = self.write(roads_gdf(), roads_info={"osm_bytes": 5})
        self.assertEqual(manifest["roads"], {"count": 3, "tiles": {"-27_-125": 1, "-26_-125": 2}, "osm_bytes": 5})
        with open(os.path.join(self.version_dir, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["roads"]["osm_bytes"], 5)

    def assert_refused(self, roads, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            self.write(roads)
        self.assertFalse(os.path.exists(self.version_dir))
        self.assertEqual(os.listdir(os.path.join(self.out, "ke")) if os.path.isdir(os.path.join(self.out, "ke")) else [], [])

    def test_an_id_without_the_r_prefix_is_refused(self):
        roads = roads_gdf()
        roads.loc[1, "id"] = "x2"
        self.assert_refused(roads, "x2")

    def test_a_duplicate_id_is_refused(self):
        roads = roads_gdf()
        roads.loc[2, "id"] = "r1"
        self.assert_refused(roads, "r1")

    def test_a_geometry_that_is_not_a_single_line_is_refused(self):
        for bad in (MultiLineString([[(0, 0), (1, 1)], [(5, 5), (6, 6)]]), Point(0, 0), LineString()):
            roads = roads_gdf()
            roads.loc[1, "geometry"] = bad
            with self.subTest(bad=bad.wkt):
                self.assert_refused(roads, "r2 ")

    def test_a_frame_not_in_5514_is_refused(self):
        self.assert_refused(roads_gdf().set_crs(4326, allow_override=True), "5514")

    def test_a_line_that_collapses_at_two_decimals_is_refused(self):
        roads = roads_gdf()
        roads.loc[2, "geometry"] = LineString([(-258000.0, -1245000.0), (-258000.002, -1245000.003)])
        self.assert_refused(roads, "r3 ")

    def test_a_worse_that_is_not_boolean_is_refused(self):
        for bad in ("yes", 1, None):
            roads = roads_gdf().astype({"worse": object})
            roads.loc[0, "worse"] = bad
            with self.subTest(bad=bad):
                self.assert_refused(roads, "r1 ")

    def test_a_failing_overwrite_with_roads_keeps_the_old_version(self):
        self.write(roads_gdf())
        with open(os.path.join(self.version_dir, "manifest.json"), encoding="utf-8") as f:
            before = f.read()
        bad = roads_gdf()
        bad.loc[2, "id"] = "r1"
        with self.assertRaises(ValueError):
            self.write(bad, overwrite=True)
        with open(os.path.join(self.version_dir, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(len(read_tile(self.version_dir, "-26_-125", "roads")), 2)
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "ke"))), ["v1"])


class RegionAndCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        region = os.path.join(self.root, "kraje", "ke")
        meta = {"region": "ke", "sources": {"osm": {"url": "https://example.org/osm.pbf", "bytes": 5, "sha256": None},
                                            "worldcover-N48E021": {"url": "https://example.org/wc.tif"}}}
        write_region(region, sectors_gdf(), {}, meta)

    def run_cli(self, *args):
        with mock.patch.object(cli, "data_root", return_value=self.root), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            return cli.main(["service-bundle", "--region", "ke", *args])

    def test_sources_are_taken_from_metadata_and_the_notice_from_attribution(self):
        manifest = service_bundle.bundle_region(self.root, "ke", "v1", os.path.join(self.root, "out"))
        self.assertEqual(manifest["sources"], [{"name": "osm", "detail": "https://example.org/osm.pbf"},
                                               {"name": "worldcover-N48E021", "detail": "https://example.org/wc.tif"}])
        self.assertIn("OpenStreetMap", manifest["attribution"])
        self.assertEqual(manifest["sector_count"], 3)

    def test_command_writes_to_service_bundles_by_default_and_refuses_an_existing_version(self):
        self.assertEqual(self.run_cli("--version", "v1"), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "service-bundles", "ke", "v1", "manifest.json")))
        self.assertEqual(self.run_cli("--version", "v1"), 2)
        self.assertEqual(self.run_cli("--version", "v1", "--overwrite"), 0)

    def test_command_out_option(self):
        out = os.path.join(self.root, "elsewhere")
        self.assertEqual(self.run_cli("--version", "v9", "--out", out), 0)
        self.assertTrue(os.path.isfile(os.path.join(out, "ke", "v9", "manifest.json")))


if __name__ == "__main__":
    unittest.main()
