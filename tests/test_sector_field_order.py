"""The plugin writes and reads sector attributes by position (id, label, typ, stav, prostredky, area_ha, ...).

Plain Python (no QGIS): reads the sources with `ast`. If the plugin's positional lists or the pipeline's column order
change, the data from tools/sk_data would silently end up in the wrong fields (a merged sector would get its type
from the id and its label from the type).
"""

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = ["id", "label", "typ"]


def parse(*parts):
    path = os.path.join(ROOT, *parts)
    with open(path, encoding="utf-8") as f:
        return ast.parse(f.read(), path)


def positional_lists(tree):
    """The first names of every `cols = [id, label, typ, None, ...]` list (one with at least 9 items) in the module."""
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "cols" for t in node.targets)
                and isinstance(node.value, ast.List) and len(node.value.elts) >= 9):
            found.append([e.id if isinstance(e, ast.Name) else None for e in node.value.elts[:3]])
    return found


class SectorFieldOrderTest(unittest.TestCase):
    def test_the_plugin_merge_writes_id_label_typ_first(self):
        found = positional_lists(parse("patracdockwidget.py"))
        self.assertEqual(found, [EXPECTED])             # merge sectors

    def test_the_plugin_split_by_grid_writes_id_label_typ_first(self):
        found = positional_lists(parse("main", "utils.py"))
        self.assertEqual(found, [EXPECTED])             # split by grid

    def test_the_pipeline_writes_the_columns_in_the_same_order(self):
        tree = parse("tools", "sk_data", "export.py")
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "sectors_frame")
        dicts = [n for n in ast.walk(function) if isinstance(n, ast.Dict)]
        self.assertEqual(len(dicts), 1)
        self.assertEqual([k.value for k in dicts[0].keys], EXPECTED)


if __name__ == "__main__":
    unittest.main()
