import ast
import importlib
import os
import shutil
import sys
import tempfile
import time
import unittest

try:
    from qgis.core import QgsApplication, QgsProject
    from qgis.PyQt.QtCore import QCoreApplication, QObject, QThread
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)
INTERVAL_MS = 300000


class SaveProjectNotAThreadTest(unittest.TestCase):
    """Plain Python: QgsProject.write() must not run in a worker thread."""

    def setUp(self):
        with open(os.path.join(ROOT, "connect", "connect.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        self.cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SaveProject")

    def test_is_not_a_qthread_and_has_no_run(self):
        bases = [ast.unparse(b) for b in self.cls.bases]
        self.assertNotIn("QThread", bases)
        methods = {n.name for n in self.cls.body if isinstance(n, ast.FunctionDef)}
        self.assertNotIn("run", methods)
        self.assertTrue({"start", "stop", "terminate", "save_now"} <= methods, sorted(methods))


@unittest.skipUnless(HAVE_QGIS, "needs QGIS's Python (source tools/dev/qgis_env.sh)")
class SaveNowTest(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.dirname(ROOT))
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        if QCoreApplication.instance() is None:
            cls.app = QgsApplication([], False)
        cls.connect = importlib.import_module(PACKAGE + ".connect.connect")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="patrac_save_")
        self.cwd = os.getcwd()
        os.chdir(self.tmp)  # QGIS drops symbology-style.db into the current directory
        self.project = QgsProject.instance()
        self.project.clear()
        self.saver = self.connect.SaveProject()

    def tearDown(self):
        self.saver.stop()
        self.project.clear()
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_project(self, with_region):
        os.mkdir(os.path.join(self.tmp, "config"))
        if with_region:
            with open(os.path.join(self.tmp, "config", "region.txt"), "w") as f:
                f.write("ke")
        path = os.path.join(self.tmp, "test.qgz")
        self.project.setFileName(path)
        self.assertTrue(self.project.write())
        old = time.time() - 100  # make a rewrite visible even on a coarse file system clock
        os.utime(path, (old, old))
        return path, os.path.getmtime(path)

    def modify(self):
        self.project.setTitle("changed %s" % time.time())

    def test_is_a_main_thread_object_with_an_active_timer(self):
        self.assertIsInstance(self.saver, QObject)
        self.assertNotIsInstance(self.saver, QThread)
        self.assertFalse(hasattr(self.saver, "run"))
        self.saver.start()
        self.assertTrue(self.saver.timer.isActive())
        self.assertEqual(self.saver.timer.interval(), INTERVAL_MS)
        self.assertEqual(self.saver.timer.thread(), QCoreApplication.instance().thread())
        self.saver.stop()
        self.assertFalse(self.saver.timer.isActive())
        self.saver.start()
        self.saver.terminate()
        self.assertFalse(self.saver.timer.isActive())

    def test_rewrites_the_project_when_region_txt_exists(self):
        path, before = self.write_project(with_region=True)
        self.modify()
        self.saver.save_now()
        self.assertGreater(os.path.getmtime(path), before)

    def test_writes_nothing_without_region_txt(self):
        path, before = self.write_project(with_region=False)
        self.modify()
        self.saver.save_now()
        self.assertEqual(os.path.getmtime(path), before)

    def test_writes_nothing_without_a_project_file_name(self):
        self.project.setFileName("")
        self.modify()
        self.saver.save_now()
        self.assertEqual(os.listdir(self.tmp), [])
        self.assertEqual(self.project.fileName(), "")

    def test_failure_is_logged_not_raised(self):
        from unittest import mock
        path, before = self.write_project(with_region=True)
        messages = []
        QgsApplication.messageLog().messageReceived.connect(lambda m, tag, level: messages.append((tag, m)))
        fake = mock.Mock()
        fake.fileName.return_value = path
        fake.write.side_effect = RuntimeError("disk full")
        with mock.patch.object(self.connect.QgsProject, "instance", return_value=fake):
            self.saver.save_now()  # must not raise
        fake.write.assert_called_once()
        self.assertTrue([m for tag, m in messages if tag == "Patrac" and "disk full" in m], messages)


if __name__ == "__main__":
    unittest.main()
