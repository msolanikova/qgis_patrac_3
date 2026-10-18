# QGIS and GIS terms for a Python developer

**QGIS**: a desktop map application (like an IDE for maps). Its engine is a C++ library with Python bindings (`qgis.core`, `qgis.gui`). Patrac is a Python plugin loaded inside it.

**Plugin**: a Python package in the QGIS profile's `python/plugins/` folder with a `metadata.txt` and a `classFactory(iface)` function in `__init__.py`. `iface` is the handle to the running QGIS window. QGIS calls `initGui()` when the plugin is enabled and `unload()` when it is disabled.

**Layer**: one dataset shown on the map. A **vector** layer holds geometry plus attributes, like a table with a geometry column. A **raster** layer is a grid of cell values, like an image. `QgsVectorLayer(path, name, "ogr")` opens a vector file, and `QgsRasterLayer` a raster.

**Shapefile (.shp)**: an old vector file format that is really 4-5 files sharing a name (`.shp` geometry, `.dbf` attributes, `.shx` index, `.prj` CRS, `.cpg` encoding). Patrac still uses it for its data. **GeoPackage (.gpkg)** is the modern single-file replacement (a SQLite database).

**OGR / GDAL**: the C library, with Python module `osgeo`, that reads and writes almost every geo file format. QGIS uses it underneath. `ogr` covers vector data, and `gdal` raster data.

**CRS (coordinate reference system)**: says what the numbers in a coordinate mean. **EPSG:4326** is WGS84 latitude/longitude in degrees, what GPS devices and GPX files use. **EPSG:3857** is Web Mercator, used by web basemaps. **EPSG:5514** is S-JTSK, a Czechoslovak system whose units are metres. Because it is metric, Patrac can compute distances and areas directly. The coordinates in S-JTSK are negative numbers, for example `-548069;-1265300` (x;y), which is normal for this system. Slovakia used the same system, so Patrac keeps it.

**Transform**: converting coordinates between CRSs, with `QgsCoordinateTransform`. Always transform GPX points from 4326 to 5514 before measuring in metres.

**Geometry / feature**: a `QgsGeometry` is a point, line or polygon. A `QgsFeature` is one geometry plus its attribute values, that is one row of a layer.

**WMS / tile service**: a web server that returns map images for a requested area. Patrac's basemaps (orthophoto, topographic maps) are WMS or tile layers added by URL.

**Processing algorithm**: a ready-made GIS operation run with `processing.run("native:buffer", {...})`. Examples: `native:extractbyextent`, `native:zonalstatisticsfb`. `native:` ones are built into QGIS, `gdal:` call GDAL, `grass7:` call GRASS GIS (Patrac no longer uses them).

**QgsTask**: QGIS's background-job class. Patrac runs the heavy steps (clipping data, calculating areas) as tasks so the window does not freeze.

**Sector**: in Patrac, a polygon of about 10-20 hectares with one type of land use. The search area is cut into sectors. Each gets a probability of containing the missing person and is assigned to a search team.

**ISRID distances**: statistics from past searches (International Search & Rescue Incident Database) about how far each type of missing person typically ends up from where they were last seen. They are in `grass/distances.txt`, one row per person type, nine distances for the 10%...95% quantiles.

**POD (probability of detection)**: the chance that a searcher passing through a sector finds the person if the person is there. Used by the GPX analysis (sub-project 4).
