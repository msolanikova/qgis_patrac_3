# -*- coding: utf-8 -*-
"""Build one region: OSM (+ WorldCover) -> sectors, reference layers, municipality list -> plugin folder layout."""

import dataclasses
import json
import logging
import os
import shutil
import tempfile
import time

import geopandas as gpd
import shapely
from pyproj import Transformer
from shapely.geometry import box

from tools.sk_data import download, export, extract, landcover, layers, places
from tools.sk_data.config import MARGIN_M, REGIONS, SectorSize, region_dir, source_dir
from tools.sk_data.crs import project_geometries, to_sjtsk, wgs84_to_sjtsk
from tools.sk_data.rules import check_rules, load_rules
from tools.sk_data.sectors import build_sectors
from tools.sk_data.validate import validate

log = logging.getLogger("sk_data")
LANDCOVER_MODES = ("osm", "osm+worldcover")
WINDOW_WIDTH_M, WINDOW_HEIGHT_M = 12000.0, 10000.0   # the area the plugin clips for one search


def default_osm_path(root):
    return os.path.join(source_dir(root, "osm-slovakia"), "slovakia-latest.osm.pbf")


def default_worldcover_paths(root, bbox):
    paths = [os.path.join(source_dir(root, "esa-worldcover"), os.path.basename(download.worldcover_url(t)))
             for t in download.worldcover_tiles(bbox)]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError("missing WorldCover tiles %s; run: python -m tools.sk_data download --region <key>" % missing)
    return paths


def _within(geoms, margin):
    shapely.prepare(margin)
    return shapely.intersects(geoms, margin)


def build_region(key, root, size=None, landcover_mode="osm+worldcover", out_dir=None, osm_pbf=None,
                 worldcover_paths=None, region_name=None, area_tolerance=0.02, window=None, overwrite=False):
    """Build and validate a region. Returns (problems, report, folder).

    window=(lon, lat) builds only a 12 x 10 km area around that point (fast, for inspecting a place);
    it needs an explicit out_dir, the region boundary is not needed and no municipality list is written.
    The data is written to a sibling staging folder "<out_dir>.partial-*" and validated there. Only when it
    validates is it moved to out_dir (default <root>/kraje/<key>), replacing an existing folder; then folder is
    out_dir. When validation fails, out_dir is not touched and folder is the staging folder, kept for inspection.
    An existing non-empty out_dir is refused (FileExistsError) unless overwrite is true.
    Every call extracts into its own temporary folder under <root>/work, so builds can run side by side.
    """
    if landcover_mode not in LANDCOVER_MODES:
        raise ValueError("landcover must be one of %s" % (LANDCOVER_MODES,))
    if window and not out_dir:
        raise ValueError("a window build needs an explicit out_dir (it must not be written to the region folder)")
    out_dir = os.path.abspath(out_dir or region_dir(root, key))
    if os.path.lexists(out_dir) and (not os.path.isdir(out_dir) or os.listdir(out_dir)) and not overwrite:
        raise FileExistsError("%s already exists and is not empty; pass --overwrite to replace it "
                              "(only after the new build validates) or choose another --out" % out_dir)
    parent = os.path.dirname(out_dir)
    os.makedirs(parent, exist_ok=True)
    os.makedirs(os.path.join(root, "work"), exist_ok=True)
    work = tempfile.mkdtemp(prefix=key + "-", dir=os.path.join(root, "work"))
    staging = tempfile.mkdtemp(prefix=os.path.basename(out_dir) + ".partial-", dir=parent)
    umask = os.umask(0)
    os.umask(umask)
    os.chmod(staging, 0o777 & ~umask)                 # mkdtemp makes it private; the data should look like a normal folder
    try:
        problems, report = _build_region(key, root, work, size, landcover_mode, staging, osm_pbf, worldcover_paths,
                                         region_name, area_tolerance, window)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if problems:
        return problems, report, staging
    _replace(out_dir, staging)
    return problems, report, out_dir


def _replace(out_dir, staging):
    """Move the validated staging folder to out_dir; the folder that was there is removed only afterwards."""
    old = None
    if os.path.lexists(out_dir):
        old = tempfile.mkdtemp(prefix=os.path.basename(out_dir) + ".old-", dir=os.path.dirname(out_dir))
        os.rmdir(old)                                 # only to get a free sibling name
        os.rename(out_dir, old)
    try:
        os.rename(staging, out_dir)
    except BaseException:
        if old:
            os.rename(old, out_dir)
        raise
    if old:
        if os.path.isdir(old) and not os.path.islink(old):
            shutil.rmtree(old)
        else:
            os.remove(old)


def _region_boundary(pbf, name, work):
    """(boundary frame, region in EPSG:4326, region in S-JTSK, padded bbox in EPSG:4326) of the region named in OSM."""
    boundary = extract.region_boundary(pbf, name, work)
    region_wgs = shapely.union_all(boundary.geometry.values)
    region = shapely.make_valid(shapely.union_all(project_geometries(boundary.geometry.values)))
    return boundary, region_wgs, region, extract.bbox_of(boundary)


def _place_rows(polygons_wgs, points_path, region_wgs, key):
    """Municipality list rows (see places.build_places) from the extracted OSM polygons and points."""
    municipalities = places.admin_areas(polygons_wgs, places.MUNICIPALITY_LEVELS)
    districts = places.admin_areas(polygons_wgs, places.DISTRICT_LEVEL)
    points = extract.read_points(points_path)
    return places.build_places(municipalities, districts, points, region_wgs, key)


def build_places_only(key, root, out_dir=None, osm_pbf=None, region_name=None):
    """Regenerate only the municipality list of a region: <out_dir>/places.csv (default the region folder).

    Extracts the region into its own temporary folder under <root>/work (removed afterwards) and returns the rows.
    Nothing else is written to out_dir.
    """
    name = region_name or REGIONS[key]
    pbf = osm_pbf or default_osm_path(root)
    out_dir = os.path.abspath(out_dir or region_dir(root, key))
    os.makedirs(os.path.join(root, "work"), exist_ok=True)
    work = tempfile.mkdtemp(prefix=key + "-places-", dir=os.path.join(root, "work"))
    try:
        _, region_wgs, _, bbox = _region_boundary(pbf, name, work)
        paths = extract.extract(pbf, bbox, work)
        polygons_wgs, _ = extract.read_polygons(paths["polygons"])
        rows = _place_rows(polygons_wgs, paths["points"], region_wgs, key)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    places.write_csv(rows, os.path.join(out_dir, "places.csv"))
    return rows


def _build_region(key, root, work, size, landcover_mode, out_dir, osm_pbf, worldcover_paths, region_name,
                  area_tolerance, window):
    if landcover_mode not in LANDCOVER_MODES:
        raise ValueError("landcover must be one of %s" % (LANDCOVER_MODES,))
    size = size or SectorSize()
    rules = load_rules()
    bad = check_rules(rules)
    if bad:
        raise ValueError("inconsistent rules: %s" % bad)
    name = region_name or REGIONS[key]
    pbf = osm_pbf or default_osm_path(root)
    t0 = time.time()

    def step(message):
        log.info("[%4.0fs] %s", time.time() - t0, message)

    if window:
        cx, cy = wgs84_to_sjtsk().transform(*window)
        region = box(cx - WINDOW_WIDTH_M / 2, cy - WINDOW_HEIGHT_M / 2, cx + WINDOW_WIDTH_M / 2, cy + WINDOW_HEIGHT_M / 2)
        margin = region.buffer(MARGIN_M)
        bbox = Transformer.from_crs(5514, 4326, always_xy=True).transform_bounds(*margin.bounds)
        region_wgs = None
    else:
        _, region_wgs, region, bbox = _region_boundary(pbf, name, work)
        margin = region.buffer(MARGIN_M)
    paths = extract.extract(pbf, bbox, work)
    step("region %s extracted" % (name if not window else "window %s,%s" % window))

    lines = to_sjtsk(extract.read_lines(paths["lines"]))
    lines = lines[_within(lines.geometry.values, margin)]
    polygons_wgs, buildings_wgs = extract.read_polygons(paths["polygons"])
    polygons = to_sjtsk(polygons_wgs)
    polygons = polygons[_within(polygons.geometry.values, margin)]
    buildings = shapely.make_valid(project_geometries(buildings_wgs.values))
    buildings = list(buildings[_within(buildings, margin)])
    step("loaded %d lines, %d polygons, %d buildings" % (len(lines), len(polygons), len(buildings)))

    osm = landcover.osm_cover(polygons, rules, size)
    if landcover_mode == "osm+worldcover":
        tifs = worldcover_paths or default_worldcover_paths(root, bbox)
        base = landcover.worldcover_cover(tifs, bbox, rules, size)
    else:
        base = gpd.GeoDataFrame({"typ": []}, geometry=[], crs=5514)
    step("land cover: %d OSM polygons, %d WorldCover polygons" % (len(osm), len(base)))

    boundary_lines = list(osm.geometry.boundary) + list(base.geometry.boundary)
    sector_list = build_sectors(layers.barrier_lines(lines), boundary_lines, margin, region, osm, base, buildings, size, rules.classes)
    sectors = export.sectors_frame(sector_list)
    step("%d sectors" % len(sectors))

    output = layers.output_layers(lines, sectors, region)
    rows = _place_rows(polygons_wgs, paths["points"], region_wgs, key) if region_wgs is not None else []

    manifest_path = os.path.join(root, "source", "sources.json")
    sources = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            sources = json.load(f)
    export.write_region(out_dir, sectors, output, {
        "region": key, "region_name": name, "landcover": landcover_mode, "window": window,
        "sector_size": dataclasses.asdict(size), "sources": sources})
    places.write_csv(rows, os.path.join(out_dir, "places.csv"))
    step("written to %s (%d places)" % (out_dir, len(rows)))

    problems, report = validate(out_dir, region, size, rules.classes, area_tolerance)
    report["places"] = len(rows)
    report["seconds"] = round(time.time() - t0)
    return problems, report
