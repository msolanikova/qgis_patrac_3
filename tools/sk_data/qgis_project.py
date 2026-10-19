# -*- coding: utf-8 -*-
"""Build a QGIS project to inspect one or more built regions, with the plugin's own layer styles."""

import os
from pathlib import Path

STYLES_DIR = Path(__file__).resolve().parents[2] / "styles"
OSM_TILES = "type=xyz&url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png&zmax=19&zmin=0"


# typ -> (fill colour, English legend name). The plugin's own style (styles/sectors_unique_*.qml) lacks most of
# these types (built-up, gardens, parks, cemeteries, wetland), so the inspection project uses this one.
TYPE_STYLE = {
    "LPSTROM": ("#1b7837", "Forest"),
    "LPKROV": ("#7fbf7b", "Shrubs"),
    "ORNAPU": ("#e6c15a", "Arable land"),
    "TRTRPO": ("#b8e186", "Grassland"),
    "SADZAH": ("#f4a582", "Orchard, garden, allotment"),
    "VINICE": ("#c51b7d", "Vineyard"),
    "AREZAS": ("#bdbdbd", "Built-up area"),
    "ARUCZA": ("#7b7b7b", "Industrial, institutional"),
    "HRBITO": ("#8c6bb1", "Cemetery"),
    "ZAHPAR": ("#41ab5d", "Park, sports ground"),
    "VODPLO": ("#3182bd", "Water"),
    "KOLEJI": ("#252525", "Railway land"),
    "MAZCHU": ("#41b6c4", "Wetland"),
    "SKLADK": ("#a6611a", "Landfill"),
    "ULOMIS": ("#bf812d", "Quarry"),
    "ELEKTR": ("#e31a1c", "Power plant"),
    "LETISTE": ("#fdae61", "Airport"),
    "OTHER": ("#ff7f00", "Unclassified (no land-use data)"),
}
BOOKMARK_SIZE_M = (12000.0, 8000.0)   # width, height in EPSG:3857 map units (about 7.9 x 5.3 km on the ground at 48.7 N)


def init_qgis(qgis_app=None):
    """Start QGIS without a GUI, with the data-provider plugins loaded (needed for the web basemap)."""
    from qgis.core import QgsApplication
    qgis_app = qgis_app or os.environ.get("QGIS_APP", "/Applications/QGIS-LTR.app")
    QgsApplication.setPrefixPath(os.path.join(qgis_app, "Contents", "MacOS"), True)
    QgsApplication.setPluginPath(os.path.join(qgis_app, "Contents", "PlugIns", "qgis"))
    app = QgsApplication([], False)
    app.initQgis()
    return app


def typ_renderer():
    """Categorized renderer on 'typ' with the colours and English names of TYPE_STYLE."""
    from qgis.core import QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsRendererCategory
    categories = []
    for typ, (colour, name) in TYPE_STYLE.items():
        symbol = QgsFillSymbol.createSimple({"color": colour, "outline_color": "#555555", "outline_width": "0.1"})
        categories.append(QgsRendererCategory(typ, symbol, "%s (%s)" % (name, typ)))
    return QgsCategorizedSymbolRenderer("typ", categories)


def build_project(region_dirs, out_path, locale="en", styles_dir=STYLES_DIR, bookmarks=()):
    """Write a .qgz with an OpenStreetMap basemap, streams, roads, forest tracks and one sectors layer per region.

    region_dirs: [(label, region folder)]; streams, roads and tracks come from the first folder.
    bookmarks: [(name, lon, lat)]: spatial bookmarks (a view of 12000 x 8000 EPSG:3857 map units, about
    7.9 x 5.3 km on the ground at 48.7 N); the project opens on the first one.
    Returns the list of layer names written. Raises if a layer is invalid (an invalid basemap is dropped
    silently by QGIS otherwise).
    """
    from qgis.core import (QgsBookmark, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject,
                           QgsRasterLayer, QgsReferencedRectangle, QgsRectangle, QgsVectorLayer)
    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    basemap = QgsRasterLayer(OSM_TILES, "OpenStreetMap", "wms")
    if not basemap.isValid():
        raise RuntimeError("the OpenStreetMap basemap layer is invalid (data provider plugins not loaded?)")
    first = region_dirs[0][1]
    shp = lambda folder, name: os.path.join(folder, "vektor", "ZABAGED", name + ".shp")
    entries = [(basemap, None)]
    for name, label in (("vodtok", "Streams (vodtok)"), ("cesta", "Roads and paths (cesta)"), ("lespru", "Forest tracks (lespru)")):
        entries.append((QgsVectorLayer(shp(first, name), label, "ogr"), "%s_%s.qml" % (name, locale)))
    for label, folder in region_dirs:
        entries.append((QgsVectorLayer(shp(folder, "sectors"), "Sectors: " + label, "ogr"), "sectors_unique_%s.qml" % locale))
    for layer, style in entries:
        if not layer.isValid():
            raise RuntimeError("invalid layer: %s" % layer.name())
        if style and style.startswith("sectors_"):
            layer.setRenderer(typ_renderer())
        elif style:
            layer.loadNamedStyle(str(Path(styles_dir) / style))
        project.addMapLayer(layer)
    layers = [layer for layer, _ in entries]
    root = project.layerTreeRoot()
    root.setHasCustomLayerOrder(True)
    root.setCustomLayerOrder(list(reversed(layers)))
    root.findLayer(layers[2].id()).setItemVisibilityChecked(False)       # about 100,000 road lines for the whole kraj: hidden by default
    for layer in layers[4:]:
        layer.setOpacity(0.7)
    for layer in layers[5:]:
        root.findLayer(layer.id()).setItemVisibilityChecked(False)        # show one sectors layer at a time
    extent = QgsCoordinateTransform(layers[4].crs(), project.crs(), project).transformBoundingBox(layers[4].extent())
    extent.scale(1.05)
    to_map = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), project.crs(), project)
    for name, lon, lat in bookmarks:
        centre = to_map.transform(QgsPointXY(lon, lat))
        view = QgsRectangle(centre.x() - BOOKMARK_SIZE_M[0] / 2, centre.y() - BOOKMARK_SIZE_M[1] / 2,
                            centre.x() + BOOKMARK_SIZE_M[0] / 2, centre.y() + BOOKMARK_SIZE_M[1] / 2)
        bookmark = QgsBookmark()
        bookmark.setName(name)
        bookmark.setExtent(QgsReferencedRectangle(view, project.crs()))
        project.bookmarkManager().addBookmark(bookmark)
        if name == bookmarks[0][0]:
            extent = view
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent, project.crs()))
    project.viewSettings().setPresetFullExtent(QgsReferencedRectangle(extent, project.crs()))
    if not project.write(str(out_path)):
        raise RuntimeError("could not write %s" % out_path)
    return [layer.name() for layer in layers]
