"""Tests of tools/sk_data. They need the geo libraries bundled with QGIS (shapely, geopandas, pyproj, GDAL)."""

import unittest

try:
    import geopandas  # noqa: F401
    import osgeo  # noqa: F401
    import pyproj  # noqa: F401
    import shapely  # noqa: F401
except ImportError as error:
    raise unittest.SkipTest("sk_data tests need QGIS's Python (source tools/dev/qgis_env.sh): %s" % error)
