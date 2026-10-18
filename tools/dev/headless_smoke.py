# Headless smoke test for the Patrac plugin inside the real QGIS binary.
# Run it with tools/dev/headless_smoke.sh (throw-away profile, 120 s limit). Running QGIS directly against your real profile may block on a keychain prompt.
# Prints PASS/FAIL lines and quits QGIS. Exit code is not reliable with --code, so read the output.
import json
import os
import traceback

results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception:
        ok, detail = False, traceback.format_exc()
    line = "%s: %s%s" % ("PASS" if ok else "FAIL", name, (" - " + str(detail)) if detail else "")
    results.append(ok)
    print("SMOKE " + line, flush=True)


def run():
    from qgis import utils
    from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem,
                           QgsCoordinateTransform, QgsPointXY, QgsProject)

    def load():
        ok = utils.loadPlugin("qgis_patrac")
        return ok, "" if ok else "loadPlugin returned False"

    def start():
        ok = utils.startPlugin("qgis_patrac")
        return ok, "" if ok else "startPlugin returned False"

    def dock():
        from qgis.PyQt.QtWidgets import QDockWidget
        plugin = utils.plugins["qgis_patrac"]
        plugin.showWidget()  # same code the toolbar/menu action calls
        docks = [d.objectName() for d in utils.iface.mainWindow().findChildren(QDockWidget)]
        ok = "PatracDockWidget" in docks
        return ok, "" if ok else "docks: %s" % docks

    def reload_does_not_duplicate_ui():
        # Unloading must remove the dock panel and toolbar; otherwise every reload adds another.
        from qgis.PyQt.QtCore import QCoreApplication, QEvent
        from qgis.PyQt.QtWidgets import QDockWidget, QToolBar
        window = utils.iface.mainWindow()

        def counts():
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            docks = [d for d in window.findChildren(QDockWidget) if d.objectName() == "PatracDockWidget"]
            bars = [t for t in window.findChildren(QToolBar) if t.objectName() == "Patrac Toolbar"]
            return len(docks), len(bars)

        before = counts()
        utils.unloadPlugin("qgis_patrac")
        after_unload = counts()
        utils.loadPlugin("qgis_patrac")
        utils.startPlugin("qgis_patrac")
        after_reload = counts()
        ok = before == (1, 1) and after_unload == (0, 0) and after_reload == (1, 1)
        return ok, "(docks, toolbars) before=%s after_unload=%s after_reload=%s" % (before, after_unload, after_reload)

    def non_patrac_project_is_ignored():
        # Opening any ordinary QGIS project fires on_project_change; it must not raise.
        plugin = utils.plugins["qgis_patrac"]
        QgsProject.instance().clear()
        plugin.dockWidget.on_project_change()
        return True, ""

    profile = QgsApplication.qgisSettingsDirPath()
    config_path = os.path.join(profile, "patrac_settings", "config", "config.json")

    def config():
        if not os.path.isfile(config_path):
            return False, "missing " + config_path
        with open(config_path, encoding="utf-8") as f:
            data_path = json.load(f).get("data_path", "")
        return data_path.endswith("/patracdata/"), "data_path=%s" % data_path

    def doc():
        p = os.path.join(os.path.expanduser("~"), "patracdata", "doc", "index.html")
        return os.path.isfile(p), p

    def transform():
        src = QgsCoordinateReferenceSystem("EPSG:4326")
        dst = QgsCoordinateReferenceSystem("EPSG:5514")
        if not (src.isValid() and dst.isValid()):
            return False, "invalid CRS"
        xform = QgsCoordinateTransform(src, dst, QgsProject.instance())
        if not xform.isValid():
            return False, "transform invalid (PROJ data not found? PROJ_LIB=%s)" % os.environ.get("PROJ_LIB")
        pt = xform.transform(QgsPointXY(21.2611, 48.7164))
        # Reference values for Kosice (QGIS x, y in S-JTSK EPSG:5514), tolerance 500 m.
        ok = abs(pt.x() - -262576) < 500 and abs(pt.y() - -1240028) < 500
        return ok, "Kosice -> x=%.1f y=%.1f (expected about -262576, -1240028; PROJ_LIB=%s)" % (
            pt.x(), pt.y(), os.environ.get("PROJ_LIB"))

    def debugpy_listen():
        import debugpy
        debugpy.configure(python=os.environ.get("QGIS_PY", ""))
        host, port = debugpy.listen(("127.0.0.1", 0))  # any free port: a real QGIS debug session may hold 5678
        return True, "%s:%s" % (host, port)

    check("plugin loaded without exception", load)
    check("plugin started without exception", start)
    check("dock widget created and showWidget() runs", dock)
    check("unload + reload leaves exactly one Patrac panel and toolbar", reload_does_not_duplicate_ui)
    check("project change on a non-Patrac project does not raise", non_patrac_project_is_ignored)
    check("config.json exists with data_path ending /patracdata/", config)
    check("~/patracdata/doc/index.html exists", doc)
    check("EPSG:4326 -> EPSG:5514 transform (Kosice)", transform)
    check("debugpy.listen on a free 127.0.0.1 port", debugpy_listen)

    print("SMOKE RESULT: %s" % ("ALL PASS" if all(results) else "FAILURES"), flush=True)
    # Quit without the "save project?" prompt (nothing was changed in the project).
    QgsApplication.instance().exit(0 if all(results) else 1)


from qgis.PyQt.QtCore import QTimer
# Let QGIS finish startup (and its own plugin init) before running the checks.
QTimer.singleShot(3000, run)
