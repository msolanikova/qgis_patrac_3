# -*- coding: utf-8 -*-
"""Sector builder: polygonize lines into faces, type them, merge small ones, split big ones.

All functions work on shapely geometries in a metric CRS (EPSG:5514) and need no files.
"""

import heapq
import logging
import math
from collections import Counter

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

log = logging.getLogger("sk_data")

MIN_SHARED_BORDER_M = 3.0  # ordinary merges need at least this much shared border
MIN_CONTACT_M = 0.01       # any real contact counts when a tiny face or sliver is absorbed


def polygonize_faces(barrier_lines, boundary_lines, margin):
    """Faces enclosed by the lines and the margin polygon's boundary, kept when inside the margin."""
    noded = unary_union(list(barrier_lines) + list(boundary_lines) + [margin.boundary])
    faces = [p for p in polygonize(noded) if p.is_valid and p.area > 1.0]
    if not faces:
        return []
    arr = np.array(faces, dtype=object)
    inside = shapely.contains(margin, shapely.point_on_surface(arr))
    return list(arr[inside])


def _smallest_enclosing_typ(points, cover):
    """{point index: typ of the smallest cover polygon containing the point}."""
    if len(cover) == 0 or len(points) == 0:
        return {}
    areas = cover.geometry.area.to_numpy()
    typs = cover["typ"].to_numpy()
    tree = STRtree(list(cover.geometry))
    point_idx, cover_idx = tree.query(points, predicate="within")
    best = {}
    for p, c in zip(point_idx, cover_idx):
        p, c = int(p), int(c)
        if p not in best or areas[c] < areas[best[p]]:
            best[p] = c
    return {p: str(typs[c]) for p, c in best.items()}


def assign_types(faces, osm_cover, base_cover, buildings, size):
    """Sector type per face: OSM cover first, then the base layer (WorldCover), else OTHER.

    osm_cover / base_cover: GeoDataFrames with columns 'typ' and geometry.
    buildings: sequence of building polygons. Faces still OTHER with enough buildings become AREZAS.
    """
    if not faces:
        return []
    arr = np.array(faces, dtype=object)
    points = shapely.point_on_surface(arr)
    from_osm = _smallest_enclosing_typ(points, osm_cover)
    from_base = _smallest_enclosing_typ(points, base_cover)
    types = [from_osm.get(i) or from_base.get(i) or "OTHER" for i in range(len(faces))]
    buildings = list(buildings)
    if buildings:
        barr = np.array(buildings, dtype=object)
        btree = STRtree(buildings)
        for i, typ in enumerate(types):
            if typ != "OTHER":
                continue
            candidates = btree.query(faces[i], predicate="intersects")
            if len(candidates) == 0:
                continue
            covered = shapely.area(shapely.intersection(barr[candidates], faces[i])).sum()
            if covered / faces[i].area >= size.building_share:
                types[i] = "AREZAS"
    return types


def _clean_polygons(geom):
    """The valid polygons in geom: an invalid geometry is repaired, specks under 1 m2 and degenerate holes are dropped."""
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    out = []
    for polygon in _polygons(geom):
        holes = [ring for ring in polygon.interiors if Polygon(ring).area >= 1.0]
        out.append(polygon if len(holes) == len(polygon.interiors) else Polygon(polygon.exterior, holes))
    return out


def _single_polygon(geom):
    """geom as one valid Polygon without degenerate parts, or None if it would be several real parts."""
    parts = _clean_polygons(geom)
    return parts[0] if len(parts) == 1 else None


def _union(a, b):
    """Union of two polygons as one valid Polygon, or None (touching only at a point, degenerate result)."""
    return _single_polygon(shapely.union(a, b))


def merge_faces(faces, types, size, classes):
    """Merge faces smaller than size.min_ha into neighbours. Returns [(geometry, typ)].

    A face merges with the neighbour of the same plugin class (classes: typ -> 1..10) that shares the
    longest border (at least MIN_SHARED_BORDER_M), as long as the result stays within size.max_ha.
    Faces under size.tiny_ha and thin slivers merge into any touching neighbour, however short the
    contact. A merged sector takes the type with the largest area.
    """
    geoms = {i: g for i, g in enumerate(faces)}
    ftyp = dict(enumerate(types))
    area = {i: g.area for i, g in geoms.items()}
    mix = {i: Counter({types[i]: faces[i].area}) for i in geoms}
    adj = {i: {} for i in geoms}
    if len(faces) > 1:
        arr = np.array(faces, dtype=object)
        a_idx, b_idx = STRtree(arr).query(arr, predicate="intersects")
        keep = a_idx < b_idx
        a_idx, b_idx = a_idx[keep], b_idx[keep]
        lengths = shapely.length(shapely.intersection(arr[a_idx], arr[b_idx]))
        for a, b, length in zip(a_idx, b_idx, lengths):
            if length >= MIN_CONTACT_M:
                adj[int(a)][int(b)] = float(length)
                adj[int(b)][int(a)] = float(length)

    heap = [(area[i], i) for i in geoms if area[i] < size.min_m2]
    heapq.heapify(heap)
    while heap:
        a, i = heapq.heappop(heap)
        if i not in geoms or abs(area[i] - a) > 1e-6 or area[i] >= size.min_m2:
            continue
        neighbours = adj[i]
        if not neighbours:
            continue
        same = [(length, -area[j], j) for j, length in neighbours.items()
                if length >= MIN_SHARED_BORDER_M and classes[ftyp[j]] == classes[ftyp[i]]
                and area[i] + area[j] <= size.max_m2]
        thin = (area[i] < size.sliver_max_m2
                and 4 * np.pi * area[i] / geoms[i].length ** 2 < size.sliver_compactness)
        if same:
            ranked = sorted(same, reverse=True)
        elif area[i] < size.tiny_m2 or thin:
            ranked = sorted(((length, -area[j], j) for j, length in neighbours.items()), reverse=True)
        else:
            continue
        for _, _, j in ranked:               # the best neighbour whose union is one valid polygon
            joined = _union(geoms[j], geoms[i])
            if joined is not None:
                break
        else:
            continue
        mix[j].update(mix[i])
        ftyp[j] = mix[j].most_common(1)[0][0]
        geoms[j] = joined
        area[j] = joined.area
        for k, length in adj[i].items():
            if k == j:
                continue
            adj[j][k] = adj[j].get(k, 0.0) + length
            adj[k][j] = adj[j][k]
            adj[k].pop(i, None)
        adj[j].pop(i, None)
        del geoms[i], adj[i], area[i], ftyp[i], mix[i]
        if area[j] < size.min_m2:
            heapq.heappush(heap, (area[j], j))
    return [(geoms[i], ftyp[i]) for i in geoms]


def _long_axis(g):
    with np.errstate(divide="ignore", invalid="ignore"):   # GEOS sets floating-point flags that numpy reports as warnings
        rectangle = g.minimum_rotated_rectangle
    xs, ys = rectangle.exterior.coords.xy
    e1 = (xs[1] - xs[0], ys[1] - ys[0])
    e2 = (xs[2] - xs[1], ys[2] - ys[1])
    v = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2
    return np.array(v) / np.hypot(*v)


def _side(g, axis, offset, lower):
    """Part of g on one side of the line {x: axis . x = offset}."""
    big = 20000.0
    perp = np.array([-axis[1], axis[0]])
    centre = np.array(g.centroid.coords[0])
    sign = -1.0 if lower else 1.0
    a = centre + axis * (offset - float(np.dot(axis, centre)))
    return g.intersection(Polygon([a + perp * big, a - perp * big,
                                   a - perp * big + sign * axis * big, a + perp * big + sign * axis * big]))


def _polygons(g):
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g] if g.area > 1.0 else []
    return [p for part in getattr(g, "geoms", []) for p in _polygons(part)]


def _parts_for(area, size):
    """Number of near-equal parts for an area above the maximum: the fewest that keep every part under
    max_m2 (with 2% safety), or one more if that gives parts closer to the target size."""
    fewest = int(math.ceil(area / (size.max_m2 * 0.98)))
    return min((fewest, fewest + 1), key=lambda n: (abs(area / n - size.target_m2), -n))


def _split(g, size, depth=0):
    if g.area <= size.max_m2 or depth > 14:
        return [g]
    parts = _parts_for(g.area, size)
    axis = _long_axis(g)
    projections = [float(np.dot(axis, c)) for c in np.array(g.convex_hull.exterior.coords)]
    low, high = min(projections), max(projections)
    wanted = g.area * (parts // 2) / parts
    for _ in range(40):  # bisection on the cut position so the lower side gets its share of the area
        mid = (low + high) / 2
        if _side(g, axis, mid, True).area < wanted:
            low = mid
        else:
            high = mid
    out = []
    for piece in _polygons(_side(g, axis, mid, True)) + _polygons(_side(g, axis, mid, False)):
        out.extend(_split(piece, size, depth + 1))
    return out


def split_oversized(sectors, size):
    """Cut sectors larger than size.max_ha into near-equal parts of about size.target_ha."""
    out = []
    for geom, typ in sectors:
        for polygon in _polygons(geom):
            out.extend((part, typ) for part in _split(polygon, size))
    return out


def absorb_fragments(sectors, size):
    """Merge every sector smaller than size.tiny_ha into a touching sector.

    Splitting leaves small corner fragments. Each one joins the neighbour it shares the longest border with
    when the result stays within size.max_ha, otherwise the smallest neighbour (so a sector can end up
    slightly above the maximum, by less than size.tiny_ha). A fragment without any neighbour is kept.
    """
    if not sectors:
        return []
    geoms = [g for g, _ in sectors]
    typs = [t for _, t in sectors]
    area = [g.area for g in geoms]
    parent = list(range(len(geoms)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tree = STRtree(np.array(geoms, dtype=object))
    for i in sorted((i for i in range(len(geoms)) if area[i] < size.tiny_m2), key=lambda i: area[i]):
        if parent[i] != i or area[i] >= size.tiny_m2:
            continue
        neighbours = {find(int(k)) for k in tree.query(geoms[i], predicate="intersects")} - {i}
        ranked = []
        for r in neighbours:
            length = geoms[i].intersection(geoms[r]).length
            if length >= MIN_CONTACT_M:
                fits = area[i] + area[r] <= size.max_m2
                ranked.append(((fits, length if fits else -area[r]), r))
        for _, r in sorted(ranked, reverse=True):   # the best neighbour whose union is one valid polygon
            joined = _union(geoms[r], geoms[i])
            if joined is not None:
                break
        else:
            continue
        if area[i] > area[r]:
            typs[r] = typs[i]
        geoms[r] = joined
        area[r] = joined.area
        parent[i] = r
    return [(geoms[i], typs[i]) for i in range(len(geoms)) if parent[i] == i]


def finalize_sectors(sectors):
    """Make every sector a valid single polygon: repair invalid geometries, drop specks and degenerate holes
    (a zero-width hole turned into an invalid MultiPolygon after a shapefile round trip), and turn a
    sector that is several real parts into separate sectors of the same type."""
    return [(polygon, typ) for geom, typ in sectors for polygon in _clean_polygons(geom)]


def select_inside(sectors, region):
    """Keep sectors whose representative point lies inside the region polygon."""
    if not sectors:
        return []
    arr = np.array([g for g, _ in sectors], dtype=object)
    inside = shapely.contains(region, shapely.point_on_surface(arr))
    return [sectors[i] for i in np.flatnonzero(inside)]


def build_sectors(barrier_lines, boundary_lines, margin, region, osm_cover, base_cover, buildings, size, classes):
    """Faces -> types -> merge -> split -> absorb fragments -> clean -> keep those inside the region. Returns [(Polygon, typ)]."""
    faces = polygonize_faces(barrier_lines, boundary_lines, margin)
    log.info("faces: %d", len(faces))
    types = assign_types(faces, osm_cover, base_cover, buildings, size)
    merged = merge_faces(faces, types, size, classes)
    log.info("sectors after merge: %d", len(merged))
    sectors = finalize_sectors(absorb_fragments(split_oversized(merged, size), size))
    log.info("sectors after split and cleanup: %d", len(sectors))
    return select_inside(sectors, region)
