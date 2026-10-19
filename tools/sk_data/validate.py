# -*- coding: utf-8 -*-
"""Checks of a written region against what the plugin expects. Returns problems and a report."""

import json
import os
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.strtree import STRtree

from tools.sk_data.crs import wgs84_to_sjtsk
from tools.sk_data.export import LAST_SECTOR_ID, PLUGIN_DATA_VERSION, zabaged_dir

KOSICE = (21.2611, 48.7164)          # lon, lat
KOSICE_SJTSK = (-262580.66, -1240038.58)  # EPSG:4836 result

ID_PATTERN = re.compile(r"^[1-9][0-9]*$")
LABEL_PATTERN = re.compile(r"^[A-Z][0-9]+$")
LABEL_MIN_DISTANCE_M = 30000.0   # the same label may be used again only farther away than this (the grid gives 36 km)
CHUNK = 5000


def label_conflicts(labels, xy):
    """{label: number of pairs of sectors with that label closer than LABEL_MIN_DISTANCE_M}; only labels with pairs.

    labels: array of strings, xy: array (n, 2) of reference points in metres. Only labels used more than once are
    looked at, one label at a time, with a spatial index, so 110,000 sectors do not need all pairs.
    """
    labels = np.asarray(labels, dtype=object)
    xy = np.asarray(xy, dtype=float)
    values, inverse, counts = np.unique(labels.astype(str), return_inverse=True, return_counts=True)
    conflicts = {}
    for k in np.flatnonzero((counts > 1) & (values != "")):          # empty labels are a format problem, not a conflict
        points = shapely.points(xy[inverse == k])
        tree = STRtree(points)
        pairs = 0
        for start in range(0, len(points), CHUNK):
            a_idx, b_idx = tree.query(points[start:start + CHUNK], predicate="dwithin", distance=LABEL_MIN_DISTANCE_M)
            pairs += int((a_idx + start < b_idx).sum())
        if pairs:
            conflicts[str(values[k])] = pairs
    return conflicts


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

    _check_ids_and_labels(sectors, problems, report)
    if len(sectors) == 0:
        problems.append("sectors.shp has no sectors")      # the size statistics below need at least one
        return problems, report

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


def _strings(column):
    """The column as a Series of Python strings; null values (and anything that is not text) become ''."""
    return pd.Series([v if isinstance(v, str) else "" for v in column], index=column.index, dtype=object)


def _check_ids_and_labels(sectors, problems, report):
    """The fields the plugin's later steps need: a unique integer-string id below the split base, and a letter+number label."""
    for name in ("id", "label"):
        if name not in sectors.columns:
            problems.append("sectors.shp has no '%s' field" % name)
    if "id" in sectors.columns:
        ids = _strings(sectors["id"])
        duplicates = int(ids.duplicated().sum())
        if duplicates:
            problems.append("%d duplicate id values" % duplicates)
        valid = ids.map(lambda v: bool(ID_PATTERN.match(v)) and int(v) < LAST_SECTOR_ID)
        if not valid.all():
            problems.append("%d ids are not a positive integer below %d (examples: %s)"
                            % (int((~valid).sum()), LAST_SECTOR_ID, list(ids[~valid].head(3))))
        report["id_max"] = int(ids[valid].astype(int).max()) if valid.any() else 0
    if "label" in sectors.columns:
        labels = _strings(sectors["label"])
        bad = ~labels.map(lambda v: bool(LABEL_PATTERN.match(v)))
        if bad.any():
            problems.append("%d labels do not match one capital letter followed by digits (examples: %s)"
                            % (int(bad.sum()), list(labels[bad].head(3))))
        named = labels[labels != ""]                                        # empty labels are already a format problem
        report["labels"] = {"max_length": int(labels.str.len().max()) if len(labels) else 0,
                            "duplicated_labels": int((named.value_counts() > 1).sum())}
        if report["labels"]["duplicated_labels"]:
            reference = shapely.get_coordinates(shapely.point_on_surface(sectors.geometry.values))
            conflicts = label_conflicts(labels.to_numpy(), reference)
            if conflicts:
                examples = sorted(conflicts)[:3]
                problems.append("sectors with the same label are closer than %.0f m: %d labels, %d pairs (examples: %s)"
                                % (LABEL_MIN_DISTANCE_M, len(conflicts), sum(conflicts.values()), examples))
