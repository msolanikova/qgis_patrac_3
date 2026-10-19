import os
import sys
import unittest

try:
    from qgis.core import QgsGeometry, QgsPointXY
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)

DISTANCES = ["110", "250", "300", "420", "600", "1150", "1600", "2100", "4450"]


def square(x, y, size=100):
    return QgsGeometry.fromWkt("POLYGON((%s %s,%s %s,%s %s,%s %s,%s %s))" % (
        x, y, x + size, y, x + size, y + size, x, y + size, x, y))


def point(x, y):
    return QgsGeometry.fromPointXY(QgsPointXY(x, y))


@unittest.skipUnless(HAVE_QGIS, "needs QGIS's Python (source tools/dev/qgis_env.sh)")
class ComputePercentsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.dirname(ROOT))
        import importlib
        cls.area = importlib.import_module(PACKAGE + ".main.area")

    def test_get_percent_classes(self):
        gp = self.area.get_percent
        self.assertEqual(gp(DISTANCES, 0), 10)
        self.assertEqual(gp(DISTANCES, 109.9), 10)
        self.assertEqual(gp(DISTANCES, 110), 20)
        self.assertEqual(gp(DISTANCES, 299), 30)
        self.assertEqual(gp(DISTANCES, 4449), 95)
        self.assertEqual(gp(DISTANCES, 4450), 95)
        self.assertEqual(gp(DISTANCES, 1000000), 95)

    def test_method_uses_the_same_rule(self):
        task = self.area.CalculateDistance.get_percent
        self.assertEqual(task(None, DISTANCES, 200), 20)

    def test_distance_classes_per_sector(self):
        sectors = {
            1: square(0, 0),            # contains the point: 0 m
            2: square(250, 0),          # 200 m east of the point at x=50
            3: square(10000, 0),        # far away
        }
        result = self.area.compute_percents(sectors, [point(50, 50)], DISTANCES)
        self.assertEqual(result, {1: 10, 2: 20, 3: 95})

    def test_several_points_take_the_minimum_distance(self):
        sectors = {7: square(0, 0)}
        points = [point(5000, 0), point(100 + 500, 50), point(100 + 120, 50)]  # 5000 m, 500 m, 120 m
        self.assertEqual(self.area.compute_percents(sectors, points, DISTANCES), {7: 20})

    def test_no_points_behaves_like_the_old_code(self):
        # The old loop started from dist = 1000000 and never lowered it: every sector falls into the last class.
        sectors = {1: square(0, 0), 2: square(300, 0)}
        self.assertEqual(self.area.compute_percents(sectors, [], DISTANCES), {1: 95, 2: 95})

    def test_no_sectors(self):
        self.assertEqual(self.area.compute_percents({}, [point(0, 0)], DISTANCES), {})

    def test_progress_callback_is_called(self):
        seen = []
        sectors = {i: square(i * 1000, 0) for i in range(5)}
        self.area.compute_percents(sectors, [point(0, 0)], DISTANCES, progress=seen.append)
        self.assertTrue(seen)
        self.assertTrue(all(0 <= v <= 1 for v in seen))


if __name__ == "__main__":
    unittest.main()
