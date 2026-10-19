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
