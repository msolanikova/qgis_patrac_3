import glob
import importlib
import os
import sys
import unittest

try:
    import qgis.core  # noqa: F401
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)  # the repo folder is itself an importable package


def module_names():
    names = []
    for sub, pattern in (("", "*.py"), ("main", "*.py"), ("ui", "*.py"), ("connect", "*.py")):
        for path in sorted(glob.glob(os.path.join(ROOT, sub, pattern))):
            base = os.path.splitext(os.path.basename(path))[0]
            if base == "__init__":
                continue
            names.append(".".join(p for p in (PACKAGE, sub, base) if p))
    return names


@unittest.skipUnless(HAVE_QGIS, "needs QGIS's Python (source tools/dev/qgis_env.sh)")
class ImportAllModulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.dirname(ROOT))

    def test_every_module_imports(self):
        for name in module_names():
            with self.subTest(module=name):
                importlib.import_module(name)


if __name__ == "__main__":
    unittest.main()
