# -*- coding: utf-8 -*-
"""Land-cover polygons with a sector type: OSM polygons (precise) and ESA WorldCover (complete, 10 m)."""

import logging
import math
import os
import tempfile

import geopandas as gpd
import shapely
from osgeo import gdal, ogr, osr

from tools.sk_data.crs import project_geometries
from tools.sk_data.rules import osm_typ

gdal.UseExceptions()
log = logging.getLogger("sk_data")


def osm_cover(polygons, rules, size):
    """OSM polygons (EPSG:5514, with a 'tags' column) that map to a sector type and are big enough to matter."""
    typs = [osm_typ(rules, tags) for tags in polygons["tags"]]
    gdf = gpd.GeoDataFrame({"typ": typs}, geometry=shapely.make_valid(polygons.geometry.values), crs=5514)
    gdf = gdf[gdf["typ"].notna() & gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
    return gdf[gdf.geometry.area >= size.min_cover_m2].reset_index(drop=True)


def _pixel_area_m2(geotransform, lat):
    """Approximate area of one pixel of a lon/lat raster at latitude lat."""
    width_m = abs(geotransform[1]) * 111320.0 * math.cos(math.radians(lat))
    height_m = abs(geotransform[5]) * 110574.0
    return width_m * height_m


def worldcover_cover(tif_paths, bbox, rules, size, sieve_ha=0.5):
    """ESA WorldCover polygons (EPSG:5514) with a sector type, for the lon/lat bbox.

    Raster regions smaller than sieve_ha are merged into their neighbours, then the classes are
    polygonized. The polygons keep their exact pixel edges, so neighbouring polygons share borders.
    """
    vrt = gdal.BuildVRT("", [str(p) for p in tif_paths])
    clipped = gdal.Warp("", vrt, outputBounds=tuple(bbox), format="MEM", resampleAlg="near")
    gt = clipped.GetGeoTransform()
    pixels = max(1, int(round(sieve_ha * 1e4 / _pixel_area_m2(gt, (bbox[1] + bbox[3]) / 2))))
    log.info("WorldCover: %d x %d pixels, sieve threshold %d pixels", clipped.RasterXSize, clipped.RasterYSize, pixels)
    sieved = gdal.GetDriverByName("MEM").Create("", clipped.RasterXSize, clipped.RasterYSize, 1, gdal.GDT_Byte)
    sieved.SetGeoTransform(gt)
    sieved.SetProjection(clipped.GetProjection())
    gdal.SieveFilter(clipped.GetRasterBand(1), None, sieved.GetRasterBand(1), pixels, 4)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "wc.gpkg")
        ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        layer = ds.CreateLayer("wc", srs, ogr.wkbPolygon)
        layer.CreateField(ogr.FieldDefn("cls", ogr.OFTInteger))
        gdal.Polygonize(sieved.GetRasterBand(1), None, layer, 0, ["8CONNECTED=NO"])
        ds = layer = None  # flush
        gdf = gpd.read_file(path)
    typs = gdf["cls"].map(rules.worldcover)
    gdf = gdf[typs.notna()].copy()
    out = gpd.GeoDataFrame({"typ": typs[typs.notna()].to_numpy()},
                           geometry=project_geometries(gdf.geometry.values), crs=5514)
    return out[out.geometry.area >= size.min_cover_m2].reset_index(drop=True)
