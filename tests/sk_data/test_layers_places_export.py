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
