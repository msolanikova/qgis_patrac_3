# -*- coding: utf-8 -*-
"""Cut the sectors of a built region into the tiled "service bundle" (format v1) read by the SAR Planner.

    <out>/<region>/<version>/manifest.json
    <out>/<region>/<version>/tiles/<tx>_<ty>.jsonl.gz

A sector lives in the 10 km tile of its centroid in EPSG:5514 (tx = floor(cx / 10000), ty likewise; the
coordinates are negative in Slovakia). A tile file is gzip, UTF-8, one JSON object per line with
id, label, typ, cls (plugin class 1..10), area_ha, wkt (the polygon in EPSG:5514, 2 decimals) and
outline (its exterior ring in WGS84, closed, 6 decimals). Only non-empty tiles are written. The manifest's
coverage_wkt is the area the sectors cover (EPSG:5514, whole metres).

A bundle built with roads also has

    <out>/<region>/<version>/roads/<tx>_<ty>.jsonl.gz

A road piece lives in the 10 km tile of the midpoint of its line (same tile numbers as the sectors). A road tile
file is gzip, UTF-8, one JSON object per line with id ("r1", "r2", ...; unique in the bundle), name (or null),
highway, tracktype (or null), surface (or null), worse (true or false), length_m (one decimal), wkt (the line in
EPSG:5514, 2 decimals) and outline (the vertices of the line in WGS84, 6 decimals, at least 2 points). Only non-empty
tiles are written. The manifest then has "roads": {"count": N, "tiles": {"<tx>_<ty>": n, ...}}; a bundle without
roads has neither the key nor the folder. Roads ship in a new version, not into one that cases already use.
"""

import gzip
import json
import math
import os
import shutil
import tempfile

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from tools.sk_data.config import region_dir
from tools.sk_data.crs import OPERATION_NAME, sjtsk_to_wgs84
from tools.sk_data.export import zabaged_dir
from tools.sk_data.pipeline import _replace
from tools.sk_data.rules import load_rules

FORMAT = 1
TILE_M = 10000
CRS = "EPSG:5514"
_POLYGON = 3   # shapely.get_type_id of a Polygon
_LINESTRING = 1   # shapely.get_type_id of a LineString
_ROAD_FIELDS = ["id", "name", "highway", "tracktype", "surface", "worse", "length_m"]


def _check(sectors, classes):
    """Return the geometries as an array after checking crs, geometry types and typ; raise ValueError otherwise."""
    if sectors.crs is None or sectors.crs.to_epsg() != 5514:
        raise ValueError("the sectors must be in EPSG:5514, got %s" % sectors.crs)
    geoms = sectors.geometry.to_numpy()
    for i in np.flatnonzero((shapely.get_type_id(geoms) != _POLYGON) | shapely.is_empty(geoms)):
        raise ValueError("sector %s is not a single non-empty Polygon" % sectors["id"].iloc[i])
    unknown = sorted(set(sectors["typ"]) - set(classes))
    if unknown:
        raise ValueError("unknown sector type(s) %s; known: %s" % (", ".join(map(str, unknown)), ", ".join(sorted(classes))))
    return geoms


def _outlines(geoms):
    """Exterior rings of the polygons in WGS84 (6 decimals) as lists of [lon, lat]; all vertices are transformed at once."""
    coords, owner = shapely.get_coordinates(shapely.get_exterior_ring(geoms), return_index=True)
    lon, lat = sjtsk_to_wgs84().transform(coords[:, 0], coords[:, 1])
    points = np.round(np.column_stack([lon, lat]), 6)
    edges = np.searchsorted(owner, np.arange(len(geoms) + 1))
    return [points[edges[i]:edges[i + 1]].tolist() for i in range(len(geoms))]


def _tile_groups(geoms):
    """{(tx, ty): [row, ...]} in input order, from the centroids."""
    centroids = shapely.centroid(geoms)
    tx = np.floor(shapely.get_x(centroids) / TILE_M).astype(int)
    ty = np.floor(shapely.get_y(centroids) / TILE_M).astype(int)
    groups = {}
    for row, key in enumerate(zip(tx.tolist(), ty.tolist())):
        groups.setdefault(key, []).append(row)
    return groups


def _wkts(geoms, ids):
    """WKT of the polygons on a 1 cm grid, which is how the coordinates are written (2 decimals).

    Plain rounding would turn about 6 % of the sectors into self-intersecting rings (cm-wide spikes and notches), so the
    polygons are snapped with set_precision, which keeps them valid. A hairline neck can make that split a polygon in
    two (about 20 sectors in Kosicky kraj); those are snapped to 0.1 mm instead and written with 4 decimals.
    """
    snapped = shapely.set_precision(geoms, 0.01)
    wkts = shapely.to_wkt(snapped, rounding_precision=2)
    for i in np.flatnonzero(shapely.get_type_id(snapped) != _POLYGON):
        finer = shapely.set_precision(geoms[i], 0.0001)
        if shapely.get_type_id(finer) != _POLYGON:
            raise ValueError("sector %s cannot be written as a single valid polygon" % ids[i])
        wkts[i] = shapely.to_wkt(finer, rounding_precision=4)
    return wkts


def _coverage_wkt(geoms, groups, close_m=100.0):
    """WKT (EPSG:5514, whole metres) of the area the sectors cover: the union of all polygons, closed with a buffer
    of close_m and simplified by close_m, so a reader can tell where the region's data ends.

    The union is built per tile first and then over the tile unions, which keeps it fast for 100k polygons. The
    result is snapped to a 1 m grid with set_precision (which keeps it valid), so it can be written with 0 decimals.
    """
    parts = [shapely.union_all(geoms[rows]) for rows in groups.values()]
    closed = shapely.union_all(parts).buffer(close_m).simplify(close_m, preserve_topology=True)
    coverage = shapely.set_precision(closed, 1.0)
    if not coverage.is_valid:
        coverage = shapely.set_precision(closed.buffer(0), 1.0)
    if coverage.is_empty or not coverage.is_valid or coverage.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("the coverage of the sectors is not a valid polygon (%s)" % coverage.geom_type)
    return shapely.to_wkt(coverage, rounding_precision=0)


def _write_tiles(folder, sectors, geoms, classes, groups):
    areas = np.round(shapely.area(geoms) / 10000.0, 2).tolist()
    outlines = _outlines(geoms)
    ids, labels, types = (sectors[c].astype(str).tolist() for c in ("id", "label", "typ"))
    wkts = _wkts(geoms, ids)
    for (tx, ty), rows in groups.items():
        with gzip.open(os.path.join(folder, "%d_%d.jsonl.gz" % (tx, ty)), "wt", encoding="utf-8") as f:
            for i in rows:
                f.write(json.dumps({"id": ids[i], "label": labels[i], "typ": types[i], "cls": int(classes[types[i]]),
                                    "area_ha": areas[i], "wkt": wkts[i], "outline": outlines[i]},
                                   ensure_ascii=False) + "\n")


def _snap_lines(lines, ids):
    """The lines on a 1 cm grid (set_precision, like the sector polygons), which is how the coordinates are written.

    A line that snapping turns into something else than one LineString is rounded to 2 decimals instead; a line
    that still has fewer than 2 distinct points raises ValueError naming the road.
    """
    snapped = shapely.set_precision(lines, 0.01)
    for i in np.flatnonzero(shapely.get_type_id(snapped) != _LINESTRING):
        rounded = np.round(shapely.get_coordinates(lines[i]), 2)
        if len(np.unique(rounded, axis=0)) < 2:
            raise ValueError("road %s has fewer than 2 distinct points at 2 decimals" % ids[i])
        snapped[i] = shapely.linestrings(rounded)
    for i in np.flatnonzero(shapely.is_empty(snapped) | (shapely.get_num_coordinates(snapped) < 2)):
        raise ValueError("road %s has fewer than 2 distinct points at 2 decimals" % ids[i])
    return snapped


def _check_roads(roads):
    """Return the lines of the road pieces, snapped to 2 decimals, after the checks; raise ValueError naming the road."""
    if roads.crs is None or roads.crs.to_epsg() != 5514:
        raise ValueError("the roads must be in EPSG:5514, got %s" % roads.crs)
    missing = [c for c in _ROAD_FIELDS if c not in roads.columns]
    if missing:
        raise ValueError("the roads lack the column(s) %s" % ", ".join(missing))
    ids = roads["id"].tolist()
    seen = set()
    for road_id in ids:
        if not isinstance(road_id, str) or not road_id.startswith("r") or len(road_id) < 2:
            raise ValueError("road id %r does not start with r followed by something" % (road_id,))
        if road_id in seen:
            raise ValueError("road id %s is not unique" % road_id)
        seen.add(road_id)
    lines = roads.geometry.to_numpy()
    for i in np.flatnonzero((shapely.get_type_id(lines) != _LINESTRING) | shapely.is_empty(lines)):
        raise ValueError("road %s is not a single non-empty LineString" % ids[i])
    for road_id, worse, highway, length in zip(ids, roads["worse"].tolist(), roads["highway"].tolist(),
                                               roads["length_m"].tolist()):
        if not isinstance(worse, (bool, np.bool_)):
            raise ValueError("road %s has worse=%r, which is not a boolean" % (road_id, worse))
        if not isinstance(highway, str) or not highway:
            raise ValueError("road %s has highway=%r, which is not a non-empty string" % (road_id, highway))
        if (isinstance(length, (bool, np.bool_)) or not isinstance(length, (int, float, np.integer, np.floating))
                or not math.isfinite(length) or length < 0):
            raise ValueError("road %s has length_m=%r, which is not a finite number >= 0" % (road_id, length))
    return _snap_lines(lines, ids)


def _line_tile_groups(lines):
    """{(tx, ty): [row, ...]} in input order, from the midpoints of the lines."""
    mid = shapely.line_interpolate_point(lines, 0.5, normalized=True)
    tx = np.floor(shapely.get_x(mid) / TILE_M).astype(int)
    ty = np.floor(shapely.get_y(mid) / TILE_M).astype(int)
    groups = {}
    for row, key in enumerate(zip(tx.tolist(), ty.tolist())):
        groups.setdefault(key, []).append(row)
    return groups


def _line_outlines(lines):
    """The vertices of the lines in WGS84 (6 decimals) as lists of [lon, lat]; all vertices are transformed at once."""
    coords, owner = shapely.get_coordinates(lines, return_index=True)
    lon, lat = sjtsk_to_wgs84().transform(coords[:, 0], coords[:, 1])
    points = np.round(np.column_stack([lon, lat]), 6)
    edges = np.searchsorted(owner, np.arange(len(lines) + 1))
    return [points[edges[i]:edges[i + 1]].tolist() for i in range(len(lines))]


def _write_road_tiles(folder, roads, lines, groups):
    outlines = _line_outlines(lines)
    wkts = shapely.to_wkt(lines, rounding_precision=2)
    ids, highways = (roads[c].tolist() for c in ("id", "highway"))
    names, tracktypes, surfaces = ([None if pd.isna(v) else str(v) for v in roads[c].tolist()]
                                   for c in ("name", "tracktype", "surface"))
    worse = [bool(v) for v in roads["worse"].tolist()]
    lengths = [round(float(v), 1) for v in roads["length_m"].tolist()]
    for (tx, ty), rows in groups.items():
        with gzip.open(os.path.join(folder, "%d_%d.jsonl.gz" % (tx, ty)), "wt", encoding="utf-8") as f:
            for i in rows:
                f.write(json.dumps({"id": ids[i], "name": names[i], "highway": highways[i], "tracktype": tracktypes[i],
                                    "surface": surfaces[i], "worse": worse[i], "length_m": lengths[i], "wkt": wkts[i],
                                    "outline": outlines[i]}, ensure_ascii=False, allow_nan=False) + "\n")


def write_bundle(sectors, out_dir, region, version, classes, attribution, sources, overwrite=False, roads=None,
                 roads_info=None):
    """Write the bundle of a GeoDataFrame (EPSG:5514; fields id, label, typ) to <out_dir>/<region>/<version>/; return the manifest.

    typ is mapped to the plugin class with classes ({typ: 1..10}). The data is written to a sibling staging folder
    "<version>.partial-*" and moved into place after the manifest, the last file, is written; so the version
    folder is either complete or absent, and a failed run leaves an existing version untouched. An existing version
    raises FileExistsError unless overwrite is true. All checks run before anything is written.

    roads is None (no roads in the bundle) or the GeoDataFrame of road pieces (EPSG:5514; fields id, name, highway,
    tracktype, surface, worse, length_m; see roads.road_pieces), possibly empty. It adds the roads/ tiles and the
    "roads" entry of the manifest; roads_info (a dict) is merged into that entry, and ignored without roads.
    """
    version_dir = os.path.abspath(os.path.join(out_dir, region, version))
    if os.path.lexists(version_dir) and not overwrite:
        raise FileExistsError("%s already exists; pass --overwrite to replace it or choose another version" % version_dir)
    geoms = _check(sectors, classes)
    groups = _tile_groups(geoms)
    if roads is not None:
        road_lines = _check_roads(roads)
        road_groups = _line_tile_groups(road_lines)
        entry = {"count": len(roads), "tiles": {"%d_%d" % key: len(rows) for key, rows in sorted(road_groups.items())}}
        for key, value in (roads_info or {}).items():
            if key in entry:
                raise ValueError("roads_info cannot replace %r" % key)
            entry[key] = value
    manifest = {"format": FORMAT, "region": region, "version": version, "crs": CRS, "tile_m": TILE_M,
                "sector_count": len(sectors), "tiles": {"%d_%d" % key: len(rows) for key, rows in sorted(groups.items())},
                "transform": OPERATION_NAME, "sources": sources, "attribution": attribution,
                "coverage_wkt": _coverage_wkt(geoms, groups)}
    if roads is not None:
        manifest["roads"] = entry
    parent = os.path.dirname(version_dir)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=version + ".partial-", dir=parent)
    umask = os.umask(0)
    os.umask(umask)
    os.chmod(staging, 0o777 & ~umask)                 # mkdtemp makes it private; the data should look like a normal folder
    try:
        os.mkdir(os.path.join(staging, "tiles"))
        _write_tiles(os.path.join(staging, "tiles"), sectors, geoms, classes, groups)
        if roads is not None and road_groups:
            os.mkdir(os.path.join(staging, "roads"))
            _write_road_tiles(os.path.join(staging, "roads"), roads, road_lines, road_groups)
        with open(os.path.join(staging, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1, ensure_ascii=False)
        _replace(version_dir, staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def sources_from_metadata(metadata):
    """[{"name", "detail"}] from the "sources" of a region's metadata.json: the name of the source and its URL."""
    return [{"name": name, "detail": info.get("url", "")} for name, info in (metadata.get("sources") or {}).items()]


def bundle_region(root, region, version, out_dir, overwrite=False):
    """Write the bundle of the built region <root>/kraje/<region> to <out_dir>/<region>/<version>/; return the manifest."""
    folder = region_dir(root, region)
    sectors = gpd.read_file(os.path.join(zabaged_dir(folder), "sectors.shp"))
    with open(os.path.join(folder, "metadata.json"), encoding="utf-8") as f:
        sources = sources_from_metadata(json.load(f))
    with open(os.path.join(folder, "ATTRIBUTION.txt"), encoding="utf-8") as f:
        attribution = f.read()
    return write_bundle(sectors, out_dir, region, version, load_rules().classes, attribution, sources, overwrite=overwrite)
