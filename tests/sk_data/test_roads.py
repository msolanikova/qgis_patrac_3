import itertools
import os
import re
import tempfile
import unittest

from unittest import mock

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, MultiPolygon, box

from tests.sk_data.osm_fixture import ROADS_OSM_XML, write_roads_fixture
from tools.sk_data import extract, roads
from tools.sk_data.rules import load_rules

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

    def test_mountain_grade_paths_are_excluded(self):
        # "searched by the mountain service, not by us": T3 (demanding_mountain_hiking) and harder; T2 and plain hiking stay
        kept = [("hiking", "path", True), ("mountain_hiking", "path", True), ("mountain_hiking", "track", True),
                ("mountain_hiking", "footway", False)]
        gone = [(scale, highway) for scale in ("demanding_mountain_hiking", "alpine_hiking", "demanding_alpine_hiking",
                                               "difficult_alpine_hiking")
                for highway in ("path", "track", "footway", "bridleway", "residential")]
        self.check([(tags(highway, sac_scale=scale), worse) for scale, highway, worse in kept]
                   + [(tags(highway, sac_scale=scale), None) for scale, highway in gone])
        self.assertEqual(roads.EXCLUDED_SAC_SCALES, {"demanding_mountain_hiking", "alpine_hiking",
                                                     "demanding_alpine_hiking", "difficult_alpine_hiking"})

    def test_indoor_ways_are_excluded(self):
        self.check([
            (tags("footway", indoor="yes"), None),
            (tags("path", indoor="yes"), None),
            (tags("footway", indoor="no"), False),
            (tags("footway", indoor="room"), False),
        ])

    def test_more_footway_values_are_excluded(self):
        self.check([
            (tags("footway", footway="traffic_island"), None),
            (tags("footway", footway="access_aisle"), None),
            (tags("footway", footway="link"), False),   # the owner has not decided about links: unchanged
        ])
        self.assertTrue({"traffic_island", "access_aisle"} <= roads.EXCLUDED_FOOTWAYS)

    def test_foot_access_overrides_a_general_ban(self):
        self.check([
            (tags("track", access="private", foot="yes"), True),
            (tags("track", access="no", foot="permissive"), True),
            (tags("path", access="no", foot="designated"), True),
            (tags("track", access="private", foot="no"), None),
            (tags("track", access="private", foot="private"), None),
            (tags("track", access="private", foot="customers"), None),
            (tags("track", access="no"), None),
            (tags("track", foot="yes"), True),
            (tags("track", foot="no"), True),   # foot=no alone is not a ban the rules know about
        ])
        self.assertEqual(roads.ACCESS_FOOT_OVERRIDE, {"yes", "permissive", "designated"})

    def test_display_name(self):
        self.assertEqual(roads.display_name({"name": "Hlavná", "ref": "III/3345"}), "Hlavná")
        self.assertEqual(roads.display_name({"ref": "III/3345"}), "III/3345")
        self.assertIsNone(roads.display_name({}))
        self.assertEqual(roads.display_name({"name": "", "ref": "III/3345"}), "III/3345")
        self.assertIsNone(roads.display_name({"name": ""}))


TRACK = {"highway": "track"}


def rotate_ring(points, k):
    """A closed point list started k vertices later; other point lists unchanged."""
    if len(points) < 4 or points[0] != points[-1]:
        return points
    ring = points[:-1]
    k %= len(ring)
    rotated = ring[k:] + ring[:k]
    return rotated + [rotated[0]]


def built_box(x0, y0, x1, y1):
    return box(BASE_X + x0, BASE_Y + y0, BASE_X + x1, BASE_Y + y1)


class RoadPiecesTest(unittest.TestCase):
    def pieces(self, *rows, region=REGION, built_up=None):
        return roads.road_pieces(lines_gdf(*rows), region, built_up)

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

    def assert_same_pieces(self, out, again):
        self.assertEqual(len(out), len(again))
        for column in COLUMNS[:-1]:
            self.assertEqual(out[column].tolist(), again[column].tolist(), column)
        for a, b in zip(out.geometry, again.geometry):
            self.assertTrue(a.equals_exact(b, 0.001), (a.wkt, b.wkt))

    def test_ids_are_r_numbers_in_midpoint_order_and_do_not_depend_on_input_order(self):
        rows = [
            (TRACK, [(0, 0), (1000, 0), (2000, 0)]),
            (TRACK, [(1000, -500), (1000, 1500)]),
            ({"highway": "residential", "name": "Hlavná"}, [(3000, 500), (3500, 200), (4200, 900)]),
            ({"highway": "path"}, [(-500, 3000), (-400, 2000)]),
            ({"highway": "service"}, [(5000, 5000), (5000, 4000)]),
            # a ring with a spur at J = (10500, 0), the ring way starting elsewhere
            (TRACK, [(10000, 500), (10000, 0), (10500, 0), (10500, 500), (10000, 500)]),
            ({"highway": "path"}, [(10500, 0), (11000, -300)]),
            # a plain ring
            (TRACK, [(20000, 0), (20600, 0), (20600, 600), (20000, 600), (20000, 0)]),
        ]
        out = self.pieces(*rows)
        self.assertEqual(list(out.columns), COLUMNS)
        self.assertEqual(out["id"].tolist(), ["r%d" % i for i in range(1, 9)])
        ring_with_spur = [g for g in out.geometry if g.is_closed and g.length == 2000.0][0]
        self.assertEqual(ring_with_spur.coords[0], (BASE_X + 10500, BASE_Y + 0))
        variants = {
            "reversed": [(t, list(reversed(points))) for t, points in reversed(rows)],
            "rotated": [(t, rotate_ring(points, 2)) for t, points in rows],
            "reversed and rotated": [(t, list(reversed(rotate_ring(points, 3)))) for t, points in reversed(rows)],
        }
        for label, variant in variants.items():
            with self.subTest(label):
                self.assert_same_pieces(out, self.pieces(*variant))
        for geom, length in zip(out.geometry, out["length_m"]):
            self.assertLessEqual(geom.coords[0], geom.coords[-1])
            self.assertEqual(length, round(geom.length, 1))
        mids = [g.interpolate(0.5, normalized=True) for g in out.geometry]
        keys = [(round(m.x, 2), round(m.y, 2), length) for m, length in zip(mids, out["length_m"])]
        self.assertEqual(keys, sorted(keys))

    def test_ids_do_not_depend_on_input_order_for_pieces_with_the_same_geometry(self):
        # real data has such pairs (an OSM way drawn twice with different tags)
        same = [(0, 0), (1000, 0)]
        rows = [({"highway": "track"}, same),
                ({"highway": "residential", "name": "Hlavn\u00e1"}, same),
                ({"highway": "track", "tracktype": "grade1"}, same),
                ({"highway": "track", "tracktype": "grade1", "surface": "gravel"}, same),
                ({"highway": "path", "name": "Z"}, same),
                ({"highway": "path", "name": "A"}, same)]
        out = self.pieces(*rows)
        self.assertEqual(len(out), 6)
        for order in itertools.permutations(range(len(rows))):
            with self.subTest(order=order):
                self.assert_same_pieces(out, self.pieces(*[rows[i] for i in order]))
        # nulls last: the track without tracktype comes after the one with it
        tracks = out[out["highway"] == "track"]
        self.assertEqual(tracks["tracktype"].tolist(), ["grade1", "grade1", None])
        self.assertEqual(tracks["surface"].tolist(), ["gravel", None, None])

    def test_pieces_in_built_up_polygons_are_dropped_by_their_midpoint(self):
        rows = [(TRACK, [(0, 0), (1000, 0)]),                 # midpoint (500, 0)
                (TRACK, [(0, 5000), (1000, 5000)]),           # midpoint (500, 5000)
                ({"highway": "residential"}, [(0, 8000), (1000, 8000)]),
                (TRACK, [(2000, 3000), (3000, 3000)])]        # midpoint (2500, 3000): outside, its end is not
        built_up = [built_box(400, -100, 600, 100), built_box(0, 7900, 2000, 8100)]
        out = self.pieces(*rows, built_up=built_up)
        self.assertEqual(self.lengths(out), [1000.0, 1000.0])
        mids = sorted((round(g.interpolate(0.5, normalized=True).x - BASE_X), round(g.interpolate(0.5, normalized=True).y - BASE_Y))
                      for g in out.geometry)
        self.assertEqual(mids, [(500, 5000), (2500, 3000)])
        self.assertEqual(out["id"].tolist(), ["r1", "r2"])   # ids are given after the exclusion

    def test_a_piece_whose_end_is_in_a_built_up_polygon_but_whose_midpoint_is_not_is_kept(self):
        out = self.pieces((TRACK, [(0, 0), (1000, 0)]), built_up=[built_box(700, -100, 1200, 100)])
        self.assertEqual(self.lengths(out), [1000.0])
        out = self.pieces((TRACK, [(0, 0), (1000, 0)]), built_up=[built_box(-100, -100, 300, 100)])
        self.assertEqual(self.lengths(out), [1000.0])

    def test_built_up_may_be_one_geometry_a_multipolygon_or_a_geoseries(self):
        rows = [(TRACK, [(0, 0), (1000, 0)]), (TRACK, [(0, 3000), (1000, 3000)]), (TRACK, [(0, 6000), (1000, 6000)])]
        a, b = built_box(400, -100, 600, 100), built_box(400, 2900, 600, 3100)
        for label, built_up in {"polygon": a, "multipolygon": MultiPolygon([a, b]), "geoseries": gpd.GeoSeries([a, b], crs=5514),
                                "list": [a, b], "tuple": (a, b), "nested multipolygon": [MultiPolygon([a, b])]}.items():
            with self.subTest(label):
                expected = 2 if label == "polygon" else 1
                self.assertEqual(len(self.pieces(*rows, built_up=built_up)), expected)

    def test_nothing_is_dropped_without_built_up_polygons(self):
        rows = [(TRACK, [(0, 0), (1000, 0)]), (TRACK, [(0, 3000), (1000, 3000)])]
        for built_up in (None, [], gpd.GeoSeries([], crs=5514), MultiPolygon(), box(0, 0, 0, 0).buffer(0)):
            with self.subTest(built_up=repr(built_up)[:40]):
                self.assertEqual(len(self.pieces(*rows, built_up=built_up)), 2)

    def test_exclusion_in_built_up_areas_can_be_switched_off(self):
        rows = [(TRACK, [(0, 0), (1000, 0)]), (TRACK, [(0, 3000), (1000, 3000)])]
        built_up = [built_box(400, -100, 600, 100)]
        self.assertTrue(roads.EXCLUDE_IN_BUILT_UP)
        self.assertEqual(roads.BUILT_UP_CLASS, 6)
        self.assertEqual(len(self.pieces(*rows, built_up=built_up)), 1)
        with mock.patch.object(roads, "EXCLUDE_IN_BUILT_UP", False):
            self.assertEqual(len(self.pieces(*rows, built_up=built_up)), 2)

    def test_built_up_class_is_the_built_up_class_of_the_rules(self):
        classes = load_rules().classes
        self.assertEqual({t for t, c in classes.items() if c == roads.BUILT_UP_CLASS},
                         {"AREZAS", "ARUCZA", "HRBITO", "PRSTPR", "ROZTRA", "ROZZRI", "ULOMIS", "USNAOD", "INTRAV"})

    def test_a_long_ring_is_cut_the_same_whatever_its_start_and_direction(self):
        ring = [(0, 0), (3000, 0), (3000, 3000), (0, 3000), (0, 0)]
        out = self.pieces((TRACK, ring))
        self.assertEqual(self.lengths(out), [4000.0, 4000.0, 4000.0])
        for k in range(4):
            for points in (rotate_ring(ring, k), list(reversed(rotate_ring(ring, k)))):
                with self.subTest(points=points):
                    self.assert_same_pieces(out, self.pieces((TRACK, points)))

    def test_an_empty_input_gives_an_empty_frame_with_the_columns(self):
        for frame in (lines_gdf(), lines_gdf(({"highway": "motorway"}, [(0, 0), (2000, 0)]))):
            out = roads.road_pieces(frame, REGION)
            self.assertEqual(len(out), 0)
            self.assertEqual(list(out.columns), COLUMNS)
            self.assertEqual(out.crs.to_epsg(), 5514)


class RoadsFromOsmFileTest(unittest.TestCase):
    """The hand-written OSM file of tests.sk_data.osm_fixture.ROADS_OSM_XML, see the list of ways there."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.osm = write_roads_fixture(os.path.join(cls.tmp.name, "roads.osm"))
        boundary = extract.region_boundary(cls.osm, "Road kraj", os.path.join(cls.tmp.name, "w0"))
        cls.gpkg = extract.extract_roads(cls.osm, extract.bbox_of(boundary), os.path.join(cls.tmp.name, "x"))
        os.mkdir(os.path.join(cls.tmp.name, "w1"))
        cls.pieces = roads.region_roads(cls.osm, "Road kraj", os.path.join(cls.tmp.name, "w1"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_extract_roads_keeps_only_included_highways(self):
        self.assertTrue(self.gpkg.endswith(".gpkg"))
        lines = extract.read_lines(self.gpkg)
        found = sorted(t["highway"] for t in lines["tags"])
        self.assertEqual(set(found), {"residential", "unclassified", "track", "path", "footway", "service"})
        self.assertTrue(set(found) <= roads.INCLUDED_HIGHWAYS)
        self.assertNotIn("motorway", found)
        self.assertEqual(len(found), 12)   # every way of the file but the motorway

    def test_region_roads_returns_the_expected_pieces(self):
        out = self.pieces
        self.assertEqual(list(out.columns), COLUMNS)
        self.assertEqual(out.crs.to_epsg(), 5514)
        self.assertEqual(sorted(out["id"], key=lambda i: int(i[1:])), ["r%d" % k for k in range(1, 7)])
        rows = {kind: out[mask] for kind, mask in (
            ("street", out["highway"] == "residential"), ("gravel", out["highway"] == "unclassified"),
            ("grade2", out["tracktype"] == "grade2"), ("path", out["highway"] == "path"),
            ("ring", (out["highway"] == "track") & out["tracktype"].isna()))}
        self.assertEqual({k: len(v) for k, v in rows.items()},
                         {"street": 2, "gravel": 1, "grade2": 1, "path": 1, "ring": 1})
        street = rows["street"]
        self.assertEqual(set(street["name"]), {'Hlavn\u00e1 "star\u00e1"'})
        self.assertEqual(sorted(street["length_m"].round(-1)), [370.0, 740.0])
        self.assertFalse(street["worse"].any())
        self.assertTrue(street["tracktype"].isna().all() and street["surface"].isna().all())
        gravel = rows["gravel"].iloc[0]
        self.assertEqual((gravel["surface"], gravel["worse"], gravel["name"]), ("gravel", True, None))
        self.assertAlmostEqual(gravel["length_m"], 368.0, delta=10)
        grade2 = rows["grade2"].iloc[0]
        self.assertEqual((grade2["highway"], grade2["worse"], grade2["name"], grade2["surface"]), ("track", True, None, None))
        self.assertAlmostEqual(grade2["length_m"], 667.0, delta=10)
        path = rows["path"].iloc[0]
        self.assertEqual((path["worse"], path["length_m"] // 100), (True, 6.0))   # not cut where it crosses the street
        ring = rows["ring"].iloc[0]
        self.assertTrue(ring["worse"])
        self.assertTrue(ring.geometry.is_closed)
        self.assertGreaterEqual(len(ring.geometry.coords), 4)
        self.assertAlmostEqual(ring["length_m"], 1404.0, delta=20)

    def test_the_excluded_ways_and_the_outside_track_are_absent(self):
        self.assertEqual(set(self.pieces["highway"]), {"residential", "unclassified", "track", "path"})
        self.assertNotIn("footway", set(self.pieces["highway"]))
        self.assertNotIn("service", set(self.pieces["highway"]))
        self.assertEqual(int((self.pieces["highway"] == "track").sum()), 2)   # grade2 and the ring; not the outside one
        self.assertEqual(int((self.pieces["highway"] == "residential").sum()), 2)   # the street; not the tunnel
        self.assertEqual(len(self.pieces), 6)
        self.assertEqual(int((self.pieces["highway"] == "path").sum()), 1)   # not the alpine_hiking path 191

    def test_an_area_without_any_road_gives_an_empty_frame(self):
        only_the_area = os.path.join(self.tmp.name, "area.osm")
        with open(only_the_area, "w", encoding="utf-8") as f:
            f.write(re.sub(r'  <way id="1\d\d">.*?</way>\n', "", ROADS_OSM_XML, flags=re.S))
        work = os.path.join(self.tmp.name, "w2")
        os.mkdir(work)
        out = roads.region_roads(only_the_area, "Road kraj", work)
        self.assertEqual((len(out), list(out.columns), out.crs.to_epsg()), (0, COLUMNS, 5514))


if __name__ == "__main__":
    unittest.main()
