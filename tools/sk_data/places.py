# -*- coding: utf-8 -*-
"""Municipality list in the format of the plugin's ui/*.csv: x;y;code;name;okres code;okres;REGION."""

import csv

import shapely
from shapely.strtree import STRtree

from tools.sk_data.crs import wgs84_to_sjtsk

PLACE_TYPES = {"city", "town", "village"}
MUNICIPALITY_LEVELS = ("8", "5")   # level 5 = the two cities with districts, Bratislava and Kosice
DISTRICT_LEVEL = "6"


def admin_areas(polygons, levels):
    """Name + geometry of the administrative areas of one admin_level or of several (polygons: GeoDataFrame with 'tags')."""
    levels = {levels} if isinstance(levels, str) else set(levels)
    keep = [t.get("boundary") == "administrative" and t.get("admin_level") in levels and bool(t.get("name"))
            for t in polygons["tags"]]
    selected = polygons[keep]
    out = selected[["geometry"]].copy()
    out["name"] = [t["name"] for t in selected["tags"]]
    return out.reset_index(drop=True)


def build_places(municipalities, districts, points, region, region_code, transformer=None):
    """Rows (x, y, 0, name, 0, district, REGION) in S-JTSK for the municipalities inside the region.

    All inputs are in EPSG:4326. The position is the OSM place node (city, town or village) inside the
    municipality, preferring one with the same name; without one, a point inside the boundary.
    The two zero columns are codes the plugin does not read.
    """
    transformer = transformer or wgs84_to_sjtsk()
    nodes = [(g, t["name"]) for g, t in zip(points.geometry, points["tags"])
             if t.get("place") in PLACE_TYPES and t.get("name")]
    node_tree = STRtree([g for g, _ in nodes]) if nodes else None
    district_tree = STRtree(list(districts.geometry)) if len(districts) else None
    rows = []
    for name, polygon in zip(municipalities["name"], municipalities.geometry):
        representative = polygon.representative_point()
        if not shapely.contains(region, representative):
            continue
        inside = [nodes[i] for i in node_tree.query(polygon, predicate="contains")] if node_tree else []
        same_name = [g for g, n in inside if n == name]
        centre = (same_name or [g for g, _ in inside] or [representative])[0]
        district = ""
        if district_tree is not None:
            hits = district_tree.query(centre, predicate="within")
            if len(hits):
                district = districts["name"].iloc[int(hits[0])]
        x, y = transformer.transform(centre.x, centre.y)
        rows.append((int(round(x)), int(round(y)), 0, name, 0, district, region_code.upper()))
    rows.sort(key=lambda r: (r[3], r[5]))
    return rows


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter=";", lineterminator="\n").writerows(rows)
