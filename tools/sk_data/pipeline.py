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
                 worldcover_paths=None, region_name=None, area_tolerance=0.02, window=None):
    """Build and validate a region. Returns (problems, report, out_dir).

    window=(lon, lat) builds only a 12 x 10 km area around that point (fast, for inspecting a place);
    the region boundary is then not needed and no municipality list is written.
    Every call extracts into its own temporary folder under <root>/work, so builds can run side by side.
    """
    os.makedirs(os.path.join(root, "work"), exist_ok=True)
    work = tempfile.mkdtemp(prefix=key + "-", dir=os.path.join(root, "work"))
    try:
        return _build_region(key, root, work, size, landcover_mode, out_dir, osm_pbf, worldcover_paths,
                             region_name, area_tolerance, window)
    finally:
        shutil.rmtree(work, ignore_errors=True)


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
    out_dir = out_dir or region_dir(root, key)
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
        boundary = extract.region_boundary(pbf, name, work)
        bbox = extract.bbox_of(boundary)
        region_wgs = shapely.union_all(boundary.geometry.values)
        region = shapely.make_valid(shapely.union_all(project_geometries(boundary.geometry.values)))
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
    rows = []
    if region_wgs is not None:
        municipalities = places.admin_areas(polygons_wgs, places.MUNICIPALITY_LEVEL)
        districts = places.admin_areas(polygons_wgs, places.DISTRICT_LEVEL)
        points = extract.read_points(paths["points"])
        rows = places.build_places(municipalities, districts, points, region_wgs, key)

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
    return problems, report, out_dir
