# -*- coding: utf-8 -*-
"""Write a region in the folder layout the plugin reads: kraje/<key>/vektor/ZABAGED/*.shp and metadata."""

import json
import os
from datetime import datetime, timezone

import geopandas as gpd

PLUGIN_DATA_VERSION = "2020-01-01"  # what Project.checkRegion in the plugin requires of metadata.json
LAST_SECTOR_ID = 1000000            # the plugin's own fallback when lastsectorid.txt is missing
ATTRIBUTION = """Data attribution

Sectors, roads, tracks and streams were derived from:
  OpenStreetMap data, (c) OpenStreetMap contributors, licensed under the ODbL
  (https://www.openstreetmap.org/copyright).
  ESA WorldCover 2021 v200, (c) ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data
  (2021) processed by ESA WorldCover consortium, licensed under CC BY 4.0
  (https://creativecommons.org/licenses/by/4.0/). Only when the data was built with --landcover osm+worldcover.

Share-alike: publishing this derived data requires ODbL handling. Keep this notice with the data.
"""


def sectors_frame(sectors):
    """GeoDataFrame (EPSG:5514) with the string field 'typ' from [(Polygon, typ)]. Every geometry must be a valid Polygon."""
    broken = sum(1 for g, _ in sectors if g.geom_type != "Polygon" or not g.is_valid)
    if broken:
        raise ValueError("%d sectors are not valid single polygons" % broken)
    return gpd.GeoDataFrame({"typ": [t for _, t in sectors]}, geometry=[g for g, _ in sectors], crs=5514)


def zabaged_dir(out_dir):
    return os.path.join(out_dir, "vektor", "ZABAGED")


def write_region(out_dir, sectors, layers, metadata):
    """Write sectors.shp, cesta/lespru/vodtok.shp, lastsectorid.txt, metadata.json and ATTRIBUTION.txt."""
    folder = zabaged_dir(out_dir)
    os.makedirs(folder, exist_ok=True)
    sectors.to_file(os.path.join(folder, "sectors.shp"), encoding="utf-8")
    for name, frame in layers.items():
        frame.to_file(os.path.join(folder, name + ".shp"), encoding="utf-8")
    with open(os.path.join(folder, "lastsectorid.txt"), "w") as f:
        f.write(str(LAST_SECTOR_ID))
    meta = {"version": PLUGIN_DATA_VERSION, "built": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    meta.update(metadata)
    with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, "ATTRIBUTION.txt"), "w", encoding="utf-8") as f:
        f.write(ATTRIBUTION)
