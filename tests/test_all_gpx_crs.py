"""all.gpx was written in S-JTSK metres instead of WGS84 degrees.

The report export (reportExportSectors) opened sektory/shp/all.shp, which is copied from the template
without a .prj file, and never declared its CRS. QgsVectorFileWriter then had nothing to transform
from, and wrote the S-JTSK numbers as latitude and longitude. exportSectors already called setCrs
(upstream fix #109). Every function that opens all.shp must declare the CRS of that layer.
"""
import ast
import os
import unittest

SECTORS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main", "sectors.py")


def _opens_all_shp(call):
    if not (isinstance(call.func, ast.Name) and call.func.id == "QgsVectorLayer"):
        return False
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith("/shp/all.shp")
               for arg in call.args for n in ast.walk(arg))


class AllGpxCrsTest(unittest.TestCase):
    def test_every_all_shp_layer_gets_its_crs(self):
        with open(SECTORS, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        checked = []
        for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            names = set()
            for node in ast.walk(func):
                if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                        and _opens_all_shp(node.value)):
                    names.update(t.id for t in node.targets if isinstance(t, ast.Name))
            for name in names:
                checked.append(func.name)
                has_set_crs = any(
                    isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "setCrs"
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == name
                    for n in ast.walk(func))
                self.assertTrue(has_set_crs, func.name + " opens all.shp as '" + name + "' but never calls " + name + ".setCrs(...)")
        # the guard must see both export paths, otherwise it silently checks nothing
        self.assertEqual(sorted(checked), ["exportSectors", "reportExportSectors"])


if __name__ == "__main__":
    unittest.main()
