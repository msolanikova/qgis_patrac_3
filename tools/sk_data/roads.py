# -*- coding: utf-8 -*-
"""Road pieces from OSM lines: which ways count as roads or paths for the service bundle, and what they are called."""

import math

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.ops import substring

from tools.sk_data.layers import _is_tunnel

INCLUDED_HIGHWAYS = frozenset({"track", "path", "bridleway", "service", "unclassified", "residential",
                               "living_street", "tertiary", "cycleway", "footway"})
WORSE_HIGHWAYS = frozenset({"track", "path", "bridleway"})
UNPAVED_SURFACES = frozenset({"unpaved", "compacted", "fine_gravel", "gravel", "pebblestone", "dirt", "earth",
                              "ground", "grass", "mud", "sand", "woodchips", "clay", "rock", "ice", "snow",
                              "salt"})
EXCLUDED_FOOTWAYS = frozenset({"sidewalk", "crossing"})
EXCLUDED_SERVICES = frozenset({"parking_aisle", "driveway", "drive-through", "emergency_access"})
EXCLUDED_ACCESS = frozenset({"no", "private"})
MAX_PIECE_M = 5000.0
MIN_PIECE_M = 30.0
PIECE_COLUMNS = ["id", "name", "highway", "tracktype", "surface", "worse", "length_m", "geometry"]
_ATTRIBUTES = ["name", "highway", "tracktype", "surface", "worse"]
_VERTEX_DECIMALS = 3  # vertices closer than 1 mm are the same OSM node
_MIDPOINT_DECIMALS = 2


def classify(tags):
    """None when the way is not a road piece, otherwise the 'worse' flag (True: track, path or unpaved surface)."""
    highway = tags.get("highway")
    if highway not in INCLUDED_HIGHWAYS:
        return None
    if (_is_tunnel(tags) or tags.get("footway") in EXCLUDED_FOOTWAYS
            or tags.get("service") in EXCLUDED_SERVICES or tags.get("access") in EXCLUDED_ACCESS):
        return None
    surfaces = {part.strip() for part in (tags.get("surface") or "").split(";")}
    return highway in WORSE_HIGHWAYS or bool(surfaces & UNPAVED_SURFACES)


def display_name(tags):
    """The name shown for a way: its name, else its ref, else None."""
    return tags.get("name") or tags.get("ref") or None


def _empty_pieces():
    columns = {"id": pd.Series([], dtype=object), "name": pd.Series([], dtype=object),
               "highway": pd.Series([], dtype=object), "tracktype": pd.Series([], dtype=object),
               "surface": pd.Series([], dtype=object), "worse": pd.Series([], dtype=bool),
               "length_m": pd.Series([], dtype=float)}
    return gpd.GeoDataFrame(columns, geometry=gpd.GeoSeries([], crs=5514), crs=5514)


def _orient(geoms):
    """Lines reversed where needed so that the first vertex is not after the last in (x, y) order."""
    first = shapely.get_coordinates(shapely.get_point(geoms, 0))
    last = shapely.get_coordinates(shapely.get_point(geoms, -1))
    flip = (first[:, 0] > last[:, 0]) | ((first[:, 0] == last[:, 0]) & (first[:, 1] > last[:, 1]))
    geoms = geoms.copy()
    geoms[flip] = shapely.reverse(geoms[flip])
    return geoms


def _components(n, pairs):
    """Component label (0..n-1 space, not compact) of each of n items joined by the given index pairs."""
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in pairs.tolist():
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return np.array([find(i) for i in range(n)], dtype=np.int64)


def _stretches(parts):
    """Cut lines at their ends and at vertices shared with another line.
    Returns (stretch geometries, index of the line of each stretch, start point id, end point id)."""
    coords, line = shapely.get_coordinates(parts, return_index=True)
    coords = np.round(coords, _VERTEX_DECIMALS)
    repeated = np.zeros(len(coords), dtype=bool)
    repeated[1:] = (line[1:] == line[:-1]) & (coords[1:] == coords[:-1]).all(axis=1)
    coords, line = coords[~repeated], line[~repeated]
    enough = np.bincount(line, minlength=len(parts))[line] >= 2
    coords, line = coords[enough], line[enough]
    if len(coords) == 0:
        return None
    point = pd.DataFrame(coords).groupby([0, 1], sort=False).ngroup().to_numpy()
    distinct = pd.DataFrame({"point": point, "line": line}).drop_duplicates()
    lines_at_point = np.bincount(distinct["point"].to_numpy(), minlength=point.max() + 1)
    first = np.r_[True, line[1:] != line[:-1]]
    last = np.r_[line[1:] != line[:-1], True]
    cut = first | last | (lines_at_point[point] >= 2)
    stretch_raw = np.cumsum(cut)
    segment = np.flatnonzero(~last)  # segment i -> i + 1
    starts = segment[cut[segment]]  # first vertex of each stretch, in stretch order
    ends = np.flatnonzero(cut & ~first)  # last vertex of each stretch, in the same order
    vertex = np.concatenate([starts, segment + 1])
    owner = np.concatenate([stretch_raw[starts], stretch_raw[segment]])
    order = np.lexsort((vertex, owner))
    vertex, owner = vertex[order], owner[order]
    _, compact = np.unique(owner, return_inverse=True)
    geoms = shapely.linestrings(coords[vertex], indices=compact)
    return geoms, line[starts], point[starts], point[ends]


def _chains(stretches, key, start, end):
    """Join stretches through points where exactly two stretches end and both have the same key.
    Returns (chain geometries, index of a stretch the chain was made from)."""
    n = len(stretches)
    ends = pd.DataFrame({"point": np.concatenate([start, end]), "stretch": np.tile(np.arange(n), 2)})
    degree = ends["point"].map(ends["point"].value_counts()).to_numpy()
    pairs = ends[degree == 2].sort_values(["point", "stretch"], kind="stable")["stretch"].to_numpy().reshape(-1, 2)
    pairs = pairs[(pairs[:, 0] != pairs[:, 1]) & (key[pairs[:, 0]] == key[pairs[:, 1]])]
    if len(pairs) == 0:
        return stretches, np.arange(n)
    group = _components(n, pairs)
    size = np.bincount(group, minlength=n)[group]
    alone = np.flatnonzero(size == 1)
    joined = np.flatnonzero(size > 1)
    joined = joined[np.argsort(group[joined], kind="stable")]
    labels, first_member, compact = np.unique(group[joined], return_index=True, return_inverse=True)
    merged = shapely.line_merge(shapely.multilinestrings(stretches[joined], indices=compact))
    merged_parts, merged_group = shapely.get_parts(merged, return_index=True)
    geoms = np.concatenate([stretches[alone], merged_parts])
    source = np.concatenate([alone, joined[first_member][merged_group]])
    return geoms, source


def _split_long(geoms, source):
    """Chains longer than MAX_PIECE_M cut into ceil(length / MAX_PIECE_M) parts of equal length."""
    lengths = shapely.length(geoms)
    long = np.flatnonzero(lengths > MAX_PIECE_M)
    if len(long) == 0:
        return geoms, source
    keep = np.ones(len(geoms), dtype=bool)
    keep[long] = False
    extra_geoms, extra_source = [], []
    for i in long.tolist():
        length = float(lengths[i])
        count = math.ceil(length / MAX_PIECE_M)
        step = length / count
        for k in range(count):
            extra_geoms.append(substring(geoms[i], k * step, length if k == count - 1 else (k + 1) * step))
            extra_source.append(source[i])
    return (np.concatenate([geoms[keep], np.array(extra_geoms, dtype=object)]),
            np.concatenate([source[keep], np.array(extra_source, dtype=source.dtype)]))


def road_pieces(lines, region):
    """Road pieces (EPSG:5514) from OSM lines in EPSG:5514 with a 'tags' column; see the road piece rules.
    Columns PIECE_COLUMNS, sorted by midpoint, ids r1, r2, ..."""
    if len(lines) == 0:
        return _empty_pieces()
    tags = lines["tags"].tolist()
    worse = [classify(t) for t in tags]
    rows = [i for i, w in enumerate(worse) if w is not None]
    if not rows:
        return _empty_pieces()
    attributes = pd.DataFrame({
        "name": pd.Series([display_name(tags[i]) for i in rows], dtype=object),
        "highway": pd.Series([tags[i]["highway"] for i in rows], dtype=object),
        "tracktype": pd.Series([tags[i].get("tracktype") for i in rows], dtype=object),
        "surface": pd.Series([tags[i].get("surface") for i in rows], dtype=object),
        "worse": pd.Series([worse[i] for i in rows], dtype=bool),
    })
    key, _ = pd.factorize(pd.Series(list(attributes[_ATTRIBUTES].itertuples(index=False, name=None)),
                                    dtype=object))
    parts, part_row = shapely.get_parts(np.asarray(lines.geometry.values)[rows], return_index=True)
    cut = _stretches(parts)
    if cut is None:
        return _empty_pieces()
    stretches, stretch_part, start, end = cut
    stretch_row = part_row[stretch_part]
    chains, chain_stretch = _chains(stretches, key[stretch_row], start, end)
    pieces, piece_row = _split_long(_orient(chains), stretch_row[chain_stretch])
    pieces = _orient(pieces)

    length_m = np.array([round(float(v), 1) for v in shapely.length(pieces)])
    mid = shapely.line_interpolate_point(pieces, 0.5, normalized=True)
    mid_x, mid_y = np.round(shapely.get_x(mid), _MIDPOINT_DECIMALS), np.round(shapely.get_y(mid), _MIDPOINT_DECIMALS)
    shapely.prepare(region)
    keep = (length_m >= MIN_PIECE_M) & shapely.contains_xy(region, mid_x, mid_y)
    if not keep.any():
        return _empty_pieces()
    pieces, piece_row, length_m, mid_x, mid_y = (a[keep] for a in (pieces, piece_row, length_m, mid_x, mid_y))
    first = shapely.get_coordinates(shapely.get_point(pieces, 0))
    order = np.lexsort((first[:, 1], first[:, 0], length_m, mid_y, mid_x))
    out = attributes.iloc[piece_row[order]].reset_index(drop=True)
    out.insert(0, "id", pd.Series(["r%d" % (i + 1) for i in range(len(order))], dtype=object))
    out["length_m"] = length_m[order]
    return gpd.GeoDataFrame(out, geometry=gpd.GeoSeries(pieces[order], crs=5514), crs=5514)[PIECE_COLUMNS]
