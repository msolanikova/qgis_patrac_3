# -*- coding: utf-8 -*-
"""Command line: python -m tools.sk_data <download|build|rules|project> ... (run with QGIS's Python)."""

import argparse
import json
import logging
import os
import sys

from tools.sk_data import download, extract, pipeline, qgis_project
from tools.sk_data.config import REGIONS, SectorSize, data_root
from tools.sk_data.rules import guessed_rules_text


def _size(args):
    return SectorSize(min_ha=args.min_ha, target_ha=args.target_ha, max_ha=args.max_ha)


def cmd_download(args):
    root = data_root()
    download.fetch_sources(root, None, include_worldcover=False)
    boundary = extract.region_boundary(pipeline.default_osm_path(root), REGIONS[args.region], os.path.join(root, "work", args.region))
    manifest = download.fetch_sources(root, extract.bbox_of(boundary), include_worldcover=not args.no_worldcover)
    print(json.dumps({k: {"bytes": v["bytes"], "path": v["path"]} for k, v in manifest.items()}, indent=1))
    return 0


def _window(parser, value):
    try:
        lon, lat = (float(part) for part in value.split(","))
    except ValueError:
        parser.error("--window must be LON,LAT, for example 21.2611,48.7164")
    return lon, lat


def cmd_build(args):
    root = data_root()
    try:
        problems, report, out_dir = pipeline.build_region(
            args.region, root, size=_size(args), landcover_mode=args.landcover, out_dir=args.out,
            window=args.window, overwrite=args.overwrite)
    except (FileExistsError, ValueError) as exc:
        print("error:", exc, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if problems:
        print("\nVALIDATION FAILED:", *problems, sep="\n  - ")
        print("\noutput kept for inspection in", out_dir)
        return 1
    print("\nvalidation passed; output in", out_dir)
    return 0


def cmd_rules(args):
    print(guessed_rules_text())
    return 0


def cmd_project(args):
    app = qgis_project.init_qgis()
    pairs = [tuple(item.split("=", 1)) for item in args.region_dir]
    bookmarks = []
    for item in args.bookmark or []:
        name, _, where = item.partition("=")
        lon, lat = (float(v) for v in where.split(","))
        bookmarks.append((name, lon, lat))
    names = qgis_project.build_project(pairs, args.out, bookmarks=bookmarks)
    print("wrote", args.out, "with layers:", names)
    app.exitQgis()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tools.sk_data", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, help_ in (("download", cmd_download, "download the OSM extract and WorldCover tiles"),
                              ("build", cmd_build, "build and validate a region"),
                              ("rules", cmd_rules, "list the OSM mappings that are guesses"),
                              ("project", cmd_project, "write a QGIS project to inspect built regions")):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(func=func)
        if name in ("download", "build"):
            p.add_argument("--region", required=True, choices=sorted(REGIONS))
        if name == "download":
            p.add_argument("--no-worldcover", action="store_true")
        if name == "build":
            p.add_argument("--landcover", choices=pipeline.LANDCOVER_MODES, default="osm+worldcover")
            p.add_argument("--out", help="output folder (default <data>/kraje/<region>)")
            p.add_argument("--overwrite", action="store_true",
                           help="replace an existing non-empty output folder, but only after the new build validates")
            p.add_argument("--window", metavar="LON,LAT", help="build only a 12 x 10 km area around this point (needs --out)")
            d = SectorSize()
            p.add_argument("--min-ha", type=float, default=d.min_ha)
            p.add_argument("--target-ha", type=float, default=d.target_ha)
            p.add_argument("--max-ha", type=float, default=d.max_ha)
        if name == "project":
            p.add_argument("--region-dir", action="append", required=True, metavar="LABEL=DIR")
            p.add_argument("--bookmark", action="append", metavar="NAME=LON,LAT",
                           help="add a spatial bookmark; the project opens on the first one (repeatable)")
            p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "build" and args.window:
        if not args.out:
            parser.error("--window needs --out (a window must not overwrite the region folder)")
        args.window = _window(parser, args.window)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
