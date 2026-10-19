# -*- coding: utf-8 -*-
"""Line layers from OSM: the lines that bound sectors, and the cesta / lespru / vodtok reference layers."""

import geopandas as gpd
import numpy as np
import shapely
from shapely.strtree import STRtree

BARRIER_HIGHWAYS = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
                    "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street"}
BARRIER_RAILWAYS = {"rail", "light_rail"}
BARRIER_WATERWAYS = {"river", "stream", "canal"}
TRACK_HIGHWAYS = {"track", "path", "bridleway"}
OUTPUT_WATERWAYS = {"river", "stream", "canal", "drain", "ditch"}
FOREST_TYPES = ("LPSTROM", "LPKROV")
TUNNEL_VALUES = {"yes", "culvert", "building_passage"}


def _is_tunnel(tags):
    return tags.get("tunnel") in TUNNEL_VALUES


def barrier_lines(lines):
    """Geometries of the roads, railways and waterways that bound sectors (lines: GeoDataFrame with 'tags')."""
    keep = np.array([
        (t.get("highway") in BARRIER_HIGHWAYS or t.get("railway") in BARRIER_RAILWAYS
         or t.get("waterway") in BARRIER_WATERWAYS) and not _is_tunnel(t)
        for t in lines["tags"]], dtype=bool)
    return list(lines.geometry.values[keep])


def output_layers(lines, sectors, region):
    """The cesta (roads and paths), lespru (tracks in forest) and vodtok (streams) layers for the region.

    lines: GeoDataFrame with 'tags' (EPSG:5514); sectors: GeoDataFrame with 'typ'; region: polygon.
    Lines that touch the region are kept whole (the plugin clips by extent itself).
    """
    lines = lines[shapely.intersects(lines.geometry.values, region)]
    tags = list(lines["tags"])
    frame = gpd.GeoDataFrame({"highway": [t.get("highway") for t in tags],
                              "waterway": [t.get("waterway") for t in tags],
                              "name": [t.get("name") for t in tags]},
                             geometry=lines.geometry.values, crs=5514)
    tunnel = np.array([_is_tunnel(t) for t in tags], dtype=bool)
    is_road = frame["highway"].notna().to_numpy() & ~tunnel
    is_track = frame["highway"].isin(TRACK_HIGHWAYS).to_numpy()
    in_forest = np.zeros(len(frame), dtype=bool)
    forest = sectors[sectors["typ"].isin(FOREST_TYPES)]
    if len(forest) and is_track.any():
        midpoints = shapely.line_interpolate_point(frame.geometry.values, 0.5, normalized=True)
        hits = STRtree(list(forest.geometry)).query(midpoints, predicate="within")[0]
        in_forest[np.unique(hits)] = True
    in_forest_track = is_road & is_track & in_forest
    return {
        "cesta": frame[is_road & ~in_forest_track][["highway", "name", "geometry"]].reset_index(drop=True),
        "lespru": frame[in_forest_track][["highway", "name", "geometry"]].reset_index(drop=True),
        "vodtok": frame[frame["waterway"].isin(OUTPUT_WATERWAYS).to_numpy() & ~tunnel][["waterway", "name", "geometry"]].reset_index(drop=True),
    }
