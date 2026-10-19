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

    def test_admin_areas_accept_several_levels(self):
        polygons = gpd.GeoDataFrame(
            {"tags": [{"boundary": "administrative", "admin_level": "8", "name": "Testov"},
                      {"boundary": "administrative", "admin_level": "5", "name": "Testcity"},
                      {"boundary": "administrative", "admin_level": "6", "name": "Okres Test"},
                      {"boundary": "administrative", "admin_level": "9", "name": "Borough"}]},
            geometry=[box(0, 0, 1, 1)] * 4, crs=4326)
        self.assertEqual(places.MUNICIPALITY_LEVELS, ("8", "5"))
        self.assertEqual(sorted(places.admin_areas(polygons, places.MUNICIPALITY_LEVELS)["name"]), ["Testcity", "Testov"])
        self.assertEqual(sorted(places.admin_areas(polygons, ["6", "9"])["name"]), ["Borough", "Okres Test"])
        self.assertEqual(list(places.admin_areas(polygons, "8")["name"]), ["Testov"])      # a plain string is one level
        self.assertEqual(list(places.admin_areas(polygons, "5")["name"]), ["Testcity"])

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
        return self.build_frame(d, export.sectors_frame(sectors), region_geom)

    def build_frame(self, d, frame, region_geom):
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

    def test_sectors_frame_adds_string_id_and_label_after_typ(self):
        frame = export.sectors_frame([(box(0, 0, 300, 250), "LPSTROM"), (box(300, 0, 600, 250), "ORNAPU")])
        self.assertEqual(list(frame.columns), ["typ", "id", "label", "geometry"])
        self.assertEqual(sorted(frame["id"]), ["1", "2"])
        self.assertEqual(list(frame["label"]), ["A1", "A2"])         # west to east inside one cell and one band
        self.assertEqual(list(frame["id"]), ["1", "2"])
        for column in ("id", "label"):
            self.assertTrue(all(isinstance(v, str) for v in frame[column]), column)

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

    # --- the id and label checks -------------------------------------------------------------------------------

    def two_sectors(self, distance=5000, **columns):
        """Two 7.5 ha sectors `distance` m apart (west to east); columns replace the generated ones. Returns (problems, report)."""
        a, b = box(0, 0, 300, 250), box(distance, 0, distance + 300, 250)
        frame = export.sectors_frame([(a, "LPSTROM"), (b, "ORNAPU")])
        for name, values in columns.items():
            if values is None:
                frame = frame.drop(columns=[name])
            else:
                frame[name] = values
        with tempfile.TemporaryDirectory() as d:
            return self.build_frame(d, frame, a.union(b))

    def test_good_ids_and_labels_are_reported(self):
        problems, report = self.two_sectors()
        self.assertEqual(problems, [])
        self.assertEqual(report["id_max"], 2)
        self.assertEqual(report["labels"], {"max_length": 2, "duplicated_labels": 0})

    def test_missing_id_or_label_field(self):
        text = " | ".join(self.two_sectors(id=None)[0])
        self.assertIn("no 'id' field", text)
        self.assertNotIn("label", text)
        text = " | ".join(self.two_sectors(label=None)[0])
        self.assertIn("no 'label' field", text)

    def test_duplicate_ids(self):
        problems, _ = self.two_sectors(id=["7", "7"])
        self.assertIn("duplicate id", " | ".join(problems))

    def test_ids_must_be_positive_integers_below_the_plugin_base(self):
        for bad in ("0", "-3", "1.5", "abc", "", "1000000", "5000000"):
            problems, _ = self.two_sectors(id=["1", bad])
            self.assertIn("not a positive integer below 1000000", " | ".join(problems), bad)
        problems, report = self.two_sectors(id=["1", "999999"])
        self.assertEqual(problems, [])
        self.assertEqual(report["id_max"], 999999)

    def test_label_format(self):
        for bad in ("142", "k142", "K", "KA1", "K1a", "K-1", ""):
            problems, _ = self.two_sectors(label=["A1", bad])
            self.assertIn("do not match", " | ".join(problems), bad)

    def test_the_same_label_close_together_is_a_problem(self):
        problems, report = self.two_sectors(distance=5000, label=["K1", "K1"])
        self.assertIn("same label", " | ".join(problems))
        self.assertIn("K1", " | ".join(problems))

    def test_the_same_label_far_apart_is_fine_and_counted(self):
        problems, report = self.two_sectors(distance=60000, label=["K1", "K1"])
        self.assertEqual(problems, [])
        self.assertEqual(report["labels"], {"max_length": 2, "duplicated_labels": 1})

    def test_the_30_km_limit(self):
        self.assertIn("same label", " | ".join(self.two_sectors(distance=29000, label=["K1", "K1"])[0]))
        self.assertEqual(self.two_sectors(distance=31000, label=["K1", "K1"])[0], [])

    def test_label_check_is_fast_for_many_sectors(self):
        import time
        import numpy as np
        from tools.sk_data.validate import label_conflicts
        rnd = np.random.RandomState(3)
        n = 110000
        xy = rnd.uniform(0, 200000, size=(n, 2))
        labels = np.array(["K%d" % (i % 40) for i in range(n)], dtype=object)          # 2750 sectors per label
        t0 = time.time()
        label_conflicts(labels, xy)
        self.assertLess(time.time() - t0, 60)

    def test_label_conflicts_finds_every_close_pair_of_the_same_label(self):
        import numpy as np
        from tools.sk_data.validate import label_conflicts
        labels = np.array(["A1", "A1", "B2", "B2", "A1", "C3"], dtype=object)
        xy = np.array([[0, 0], [29000, 0], [0, 0], [31000, 0], [100000, 100000], [1, 1]], dtype=float)
        self.assertEqual(label_conflicts(labels, xy), {"A1": 1})          # B2 is far apart, C3 is alone

    def test_an_empty_sectors_file_gives_a_report_not_an_exception(self):
        import geopandas as gpd
        empty = gpd.GeoDataFrame({"typ": [], "id": [], "label": []}, geometry=[], crs=5514)
        with tempfile.TemporaryDirectory() as d:
            problems, report = self.build_frame(d, empty, box(0, 0, 600, 250))
        self.assertIsInstance(problems, list)
        self.assertEqual(report["labels"]["max_length"], 0)
        self.assertEqual(report["labels"]["duplicated_labels"], 0)
        self.assertEqual(report["id_max"], 0)

    def test_empty_or_null_labels_are_a_format_problem_not_a_duplicate_label(self):
        problems, report = self.two_sectors(distance=1000, label=[None, None])
        text = " | ".join(problems)
        self.assertIn("do not match", text)
        self.assertNotIn("same label", text)
        self.assertEqual(report["labels"]["duplicated_labels"], 0)
        problems, _ = self.two_sectors(distance=1000, label=["", ""])
        text = " | ".join(problems)
        self.assertIn("do not match", text)
        self.assertNotIn("same label", text)

    def test_label_conflicts_ignores_empty_labels(self):
        import numpy as np
        from tools.sk_data.validate import label_conflicts
        self.assertEqual(label_conflicts(np.array(["", ""], dtype=object), np.array([[0.0, 0.0], [1.0, 1.0]])), {})

    def test_missing_files_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            problems, _ = validate(d, box(0, 0, 1, 1), SectorSize(), load_rules().classes)
            self.assertIn("missing sectors.shp", problems)


if __name__ == "__main__":
    unittest.main()
