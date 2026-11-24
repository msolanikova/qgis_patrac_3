import math
import os
import tempfile
import unittest

import geopandas as gpd
import numpy as np
from osgeo import gdal, osr
from shapely.geometry import MultiPolygon, Polygon, box

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

    def test_keeps_the_polygon_of_an_invalid_geometry_that_repairs_to_a_collection(self):
        # A ring that doubles back along a line (a spike) is invalid; shapely repairs it to a polygon PLUS a stray
        # line, a GeometryCollection. The forest must not be dropped because of the line (real case: an 8,000 ha
        # natural=wood relation near Ostrov, 62 such OSM polygons in Kosicky kraj).
        spike = Polygon([(0, 0), (200, 0), (200, 200), (0, 200), (0, 0), (-40, 0), (0, 0)])
        self.assertFalse(spike.is_valid)
        polygons = gpd.GeoDataFrame({"tags": [{"natural": "wood"}]}, geometry=[MultiPolygon([spike])], crs=5514)
        cover = osm_cover(polygons, RULES, SIZE)
        self.assertEqual(list(cover["typ"]), ["LPSTROM"])
        self.assertEqual(cover.geometry.iloc[0].geom_type, "Polygon")
        self.assertAlmostEqual(cover.geometry.iloc[0].area, 40000.0)  # the stray line adds nothing

    def test_a_geometry_with_no_area_after_repair_is_dropped(self):
        line_only = Polygon([(0, 0), (100, 0), (200, 0), (0, 0)])      # all points on one line: no area
        polygons = gpd.GeoDataFrame({"tags": [{"natural": "wood"}]}, geometry=[line_only], crs=5514)
        self.assertEqual(len(osm_cover(polygons, RULES, SIZE)), 0)


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
        array[10:17, 10:17] = 30                          # a 7 x 7 pixel grass speckle (about 4000 m2: above min_cover_m2, below the sieve threshold)
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
