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
        expected = os.environ["PATRAC_DATA"] + "/"
        return data_path == expected, "data_path=%s expected=%s" % (data_path, expected)

    def doc():
        p = os.path.join(os.environ["PATRAC_DATA"], "doc", "index.html")
        return os.path.isfile(p), p

    def municipalities_come_from_region_folders():
        widget = utils.plugins["qgis_patrac"].dockWidget
        names, regions = widget.municipalities_names, widget.municipalities_regions
        ok = names == ["Ardovo (okres Rožňava)", "Košice (okres Košice I)"] and regions == ["XX", "XX"]
        return ok, "names=%s regions=%s" % (names, regions)

    def osm_basemap_is_added():
        project = QgsProject.instance()
        project.clear()
        try:
            utils.plugins["qgis_patrac"].dockWidget.Utils.addOsmBasemap()
            layers = list(project.mapLayers().values())
            ok = len(layers) == 1 and layers[0].name() == "OpenStreetMap" and layers[0].isValid()
            return ok, "layers=%s" % [(l.name(), l.isValid()) for l in layers]
        finally:
            project.clear()

    def osm_basemap_not_duplicated():
        # A second call, or a project that already has an OSM layer (the template's "OSM Standard"), must not add another one.
        from qgis.core import QgsRasterLayer
        project = QgsProject.instance()
        project.clear()
        utils_obj = utils.plugins["qgis_patrac"].dockWidget.Utils

        def osm_layers():
            return [l for l in project.mapLayers().values() if "tile.openstreetmap.org" in l.source()]

        try:
            utils_obj.addOsmBasemap()
            first = [l.name() for l in osm_layers()]
            utils_obj.addOsmBasemap()
            second = [l.name() for l in osm_layers()]
            project.clear()
            template_osm = QgsRasterLayer(
                "type=xyz&url=http://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19&zmin=0", "OSM Standard", "wms")
            project.addMapLayer(template_osm)
            utils_obj.addOsmBasemap()
            names = [l.name() for l in project.mapLayers().values()]
            ok = len(first) == 1 and len(second) == 1 and "OpenStreetMap" not in names
            return ok, "after 1st call=%s after 2nd call=%s with template layer=%s" % (first, second, names)
        finally:
            project.clear()

    def land_use_style_loads():
        # The "sectors by land use" style must load on a sectors-like layer and know the land-use types of the Slovak pipeline.
        from qgis.core import QgsCategorizedSymbolRenderer, QgsVectorLayer
        import sys
        styles = os.path.join(os.path.dirname(sys.modules["qgis_patrac"].__file__), "styles")  # the repo, through the plugin symlink
        wanted = {"AREZAS", "ARUCZA", "HRBITO", "ZAHPAR", "SADZAH", "MAZCHU"}
        problems = []
        for lang in ("cs", "en", "uk"):
            layer = QgsVectorLayer("Polygon?crs=EPSG:5514&field=typ:string(10)", "sectors", "memory")
            message, ok = layer.loadNamedStyle(os.path.join(styles, "sectors_unique_%s.qml" % lang))
            renderer = layer.renderer()
            if not ok:
                problems.append("%s: loadNamedStyle failed: %s" % (lang, message))
            elif not isinstance(renderer, QgsCategorizedSymbolRenderer):
                problems.append("%s: renderer is %s" % (lang, type(renderer).__name__))
            else:
                missing = wanted - {c.value() for c in renderer.categories()}
                if missing:
                    problems.append("%s: no category for %s" % (lang, sorted(missing)))
        return not problems, "; ".join(problems)

    def no_czech_only_buttons():
        # The CUZK map services (ZTM10, aerial) cover only the Czech Republic; their buttons must not be in the toolbar or the menu.
        plugin = utils.plugins["qgis_patrac"]
        menu = [a for m in utils.iface.pluginMenu().actions() if m.menu() and m.menu().title().replace("&", "") == "Patrac"
                for a in m.menu().actions()]
        toolbar = list(plugin.toolbar.actions())
        texts = lambda actions: [(a.text(), a.toolTip(), a.objectName()) for a in actions]
        bad = [t for t in texts(toolbar) + texts(menu) if any("CUZK" in x.upper() or "ZTM10" in x.upper() for x in t)]
        ok = not bad and len(toolbar) > 5 and len(menu) == 1  # the menu keeps its one "show/hide panel" action
        return ok, "toolbar actions=%d menu actions=%d czech-only=%s" % (len(toolbar), len(menu), bad)

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
    check("OpenStreetMap basemap is added as one valid layer", osm_basemap_is_added)
    check("addOsmBasemap does not add a second OpenStreetMap layer", osm_basemap_not_duplicated)
    check("sectors land-use style loads in cs/en/uk with categories for the new types", land_use_style_loads)
    check("toolbar and plugin menu have no Czech-only CUZK buttons", no_czech_only_buttons)
    check("config.json exists with data_path equal to PATRAC_DATA/", config)
    check("PATRAC_DATA/doc/index.html exists", doc)
    check("municipality list comes from PATRAC_DATA/kraje/*/places.csv", municipalities_come_from_region_folders)
    check("EPSG:4326 -> EPSG:5514 transform (Kosice)", transform)
    check("debugpy.listen on a free 127.0.0.1 port", debugpy_listen)

    print("SMOKE RESULT: %s" % ("ALL PASS" if all(results) else "FAILURES"), flush=True)
    # Quit without the "save project?" prompt (nothing was changed in the project).
    QgsApplication.instance().exit(0 if all(results) else 1)


from qgis.PyQt.QtCore import QTimer
# Let QGIS finish startup (and its own plugin init) before running the checks.
QTimer.singleShot(3000, run)
