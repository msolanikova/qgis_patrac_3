# -*- coding: utf-8 -*-
"""Cut the sectors of a built region into the tiled "service bundle" (format v1) read by the SAR Planner.

    <out>/<region>/<version>/manifest.json
    <out>/<region>/<version>/tiles/<tx>_<ty>.jsonl.gz

A sector lives in the 10 km tile of its centroid in EPSG:5514 (tx = floor(cx / 10000), ty likewise; the
coordinates are negative in Slovakia). A tile file is gzip, UTF-8, one JSON object per line with
id, label, typ, cls (plugin class 1..10), area_ha, wkt (the polygon in EPSG:5514, 2 decimals) and
outline (its exterior ring in WGS84, closed, 6 decimals). Only non-empty tiles are written. The manifest's
coverage_wkt is the area the sectors cover (EPSG:5514, whole metres).
"""

import gzip
import json
import os
import shutil
import tempfile

import geopandas as gpd
import numpy as np
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


def write_bundle(sectors, out_dir, region, version, classes, attribution, sources, overwrite=False):
    """Write the bundle of a GeoDataFrame (EPSG:5514; fields id, label, typ) to <out_dir>/<region>/<version>/; return the manifest.

    typ is mapped to the plugin class with classes ({typ: 1..10}). The data is written to a sibling staging folder
    "<version>.partial-*" and moved into place after the manifest, the last file, is written; so the version
    folder is either complete or absent, and a failed run leaves an existing version untouched. An existing version
    raises FileExistsError unless overwrite is true. All checks run before anything is written.
    """
    version_dir = os.path.abspath(os.path.join(out_dir, region, version))
    if os.path.lexists(version_dir) and not overwrite:
        raise FileExistsError("%s already exists; pass --overwrite to replace it or choose another version" % version_dir)
    geoms = _check(sectors, classes)
    groups = _tile_groups(geoms)
    manifest = {"format": FORMAT, "region": region, "version": version, "crs": CRS, "tile_m": TILE_M,
                "sector_count": len(sectors), "tiles": {"%d_%d" % key: len(rows) for key, rows in sorted(groups.items())},
                "transform": OPERATION_NAME, "sources": sources, "attribution": attribution,
                "coverage_wkt": _coverage_wkt(geoms, groups)}
    parent = os.path.dirname(version_dir)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=version + ".partial-", dir=parent)
    umask = os.umask(0)
    os.umask(umask)
    os.chmod(staging, 0o777 & ~umask)                 # mkdtemp makes it private; the data should look like a normal folder
    try:
        os.mkdir(os.path.join(staging, "tiles"))
        _write_tiles(os.path.join(staging, "tiles"), sectors, geoms, classes, groups)
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
