import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Project layers belong to the main thread: the layer tree panel and the canvas read them while a task runs.
FORBIDDEN = {"startEditing", "commitChanges", "updateFeature", "setSubsetString", "mapLayers", "dataProvider"}


def method_calls(path, class_name, method_name):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for node in cls.body:
                if isinstance(node, ast.FunctionDef) and node.name == method_name:
                    names = set()
                    for call in ast.walk(node):
                        if isinstance(call, ast.Call):
                            func = call.func
                            names.add(func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", ""))
                    return names
    raise AssertionError("%s.%s not found in %s" % (class_name, method_name, path))


class CalculateDistanceThreadingTest(unittest.TestCase):
    def test_run_does_not_touch_project_layers(self):
        calls = method_calls(os.path.join(ROOT, "main", "area.py"), "CalculateDistance", "run")
        self.assertEqual(sorted(calls & FORBIDDEN), [])

    def test_results_are_written_from_finished_on_the_main_thread(self):
        path = os.path.join(ROOT, "main", "area.py")
        self.assertIn("write_results", method_calls(path, "CalculateDistance", "finished"))
        writer = method_calls(path, "CalculateDistance", "write_results")
        self.assertTrue({"startEditing", "commitChanges"} <= writer, sorted(writer))


if __name__ == "__main__":
    unittest.main()
