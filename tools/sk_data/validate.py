# -*- coding: utf-8 -*-
"""Checks of a written region against what the plugin expects. Returns problems and a report."""

import json
import os

import geopandas as gpd
import numpy as np
import shapely
from shapely.strtree import STRtree

from tools.sk_data.crs import wgs84_to_sjtsk
from tools.sk_data.export import PLUGIN_DATA_VERSION, zabaged_dir

KOSICE = (21.2611, 48.7164)          # lon, lat
KOSICE_SJTSK = (-262580.66, -1240038.58)  # EPSG:4836 result


def validate(out_dir, region, size, classes, area_tolerance=0.02):
    """Return (problems, report). problems is empty when the output is usable by the plugin.

    region: the region polygon in EPSG:5514.
    """
    problems = []
    folder = zabaged_dir(out_dir)
    for name in ("sectors", "cesta", "lespru", "vodtok"):
        if not os.path.exists(os.path.join(folder, name + ".shp")):
            problems.append("missing %s.shp" % name)
    if problems:
        return problems, {}
    sectors = gpd.read_file(os.path.join(folder, "sectors.shp"))
    report = {"sectors": len(sectors)}

    if sectors.crs is None or sectors.crs.to_epsg() != 5514:
        problems.append("sectors.shp is not EPSG:5514")
    if "typ" not in sectors.columns:
        problems.append("sectors.shp has no 'typ' field")
    else:
        unknown = sorted(set(sectors["typ"]) - set(classes))
        if unknown:
            problems.append("unknown typ values: %s" % unknown)
    if not (sectors.geometry.geom_type == "Polygon").all():
        problems.append("sectors.shp has geometries that are not single polygons")
    invalid = int((~sectors.geometry.is_valid).sum())
    if invalid:
        problems.append("%d invalid sector geometries" % invalid)

    areas = sectors.geometry.area.to_numpy()
    total = float(areas.sum())
    report["total_ha"] = round(total / 1e4)
    report["region_ha"] = round(region.area / 1e4)
    report["area_ratio"] = round(total / region.area, 4)
    report["area_ha_percentiles_5_25_50_75_95"] = [round(float(np.percentile(areas, q)) / 1e4, 1) for q in (5, 25, 50, 75, 95)]
    in_range = (areas >= size.min_m2) & (areas <= size.max_m2 * 1.01)
    report["share_in_min_max"] = round(float(in_range.mean()), 3)
    report["share_of_area_in_min_max"] = round(float(areas[in_range].sum() / total), 3)
    report["sectors_over_max"] = int((areas > size.max_m2 * 1.01).sum())   # fragments absorbed after splitting
    report["sectors_under_tiny"] = int((areas < size.tiny_m2).sum())
    limit = size.max_m2 + size.tiny_m2                                      # an absorbed fragment adds less than tiny_ha
    too_big = int((areas > limit).sum())
    if too_big:
        problems.append("%d sectors are larger than %.1f ha" % (too_big, limit / 1e4))
    if abs(total / region.area - 1) > area_tolerance:
        problems.append("sector area %.0f ha differs from the region area %.0f ha by more than %.1f%%"
                        % (total / 1e4, region.area / 1e4, area_tolerance * 100))

    geoms = np.array(sectors.geometry.values, dtype=object)
    a_idx, b_idx = STRtree(geoms).query(geoms, predicate="intersects")
    keep = a_idx < b_idx
    overlap = shapely.area(shapely.intersection(geoms[a_idx[keep]], geoms[b_idx[keep]]))
    overlapping = int((overlap > 1.0).sum())
    if overlapping:
        problems.append("%d pairs of sectors overlap by more than 1 m2" % overlapping)

    by_typ = sectors.groupby("typ")["typ"].count().to_dict() if "typ" in sectors.columns else {}
    report["count_by_typ"] = {k: int(v) for k, v in sorted(by_typ.items())}
    if "typ" in sectors.columns:
        report["other_share_of_area"] = round(float(areas[(sectors["typ"] == "OTHER").to_numpy()].sum() / total), 3)

    try:
        with open(os.path.join(folder, "lastsectorid.txt")) as f:
            int(f.read())
    except (OSError, ValueError):
        problems.append("lastsectorid.txt is missing or not an integer")
    try:
        with open(os.path.join(out_dir, "metadata.json"), encoding="utf-8") as f:
            if json.load(f).get("version") != PLUGIN_DATA_VERSION:
                problems.append("metadata.json version is not %s" % PLUGIN_DATA_VERSION)
    except (OSError, ValueError):
        problems.append("metadata.json is missing or invalid")

    x, y = wgs84_to_sjtsk().transform(*KOSICE)
    if abs(x - KOSICE_SJTSK[0]) > 1.0 or abs(y - KOSICE_SJTSK[1]) > 1.0:
        problems.append("the WGS84 -> S-JTSK transformation does not give the Slovak result at Kosice (%.1f, %.1f)" % (x, y))
    return problems, report
