import unittest

import geopandas as gpd
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

    def test_splitting_emits_no_floating_point_warnings(self):
        import warnings
        l_shape = Polygon([(0, 0), (900, 0), (900, 200), (300, 200), (300, 700), (0, 700)])
        with warnings.catch_warnings():
            warnings.simplefilter("error")   # numpy reports flags that GEOS sets inside oriented_envelope
            split_oversized([(box(0, 0, 400, 215), "ORNAPU"), (l_shape, "OTHER"), (box(0, 0, 800, 500), "LPSTROM")], SIZE)

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
