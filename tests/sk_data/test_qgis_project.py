import os
import subprocess
import sys
import unittest
from pathlib import Path

try:
    import qgis.core  # noqa: F401
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

REPO = Path(__file__).resolve().parents[2]

# Runs in its own process: QGIS must be shut down with exitQgis() after the test, and a QGIS application that
# has been shut down makes later tests in the same process (tests/test_imports.py imports plugin modules that
# log to QGIS at import time) crash with a segmentation fault.
SCRIPT = '''
import os, tempfile
from qgis.core import QgsProject
from tests.sk_data.osm_fixture import write_fixture
from tools.sk_data import pipeline, qgis_project

with tempfile.TemporaryDirectory() as d:
    osm = write_fixture(os.path.join(d, "mini.osm"))
    problems, _, out_dir = pipeline.build_region("ke", d, osm_pbf=osm, region_name="Test kraj",
                                                 landcover_mode="osm", area_tolerance=0.15)
    assert problems == [], problems
    app = qgis_project.init_qgis()
    try:
        out = os.path.join(d, "p.qgz")
        names = qgis_project.build_project([("test", out_dir)], out, bookmarks=[("Fixture forest", 21.205, 48.705)])
        assert names[0] == "OpenStreetMap", names
        assert "Sectors: test" in names, names
        project = QgsProject()
        assert project.read(out)
        loaded = {layer.name(): layer.isValid() for layer in project.mapLayers().values()}
        assert len(loaded) == 5, loaded
        assert all(loaded.values()), loaded          # an invalid basemap used to vanish silently
        assert not project.viewSettings().defaultViewExtent().isEmpty()
        bookmarks = project.bookmarkManager().bookmarks()
        assert [b.name() for b in bookmarks] == ["Fixture forest"]
        sectors = project.mapLayersByName("Sectors: test")[0]
        renderer = sectors.renderer()
        assert renderer.classAttribute() == "typ"
        assert {c.value() for c in renderer.categories()} == set(qgis_project.TYPE_STYLE)
        labels = {c.value(): c.label() for c in renderer.categories()}
        assert "Unclassified" in labels["OTHER"], labels
        del bookmarks, renderer, sectors
        project.clear()
        del project      # QGIS objects must be gone before exitQgis()
    finally:
        app.exitQgis()
print("PROJECT TEST OK")
'''


@unittest.skipUnless(HAVE_QGIS, "needs QGIS's Python (source tools/dev/qgis_env.sh)")
class QgisProjectTest(unittest.TestCase):
    def test_project_contains_a_valid_basemap_and_all_layers(self):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        result = subprocess.run([sys.executable, "-c", SCRIPT], cwd=REPO, env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, "exit code %s\n%s" % (result.returncode, result.stderr[-3000:]))
        self.assertIn("PROJECT TEST OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
