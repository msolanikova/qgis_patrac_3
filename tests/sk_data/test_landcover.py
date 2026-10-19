import math
import os
import tempfile
import unittest

import geopandas as gpd
import numpy as np
from osgeo import gdal, osr
from shapely.geometry import box

from tools.sk_data.config import SectorSize
from tools.sk_data.landcover import osm_cover, worldcover_cover
from tools.sk_data.rules import load_rules

RULES = load_rules()
SIZE = SectorSize()


class OsmCoverTest(unittest.TestCase):
    def test_keeps_typed_polygons_of_sufficient_area_only(self):
        polygons = gpd.GeoDataFrame(
            {"tags": [{"landuse": "forest"}, {"landuse": "forest"}, {"highway": "pedestrian"}, {"natural": "water"}]},
            geometry=[box(0, 0, 100, 100), box(0, 0, 20, 20), box(0, 0, 100, 100), box(0, 0, 60, 60)], crs=5514)
        cover = osm_cover(polygons, RULES, SIZE)
        self.assertEqual(sorted(cover["typ"]), ["LPSTROM", "VODPLO"])  # 400 m2 forest and the untyped polygon are dropped
        self.assertEqual(cover.crs.to_epsg(), 5514)


def write_raster(path, array, origin=(21.200, 48.706), pixel=0.0001):
    ds = gdal.GetDriverByName("GTiff").Create(path, array.shape[1], array.shape[0], 1, gdal.GDT_Byte)
    ds.SetGeoTransform((origin[0], pixel, 0, origin[1], 0, -pixel))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(array)
    ds.FlushCache()
    ds = None


class WorldCoverTest(unittest.TestCase):
    def test_classes_become_typed_polygons_and_speckles_are_removed(self):
        array = np.full((60, 100), 10, dtype=np.uint8)   # trees
        array[:, 50:] = 40                                # cropland on the right half
        array[10:13, 10:13] = 30                          # a 3 x 3 pixel grass speckle inside the trees
        with tempfile.TemporaryDirectory() as d:
            tif = os.path.join(d, "wc.tif")
            write_raster(tif, array)
            cover = worldcover_cover([tif], (21.200, 48.700, 21.210, 48.706), RULES, SIZE)
        self.assertEqual(sorted(cover["typ"]), ["LPSTROM", "ORNAPU"])
        self.assertEqual(cover.crs.to_epsg(), 5514)
        expected = (0.01 * 111320 * math.cos(math.radians(48.703))) * (0.006 * 110574)  # 0.01 x 0.006 degrees in m2
        self.assertAlmostEqual(cover.geometry.area.sum(), expected, delta=expected * 0.02)
        areas = dict(zip(cover["typ"], cover.geometry.area))
        self.assertAlmostEqual(areas["LPSTROM"], areas["ORNAPU"], delta=areas["LPSTROM"] * 0.02)  # the speckle is gone

    def test_unmapped_values_are_dropped(self):
        array = np.zeros((60, 100), dtype=np.uint8)       # 0 = no data in WorldCover
        array[:, :50] = 80                                # water
        with tempfile.TemporaryDirectory() as d:
            tif = os.path.join(d, "wc.tif")
            write_raster(tif, array)
            cover = worldcover_cover([tif], (21.200, 48.700, 21.210, 48.706), RULES, SIZE)
        self.assertEqual(list(cover["typ"]), ["VODPLO"])


if __name__ == "__main__":
    unittest.main()
