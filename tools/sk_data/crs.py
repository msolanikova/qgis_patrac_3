# -*- coding: utf-8 -*-
"""WGS84 -> S-JTSK (EPSG:5514) with the Slovak transformation pinned.

PROJ offers several operations for this pair. EPSG:4836 "S-JTSK to WGS 84 (4)" is the one defined for
Slovakia (1 m); the Czechoslovak fallback "(3)" is about 10 m away at Kosice and the Czech ones "(1)" and
"(5)" do not cover eastern Slovakia. Pinning it makes the output independent of PROJ's choice.
"""

import geopandas as gpd
import numpy as np
import shapely
from pyproj.transformer import TransformerGroup

OPERATION_NAME = "S-JTSK to WGS 84 (4)"
_cache = {}


def wgs84_to_sjtsk():
    """pyproj Transformer EPSG:4326 -> EPSG:5514 (lon, lat in; x, y out) using the Slovak operation."""
    if "t" not in _cache:
        for transformer in TransformerGroup(4326, 5514, always_xy=True).transformers:
            if OPERATION_NAME in transformer.description:
                _cache["t"] = transformer
                break
        else:
            raise RuntimeError("PROJ has no operation named %r; check the PROJ database of this QGIS" % OPERATION_NAME)
    return _cache["t"]


def project_geometries(geoms, transformer=None):
    """Transform an array-like of WGS84 shapely geometries to EPSG:5514."""
    transformer = transformer or wgs84_to_sjtsk()

    def apply(coords):
        x, y = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(np.asarray(list(geoms), dtype=object), apply)


def to_sjtsk(gdf):
    """Copy of a WGS84 GeoDataFrame with geometries in EPSG:5514."""
    geoms = project_geometries(gdf.geometry.values)
    return gpd.GeoDataFrame(gdf.drop(columns=gdf.geometry.name), geometry=geoms, crs=5514)
