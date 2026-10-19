import itertools
import random
import re
import unittest
from unittest import mock

import numpy as np
import shapely
from shapely.geometry import box
from shapely.strtree import STRtree

from tools.sk_data import naming


def square(x, y, size=100.0):
    return box(x, y, x + size, y + size)


class CellTest(unittest.TestCase):
    def test_cell_of_uses_floor_for_negative_coordinates(self):
        self.assertEqual(naming.cell_of(0, 0), (0, 0))
        self.assertEqual(naming.cell_of(11999.9, 12000.0), (0, 1))
        self.assertEqual(naming.cell_of(-0.1, -0.1), (-1, -1))
        self.assertEqual(naming.cell_of(-12000.0, -12000.1), (-1, -2))
        self.assertEqual(naming.cell_of(-262580.66, -1240038.58), (-22, -104))   # Kosice

    def test_letters_of_the_four_cells_around_the_origin(self):
        self.assertEqual(naming.letter_of(0, 0), "A")
        self.assertEqual(naming.letter_of(-1, 0), "D")
        self.assertEqual(naming.letter_of(0, -1), "N")
        self.assertEqual(naming.letter_of(-1, -1), "S")
        self.assertEqual(len(naming.LETTERS), 16)
        self.assertEqual(len(set(naming.LETTERS)), 16)
        self.assertFalse(set("IOQ") & set(naming.LETTERS))

    def test_any_3_by_3_block_has_nine_different_letters(self):
        for cx, cy in itertools.product(range(-9, 9), repeat=2):
            block = {naming.letter_of(cx + i, cy + j) for i in range(3) for j in range(3)}
            self.assertEqual(len(block), 9, (cx, cy))

    def test_same_letter_means_at_least_4_cells_apart(self):
        cells = list(itertools.product(range(-6, 6), repeat=2))
        for (ax, ay), (bx, by) in itertools.combinations(cells, 2):
            if naming.letter_of(ax, ay) == naming.letter_of(bx, by):
                self.assertGreaterEqual(max(abs(ax - bx), abs(ay - by)), 4, ((ax, ay), (bx, by)))


class AssignTest(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(naming.assign_ids_and_labels([]), ([], []))

    def test_ids_are_1_to_n_strings_aligned_with_the_input(self):
        sectors = [(square(500, 0), "A"), (square(0, 0), "A"), (square(0, 1000), "B")]
        ids, labels = naming.assign_ids_and_labels(sectors)
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(labels), 3)
        self.assertEqual(sorted(ids), ["1", "2", "3"])
        self.assertTrue(all(isinstance(i, str) for i in ids + labels))

    def test_reading_order_is_north_to_south_bands_then_west_to_east(self):
        # all in cell (0, 0). Band = floor(-y / 500): the more northern sector (bigger y) comes first.
        north_east = square(5000, 3000)
        north_west = square(1000, 3100)       # same 500 m band as north_east (y 3050 and 3150 -> band -7 and -7)
        south = square(100, 1000)
        sectors = [(south, "A"), (north_east, "A"), (north_west, "A")]
        ids, labels = naming.assign_ids_and_labels(sectors)
        by_geom = {id(g): (i, l) for (g, _), i, l in zip(sectors, ids, labels)}
        self.assertEqual(by_geom[id(north_west)], ("1", "A1"))
        self.assertEqual(by_geom[id(north_east)], ("2", "A2"))
        self.assertEqual(by_geom[id(south)], ("3", "A3"))

    def test_cells_are_ordered_south_to_north_then_west_to_east_and_counters_restart(self):
        # cell (0,0) = A, cell (1,0) = B, cell (0,1) = E; cell order is (cy, cx)
        a1, a2 = square(100, 100), square(600, 100)
        b1 = square(12100, 100)
        e1 = square(100, 12100)
        sectors = [(e1, "x"), (b1, "x"), (a2, "x"), (a1, "x")]
        ids, labels = naming.assign_ids_and_labels(sectors)
        self.assertEqual(labels, ["E1", "B1", "A2", "A1"])
        self.assertEqual([ids[3], ids[2], ids[1], ids[0]], ["1", "2", "3", "4"])   # a1, a2, b1, e1

    def test_negative_coordinates_land_in_the_right_cells(self):
        # S-JTSK around Kosice: x about -262000, y about -1240000
        s1 = square(-262580, -1240038)
        s2 = square(-262580 + 15000, -1240038)
        ids, labels = naming.assign_ids_and_labels([(s1, "x"), (s2, "x")])
        cx1, cy1 = naming.cell_of(*s1.point_on_surface().coords[0])
        cx2, cy2 = naming.cell_of(*s2.point_on_surface().coords[0])
        self.assertEqual(labels[0], naming.letter_of(cx1, cy1) + "1")
        self.assertEqual(labels[1], naming.letter_of(cx2, cy2) + "1")
        self.assertNotEqual(labels[0][0], labels[1][0])

    def test_reference_point_is_point_on_surface_not_the_corner(self):
        # an L shape whose bounding box centre lies outside it; the cell comes from point_on_surface
        poly = box(11000, 0, 11500, 5000).union(box(11000, 0, 13000, 500))
        ids, labels = naming.assign_ids_and_labels([(poly, "x")])
        x, y = poly.point_on_surface().coords[0]
        self.assertEqual(labels[0], naming.letter_of(*naming.cell_of(x, y)) + "1")

    def test_result_does_not_depend_on_the_input_order(self):
        rnd = random.Random(7)
        sectors = [(square(rnd.uniform(-30000, 30000), rnd.uniform(-30000, 30000), rnd.uniform(50, 300)), "x") for _ in range(300)]
        ids, labels = naming.assign_ids_and_labels(sectors)
        expected = {sectors[k][0].wkb: (ids[k], labels[k]) for k in range(len(sectors))}
        for seed in (1, 2):
            shuffled = list(sectors)
            random.Random(seed).shuffle(shuffled)
            ids2, labels2 = naming.assign_ids_and_labels(shuffled)
            got = {shuffled[k][0].wkb: (ids2[k], labels2[k]) for k in range(len(shuffled))}
            self.assertEqual(got, expected)

    def test_identical_polygons_are_still_numbered_uniquely(self):
        ids, labels = naming.assign_ids_and_labels([(square(0, 0), "x"), (square(0, 0), "x")])
        self.assertEqual(sorted(ids), ["1", "2"])
        self.assertEqual(sorted(labels), ["A1", "A2"])

    def test_reading_order_returns_the_indices_in_id_order(self):
        sectors = [(square(12100, 100), "x"), (square(600, 100), "x"), (square(100, 100), "x"), (square(100, 12100), "x")]
        order = naming.reading_order(sectors)
        self.assertEqual(order, [2, 1, 0, 3])
        ids, _ = naming.assign_ids_and_labels(sectors)
        self.assertEqual([ids[k] for k in order], ["1", "2", "3", "4"])

    def test_too_many_sectors_are_refused(self):
        with mock.patch.object(naming, "MAX_SECTORS", 3):
            naming.assign_ids_and_labels([(square(i * 200, 0), "x") for i in range(2)])      # 2 < 3 fine
            with self.assertRaises(ValueError):
                naming.assign_ids_and_labels([(square(i * 200, 0), "x") for i in range(3)])

    def test_the_real_limit_is_one_million(self):
        self.assertEqual(naming.MAX_SECTORS, 1000000)

    def test_synthetic_layout_has_unique_ids_and_labels_unique_within_30_km(self):
        rnd = random.Random(11)
        sectors = []
        for gx in range(80):                         # 80 x 50 squares of 200 m spread over 200 km x 100 km (x < 0, y < 0 like S-JTSK)
            for gy in range(50):
                x = -400000 + gx * 2500 + rnd.uniform(0, 2000)
                y = -1300000 + gy * 2000 + rnd.uniform(0, 1500)
                sectors.append((square(x, y, 200), "x"))
        ids, labels = naming.assign_ids_and_labels(sectors)
        self.assertEqual(len(set(ids)), len(sectors))
        self.assertEqual(sorted(map(int, ids)), list(range(1, len(sectors) + 1)))
        self.assertTrue(all(re.match(r"^[A-Z][0-9]+$", l) for l in labels))
        pts = shapely.points(np.array([g.point_on_surface().coords[0] for g, _ in sectors]))
        a_idx, b_idx = STRtree(pts).query(pts, predicate="dwithin", distance=30000.0)
        for a, b in zip(a_idx, b_idx):
            if a != b:
                self.assertNotEqual(labels[a], labels[b])
        self.assertGreater(len(set(labels)), 100)


if __name__ == "__main__":
    unittest.main()
