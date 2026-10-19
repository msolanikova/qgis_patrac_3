# -*- coding: utf-8 -*-
"""Read OpenStreetMap data with GDAL's OSM driver: region boundary, lines, polygons and place nodes."""

import logging
import os
import re

import geopandas as gpd
from osgeo import gdal

gdal.UseExceptions()
log = logging.getLogger("sk_data")

_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')
_SKIP_COLUMNS = {"geometry", "other_tags", "osm_id", "osm_way_id", "z_order"}
BBOX_PAD_DEG = 0.02


def parse_tags(other_tags):
    """Dict from the hstore text GDAL puts in the other_tags column."""
    if not isinstance(other_tags, str):
        return {}
    unescape = lambda s: s.replace('\\"', '"').replace("\\\\", "\\")
    return {unescape(k): unescape(v) for k, v in _PAIR.findall(other_tags)}


def with_tags(gdf):
    """Copy of gdf with a 'tags' column: all OSM tags of a feature (columns and other_tags) as one dict."""
    columns = [c for c in gdf.columns if c not in _SKIP_COLUMNS]
    tags = []
    for row in gdf[columns + ["other_tags"]].to_dict("records"):
        t = parse_tags(row.pop("other_tags"))
        t.update({k: v for k, v in row.items() if isinstance(v, str)})
        tags.append(t)
    out = gdf[["geometry"]].copy()
    out["tags"] = tags
    return out


def _translate(dest, pbf, layer, **kwargs):
    if os.path.exists(dest):
        os.remove(dest)
    gdal.PushErrorHandler("CPLQuietErrorHandler")  # cut-off relations at the border warn about unclosed rings
    try:
        gdal.VectorTranslate(dest, pbf, format="GPKG", layers=[layer],
                             geometryType="PROMOTE_TO_MULTI" if layer == "multipolygons" else None, **kwargs)
    finally:
        gdal.PopErrorHandler()
    return dest


def region_boundary(pbf, osm_name, work_dir, admin_level=4):
    """Boundary of an administrative relation as a one-row GeoDataFrame (EPSG:4326)."""
    os.makedirs(work_dir, exist_ok=True)
    where = "boundary='administrative' AND admin_level='%d' AND name='%s'" % (admin_level, osm_name.replace("'", "''"))
    dest = _translate(os.path.join(work_dir, "boundary.gpkg"), pbf, "multipolygons", where=where)
    gdf = gpd.read_file(dest)
    if gdf.empty:
        raise ValueError("no administrative boundary named %r (admin_level=%d) in %s" % (osm_name, admin_level, pbf))
    return gdf.iloc[[0]][["name", "geometry"]].reset_index(drop=True)


def bbox_of(boundary, pad=BBOX_PAD_DEG):
    minx, miny, maxx, maxy = boundary.total_bounds
    return (minx - pad, miny - pad, maxx + pad, maxy + pad)


def extract(pbf, bbox, out_dir):
    """Cut lines, multipolygons, points and administrative areas inside bbox (lon/lat) out of the OSM file.

    Returns {'lines', 'polygons', 'points'} -> GeoPackage paths in out_dir.
    """
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for name, layer in (("lines", "lines"), ("polygons", "multipolygons"), ("points", "points")):
        log.info("extracting OSM %s", layer)
        paths[name] = _translate(os.path.join(out_dir, name + ".gpkg"), pbf, layer, spatFilter=tuple(bbox))
    return paths


def read_lines(path):
    """OSM lines as a GeoDataFrame with a 'tags' column (EPSG:4326)."""
    return with_tags(gpd.read_file(path))


def read_polygons(path):
    """OSM polygons split into (everything except buildings with a 'tags' column, building geometries)."""
    gdf = gpd.read_file(path)
    is_building = gdf["building"].notna() if "building" in gdf.columns else gdf.index.to_series().map(lambda _: False)
    buildings = gdf.loc[is_building, "geometry"].reset_index(drop=True)
    return with_tags(gdf.loc[~is_building]), buildings


def read_points(path):
    """OSM nodes with tags as a GeoDataFrame with a 'tags' column (EPSG:4326)."""
    return with_tags(gpd.read_file(path))
