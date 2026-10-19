import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from tests.sk_data.osm_fixture import write_fixture
from tests.sk_data.test_landcover import write_raster
from tools.sk_data import pipeline
from tools.sk_data.__main__ import main
from tools.sk_data.config import REGIONS, SectorSize, region_dir
from tools.sk_data.crs import wgs84_to_sjtsk
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

    def test_sectors_shapefile_has_string_id_and_label(self):
        import re
        import geopandas as gpd
        from osgeo import ogr
        problems, report, out_dir = self.build(landcover_mode="osm")
        self.assertEqual(problems, [])
        path = os.path.join(out_dir, "vektor", "ZABAGED", "sectors.shp")
        dataset = ogr.Open(path)
        definition = dataset.GetLayer(0).GetLayerDefn()
        types = {definition.GetFieldDefn(i).GetName(): definition.GetFieldDefn(i).GetType() for i in range(definition.GetFieldCount())}
        definition = dataset = None
        self.assertEqual(types["id"], ogr.OFTString)
        self.assertEqual(types["label"], ogr.OFTString)
        sectors = gpd.read_file(path)
        n = len(sectors)
        self.assertEqual(sorted(int(i) for i in sectors["id"]), list(range(1, n + 1)))
        self.assertTrue(all(isinstance(i, str) and re.match(r"^[1-9][0-9]*$", i) for i in sectors["id"]))
        self.assertTrue(all(isinstance(l, str) and re.match(r"^[A-Z][0-9]+$", l) for l in sectors["label"]))
        self.assertEqual(report["id_max"], n)
        self.assertEqual(report["labels"]["duplicated_labels"], 0)         # the fixture is far smaller than one grid cell group
        self.assertLessEqual(report["labels"]["max_length"], 4)

    def test_worldcover_fills_the_gaps(self):
        tif = os.path.join(self.root, "wc.tif")
        write_raster(tif, np.full((700, 700), 40, dtype=np.uint8), origin=(21.17, 48.75))  # cropland everywhere, 0.07 deg square
        problems, report, _ = self.build(landcover_mode="osm+worldcover", worldcover_paths=[tif])
        self.assertEqual(problems, [])
        self.assertEqual(set(report["count_by_typ"]), {"LPSTROM", "ORNAPU"})
        self.assertEqual(report["other_share_of_area"], 0.0)

    def test_window_builds_a_12_by_10_km_area_around_a_point(self):
        problems, report, out_dir = self.build(landcover_mode="osm", window=(21.205, 48.705),
                                                  out_dir=os.path.join(self.root, "window"))
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


class OutputFolderProtectionTest(unittest.TestCase):
    """build_region never writes into an existing region folder until the new data has validated."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.osm = write_fixture(os.path.join(self.root, "mini.osm"))
        self.parent = os.path.join(self.root, "out")
        self.out = os.path.join(self.parent, "ke")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, **kwargs):
        kwargs.setdefault("area_tolerance", 0.15)    # tiny region: whole sectors at the border weigh a lot
        kwargs.setdefault("landcover_mode", "osm")
        kwargs.setdefault("out_dir", self.out)
        return pipeline.build_region("ke", self.root, osm_pbf=self.osm, region_name="Test kraj", **kwargs)

    def make_old_folder(self):
        os.makedirs(self.out)
        marker = os.path.join(self.out, "marker.txt")
        with open(marker, "w") as f:
            f.write("old")
        return marker

    def siblings(self):
        return sorted(os.listdir(self.parent)) if os.path.isdir(self.parent) else []

    def test_window_without_out_dir_is_refused_before_anything_is_created(self):
        with self.assertRaises(ValueError) as ctx:
            self.build(window=(21.205, 48.705), out_dir=None)
        self.assertIn("out_dir", str(ctx.exception))
        self.assertEqual(os.listdir(self.root), ["mini.osm"])

    def test_non_empty_folder_is_refused_without_overwrite(self):
        marker = self.make_old_folder()
        with self.assertRaises(FileExistsError) as ctx:
            self.build()
        self.assertIn(self.out, str(ctx.exception))
        self.assertIn("--overwrite", str(ctx.exception))
        self.assertEqual(os.listdir(self.out), ["marker.txt"])
        with open(marker) as f:
            self.assertEqual(f.read(), "old")
        self.assertFalse(os.path.exists(os.path.join(self.root, "work")))     # refused before any work started
        self.assertEqual(self.siblings(), ["ke"])

    def test_default_folder_is_protected_too(self):
        default = os.path.join(self.root, "kraje", "ke")
        os.makedirs(default)
        with open(os.path.join(default, "marker.txt"), "w") as f:
            f.write("old")
        with self.assertRaises(FileExistsError):
            self.build(out_dir=None)
        self.assertEqual(os.listdir(default), ["marker.txt"])

    def test_an_existing_empty_folder_is_fine(self):
        os.makedirs(self.out)
        problems, _, out_dir = self.build()
        self.assertEqual(problems, [])
        self.assertEqual(out_dir, self.out)
        self.assertTrue(os.path.exists(os.path.join(self.out, "vektor", "ZABAGED", "sectors.shp")))
        self.assertEqual(self.siblings(), ["ke"])

    def test_a_new_build_leaves_no_staging_folder(self):
        problems, _, out_dir = self.build()
        self.assertEqual(problems, [])
        self.assertEqual(out_dir, self.out)
        self.assertEqual(self.siblings(), ["ke"])

    def test_overwrite_replaces_the_old_folder(self):
        marker = self.make_old_folder()
        problems, _, out_dir = self.build(overwrite=True)
        self.assertEqual(problems, [])
        self.assertEqual(out_dir, self.out)
        self.assertFalse(os.path.exists(marker))
        self.assertTrue(os.path.exists(os.path.join(self.out, "vektor", "ZABAGED", "sectors.shp")))
        self.assertTrue(os.path.exists(os.path.join(self.out, "places.csv")))
        self.assertEqual(self.siblings(), ["ke"])                               # no .partial-* or .old-* left

    def test_failed_validation_keeps_the_old_folder_and_the_new_data_for_inspection(self):
        marker = self.make_old_folder()
        problems, report, kept = self.build(overwrite=True, area_tolerance=1e-9)
        self.assertTrue(problems)
        self.assertNotEqual(kept, self.out)
        self.assertEqual(os.path.dirname(kept), self.parent)
        self.assertIn(".partial-", os.path.basename(kept))
        self.assertTrue(os.path.exists(os.path.join(kept, "vektor", "ZABAGED", "sectors.shp")))
        self.assertTrue(os.path.exists(os.path.join(kept, "places.csv")))
        self.assertEqual(os.listdir(self.out), ["marker.txt"])                  # the old folder is untouched
        with open(marker) as f:
            self.assertEqual(f.read(), "old")
        self.assertEqual(self.siblings(), sorted(["ke", os.path.basename(kept)]))

    def test_a_crash_removes_the_staging_folder_and_leaves_the_old_one(self):
        self.make_old_folder()
        with self.assertRaises(FileNotFoundError):
            self.build(overwrite=True, landcover_mode="osm+worldcover")         # no WorldCover tiles
        self.assertEqual(self.siblings(), ["ke"])
        self.assertEqual(os.listdir(self.out), ["marker.txt"])


def expected_places():
    """The rows of the fixture: the village node of Testov and the city node of Testcity (S-JTSK, rounded)."""
    to_sjtsk = wgs84_to_sjtsk().transform
    lines = []
    for name, lon, lat in (("Testcity", 21.215, 48.706), ("Testov", 21.205, 48.705)):
        x, y = to_sjtsk(lon, lat)
        lines.append("%d;%d;0;%s;0;okres Test;KE" % (round(x), round(y), name))
    return lines


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


class PlacesOnlyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.osm = write_fixture(os.path.join(self.root, "mini.osm"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_level_8_municipalities_and_level_5_cities_are_listed(self):
        out = os.path.join(self.root, "out")
        rows = pipeline.build_places_only("ke", self.root, out_dir=out, osm_pbf=self.osm, region_name="Test kraj")
        self.assertEqual([r[3] for r in rows], ["Testcity", "Testov"])
        self.assertEqual(read_lines(os.path.join(out, "places.csv")), expected_places())
        self.assertEqual(os.listdir(out), ["places.csv"])                    # only that one file
        self.assertEqual(os.listdir(os.path.join(self.root, "work")), [])    # the temporary folder is removed

    def test_default_folder_is_the_region_folder(self):
        pipeline.build_places_only("ke", self.root, osm_pbf=self.osm, region_name="Test kraj")
        self.assertEqual(os.listdir(region_dir(self.root, "ke")), ["places.csv"])

    def test_the_work_folder_is_removed_when_it_fails(self):
        with self.assertRaises(ValueError):
            pipeline.build_places_only("ke", self.root, out_dir=os.path.join(self.root, "out"), osm_pbf=self.osm,
                                       region_name="Nowhere kraj")
        self.assertEqual(os.listdir(os.path.join(self.root, "work")), [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "out")))

    def test_full_build_lists_the_same_places(self):
        problems, report, out_dir = pipeline.build_region("ke", self.root, landcover_mode="osm", osm_pbf=self.osm,
                                                          region_name="Test kraj", area_tolerance=0.15)
        self.assertEqual(problems, [])
        self.assertEqual(report["places"], 2)
        self.assertEqual(read_lines(os.path.join(out_dir, "places.csv")), expected_places())


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

    def test_build_refuses_a_non_empty_output_folder_and_says_how_to_overwrite(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "marker.txt"), "w") as f:
                f.write("old")
            err = io.StringIO()
            with mock.patch.dict(os.environ, {"PATRAC_DATA": data}), contextlib.redirect_stderr(err):
                code = main(["build", "--region", "ke", "--out", out])
            self.assertEqual(code, 2)
            self.assertIn("--overwrite", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())
            self.assertEqual(os.listdir(out), ["marker.txt"])
            self.assertEqual(os.listdir(data), [])                               # nothing created under the data folder

    def test_places_command_writes_the_municipality_list(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as out:
            osm = pipeline.default_osm_path(data)
            os.makedirs(os.path.dirname(osm))
            write_fixture(osm)
            stdout = io.StringIO()
            with mock.patch.dict(os.environ, {"PATRAC_DATA": data}), mock.patch.dict(REGIONS, {"ke": "Test kraj"}), \
                    contextlib.redirect_stdout(stdout):
                code = main(["places", "--region", "ke", "--out", out])
            self.assertEqual(code, 0)
            path = os.path.join(out, "places.csv")
            self.assertEqual(stdout.getvalue().strip(), "wrote %s (2 places)" % path)
            self.assertEqual(os.listdir(out), ["places.csv"])
            self.assertEqual(read_lines(path), expected_places())
            self.assertEqual(os.listdir(os.path.join(data, "work")), [])
            self.assertFalse(os.path.exists(region_dir(data, "ke")))         # --out given: the region folder is not touched

    def test_places_command_needs_a_region(self):
        self.assertIn("--region", self.run_expecting_usage_error(["places"]))

    def test_places_is_in_the_module_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            main(["--help"])
        self.assertIn("places", out.getvalue())

    def test_build_help_lists_overwrite(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            main(["build", "--help"])
        self.assertIn("--overwrite", out.getvalue())


if __name__ == "__main__":
    unittest.main()
