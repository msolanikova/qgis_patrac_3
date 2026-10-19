# -*- coding: utf-8 -*-
"""Download the source data (Geofabrik OSM extract, ESA WorldCover tiles) and record where it came from."""

import hashlib
import json
import logging
import math
import os
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("sk_data")

GEOFABRIK_URL = "https://download.geofabrik.de/europe/slovakia-latest.osm.pbf"
WORLDCOVER_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
USER_AGENT = "patrac-sk-data/1.0"


def worldcover_tiles(bbox):
    """Names of the 3 x 3 degree WorldCover tiles (e.g. 'N48E021') covering bbox = (minx, miny, maxx, maxy) lon/lat."""
    minx, miny, maxx, maxy = bbox
    tiles = []
    lat = int(math.floor(miny / 3) * 3)
    while lat < maxy:
        lon = int(math.floor(minx / 3) * 3)
        while lon < maxx:
            tiles.append("%s%02d%s%03d" % ("N" if lat >= 0 else "S", abs(lat), "E" if lon >= 0 else "W", abs(lon)))
            lon += 3
        lat += 3
    return tiles


def worldcover_url(tile):
    return WORLDCOVER_URL.format(tile=tile)


def download(url, dest, opener=None, chunk=1 << 20):
    """Download url to dest (via dest + '.part'). Returns {'url', 'path', 'bytes', 'sha256', 'downloaded'}."""
    opener = opener or (lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": USER_AGENT})))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    digest = hashlib.sha256()
    size = 0
    with opener(url) as response, open(part, "wb") as out:
        while True:
            block = response.read(chunk)
            if not block:
                break
            out.write(block)
            digest.update(block)
            size += len(block)
    os.replace(part, dest)
    return {"url": url, "path": dest, "bytes": size, "sha256": digest.hexdigest(),
            "downloaded": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def fetch_sources(root, bbox, opener=None, include_worldcover=True):
    """Make sure the OSM extract and the WorldCover tiles for bbox exist under <root>/source. Returns the manifest.

    Files that already exist are kept (their manifest entry is kept too); delete a file to download it again.
    The manifest is written to <root>/source/sources.json.
    """
    source = os.path.join(root, "source")
    manifest_path = os.path.join(source, "sources.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    wanted = [("osm", GEOFABRIK_URL, os.path.join(source, "osm-slovakia", "slovakia-latest.osm.pbf"))]
    if include_worldcover:
        for tile in worldcover_tiles(bbox):
            wanted.append(("worldcover-" + tile, worldcover_url(tile),
                           os.path.join(source, "esa-worldcover", os.path.basename(worldcover_url(tile)))))
    for name, url, dest in wanted:
        if os.path.exists(dest):
            manifest.setdefault(name, {"url": url, "path": dest, "bytes": os.path.getsize(dest), "sha256": None, "downloaded": None})
            continue
        log.info("downloading %s", url)
        manifest[name] = download(url, dest, opener)
    os.makedirs(source, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    return manifest
