import unittest

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, box

from tools.sk_data import roads

BASE_X, BASE_Y = -262000.0, -1245000.0
REGION = box(BASE_X - 50000, BASE_Y - 50000, BASE_X + 50000, BASE_Y + 50000)
COLUMNS = ["id", "name", "highway", "tracktype", "surface", "worse", "length_m", "geometry"]


def _line(points):
    return LineString([(BASE_X + x, BASE_Y + y) for x, y in points])


def lines_gdf(*rows):
    """GeoDataFrame like read_lines + to_sjtsk from (tags, points) rows, points in metres from the base point.
    A list of point lists gives a MultiLineString."""
    geoms = [MultiLineString([_line(part) for part in points]) if isinstance(points[0], list) else _line(points)
             for _, points in rows]
    return gpd.GeoDataFrame({"tags": [dict(t) for t, _ in rows]}, geometry=geoms, crs=5514)


def tags(highway=None, **extra):
    result = dict(extra)
    if highway is not None:
        result["highway"] = highway
    return result


class ClassifyTest(unittest.TestCase):
    def check(self, cases):
        for given, expected in cases:
            with self.subTest(tags=given):
                self.assertIs(roads.classify(given), expected)

    def test_highway_values(self):
        good = ["residential", "unclassified", "tertiary", "service", "living_street", "cycleway", "footway"]
        worse = ["track", "path", "bridleway"]
        none = ["motorway", "trunk", "primary", "secondary", "tertiary_link", "secondary_link", "steps",
                "construction"]
        self.check([(tags(h), False) for h in good] + [(tags(h), True) for h in worse]
                   + [(tags(h), None) for h in none] + [({}, None), ({"waterway": "stream"}, None)])

    def test_surface(self):
        self.check([
            (tags("residential", surface="gravel"), True),
            (tags("residential", surface="asphalt"), False),
            (tags("residential", surface="asphalt;gravel"), True),
            (tags("residential", surface="asphalt;paved"), False),
            (tags("residential", surface="asphalt; gravel"), True),
            (tags("track", surface="asphalt", tracktype="grade1"), True),
        ])

    def test_excluded_by_tags(self):
        self.check([
            (tags("residential", tunnel="yes"), None),
            (tags("residential", tunnel="culvert"), None),
            (tags("footway", footway="sidewalk"), None),
            (tags("footway", footway="crossing"), None),
            (tags("service", service="driveway"), None),
            (tags("service", service="parking_aisle"), None),
            (tags("track", access="private"), None),
            (tags("track", access="no"), None),
            (tags("track", access="yes"), True),
            (tags("service", service="alley"), False),
            (tags("footway", footway="path"), False),
        ])

    def test_display_name(self):
        self.assertEqual(roads.display_name({"name": "Hlavná", "ref": "III/3345"}), "Hlavná")
        self.assertEqual(roads.display_name({"ref": "III/3345"}), "III/3345")
        self.assertIsNone(roads.display_name({}))
        self.assertEqual(roads.display_name({"name": "", "ref": "III/3345"}), "III/3345")
        self.assertIsNone(roads.display_name({"name": ""}))


TRACK = {"highway": "track"}


class RoadPiecesTest(unittest.TestCase):
    def pieces(self, *rows, region=REGION):
        return roads.road_pieces(lines_gdf(*rows), region)

    def lengths(self, frame):
        return sorted(frame["length_m"].tolist())

    def test_a_junction_in_the_middle_of_a_way_cuts_it(self):
        out = self.pieces((TRACK, [(0, 0), (1000, 0), (2000, 0)]), (TRACK, [(1000, 0), (1000, 1500)]))
        self.assertEqual(self.lengths(out), [1000.0, 1000.0, 1500.0])
        self.assertTrue(all(w is True for w in out["worse"].tolist()))

    def test_two_stretches_with_the_same_tags_are_chained_through_a_plain_node(self):
        street = {"highway": "residential", "name": "Hlavná"}
        out = self.pieces((street, [(0, 0), (1000, 0)]), (street, [(1000, 0), (2000, 0)]))
        self.assertEqual(self.lengths(out), [2000.0])
        out = self.pieces((street, [(0, 0), (1000, 0)]), (dict(street, surface="gravel"), [(1000, 0), (2000, 0)]))
        self.assertEqual(self.lengths(out), [1000.0, 1000.0])
        out = self.pieces((street, [(0, 0), (1000, 0)]), (dict(street, name="Krátka"), [(1000, 0), (2000, 0)]))
        self.assertEqual(self.lengths(out), [1000.0, 1000.0])

    def test_ways_that_cross_without_a_shared_node_are_not_cut_or_joined(self):
        out = self.pieces((TRACK, [(0, 0), (2000, 0)]), (TRACK, [(1000, -500), (1000, 500)]))
        self.assertEqual(self.lengths(out), [1000.0, 2000.0])

    def test_a_chain_longer_than_five_km_is_cut_into_equal_parts(self):
        out = self.pieces((TRACK, [(0, 0), (12000, 0)]))
        self.assertEqual(self.lengths(out), [4000.0, 4000.0, 4000.0])
        geoms = sorted(out.geometry, key=lambda g: g.coords[0])
        for a, b in zip(geoms, geoms[1:]):
            self.assertAlmostEqual(a.coords[-1][0], b.coords[0][0], places=3)
            self.assertAlmostEqual(a.coords[-1][1], b.coords[0][1], places=3)
        self.assertEqual(self.lengths(self.pieces((TRACK, [(0, 0), (5000, 0)]))), [5000.0])
        self.assertEqual(self.lengths(self.pieces((TRACK, [(0, 0), (5001, 0)]))), [2500.5, 2500.5])

    def test_pieces_shorter_than_thirty_metres_are_dropped(self):
        self.assertEqual(len(self.pieces((TRACK, [(0, 0), (29.9, 0)]))), 0)
        self.assertEqual(self.lengths(self.pieces((TRACK, [(0, 0), (30, 0)]))), [30.0])
        out = self.pieces((TRACK, [(0, 0), (1000, 0), (2000, 0)]),
                          ({"highway": "path"}, [(1000, 0), (1000, 10)]))
        self.assertEqual(self.lengths(out), [1000.0, 1000.0])

    def test_a_closed_way_gives_a_ring_piece(self):
        out = self.pieces((TRACK, [(0, 0), (500, 0), (500, 500), (0, 500), (0, 0)]))
        self.assertEqual(self.lengths(out), [2000.0])
        coords = list(out.geometry.iloc[0].coords)
        self.assertGreaterEqual(len(set(coords)), 2)
        self.assertEqual(coords[0], coords[-1])
        out = self.pieces((TRACK, [(0, 0), (3000, 0), (3000, 3000), (0, 3000), (0, 0)]))
        self.assertEqual(self.lengths(out), [4000.0, 4000.0, 4000.0])

    def test_a_zero_length_way_and_duplicate_vertices_do_no_harm(self):
        self.assertEqual(len(self.pieces((TRACK, [(0, 0), (0, 0)]))), 0)
        out = self.pieces((TRACK, [(0, 0), (0, 0), (1000, 0)]))
        self.assertEqual(self.lengths(out), [1000.0])
        self.assertEqual(len(out.geometry.iloc[0].coords), 2)

    def test_excluded_ways_give_no_pieces_and_tags_are_copied(self):
        out = self.pieces(
            ({"highway": "motorway"}, [(0, 1000), (2000, 1000)]),
            ({"highway": "residential", "tunnel": "yes"}, [(0, 2000), (2000, 2000)]),
            ({"highway": "footway", "footway": "sidewalk"}, [(0, 3000), (2000, 3000)]),
            ({"highway": "track", "access": "private"}, [(0, 4000), (2000, 4000)]),
            ({"highway": "track", "tracktype": "grade3", "surface": "ground"}, [(0, 5000), (1000, 5000)]),
            ({"highway": "residential", "surface": "asphalt;gravel"}, [(0, 6000), (1100, 6000)]),
            ({"highway": "path"}, [(0, 7000), (1200, 7000)]),
        )
        self.assertEqual(self.lengths(out), [1000.0, 1100.0, 1200.0])
        rows = {r["length_m"]: r for r in out.to_dict("records")}
        track = rows[1000.0]
        self.assertEqual((track["highway"], track["tracktype"], track["surface"]), ("track", "grade3", "ground"))
        self.assertIsNone(track["name"])
        residential = rows[1100.0]
        self.assertIs(residential["worse"], True)
        self.assertEqual(residential["surface"], "asphalt;gravel")
        path = rows[1200.0]
        self.assertIsNone(path["tracktype"])
        self.assertIsNone(path["surface"])

    def test_pieces_belong_to_the_region_by_their_midpoint(self):
        region = box(BASE_X - 1000, BASE_Y - 1000, BASE_X + 1500, BASE_Y + 1000)
        out = self.pieces((TRACK, [(1000, 0), (1900, 0)]), (TRACK, [(1400, 100), (2400, 100)]), region=region)
        self.assertEqual(self.lengths(out), [900.0])
        self.assertAlmostEqual(out.geometry.iloc[0].length, 900.0)

    def test_a_multilinestring_is_handled_like_its_parts(self):
        out = self.pieces((TRACK, [[(0, 0), (1000, 0), (2000, 0)], [(1000, 0), (1000, 1500)]]))
        self.assertEqual(self.lengths(out), [1000.0, 1000.0, 1500.0])

    def test_ids_are_r_numbers_in_midpoint_order_and_do_not_depend_on_input_order(self):
        rows = [
            (TRACK, [(0, 0), (1000, 0), (2000, 0)]),
            (TRACK, [(1000, -500), (1000, 1500)]),
            ({"highway": "residential", "name": "Hlavná"}, [(3000, 500), (3500, 200), (4200, 900)]),
            ({"highway": "path"}, [(-500, 3000), (-400, 2000)]),
            ({"highway": "service"}, [(5000, 5000), (5000, 4000)]),
        ]
        out = self.pieces(*rows)
        self.assertEqual(list(out.columns), COLUMNS)
        self.assertEqual(out["id"].tolist(), ["r%d" % i for i in range(1, 6)])
        reversed_rows = [(t, list(reversed(points))) for t, points in reversed(rows)]
        again = self.pieces(*reversed_rows)
        self.assertEqual(len(out), len(again))
        for column in COLUMNS[:-1]:
            self.assertEqual(out[column].tolist(), again[column].tolist(), column)
        for a, b in zip(out.geometry, again.geometry):
            self.assertTrue(a.equals_exact(b, 0.001), (a.wkt, b.wkt))
        for geom, length in zip(out.geometry, out["length_m"]):
            self.assertLessEqual(geom.coords[0], geom.coords[-1])
            self.assertEqual(length, round(geom.length, 1))
        mids = [g.interpolate(0.5, normalized=True) for g in out.geometry]
        keys = [(round(m.x, 2), round(m.y, 2), length) for m, length in zip(mids, out["length_m"])]
        self.assertEqual(keys, sorted(keys))

    def test_an_empty_input_gives_an_empty_frame_with_the_columns(self):
        for frame in (lines_gdf(), lines_gdf(({"highway": "motorway"}, [(0, 0), (2000, 0)]))):
            out = roads.road_pieces(frame, REGION)
            self.assertEqual(len(out), 0)
            self.assertEqual(list(out.columns), COLUMNS)
            self.assertEqual(out.crs.to_epsg(), 5514)


if __name__ == "__main__":
    unittest.main()
