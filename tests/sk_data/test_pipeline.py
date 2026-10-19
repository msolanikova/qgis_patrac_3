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
