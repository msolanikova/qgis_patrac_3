# -*- coding: utf-8 -*-
"""Region table, sector-size settings and data locations for the Slovak data pipeline."""

import os
from dataclasses import dataclass

# Region key (lower-case ISO 3166-2:SK suffix, also the folder name under kraje/) -> OSM name of the admin_level=4 relation
REGIONS = {
    "ba": "Bratislavský kraj",
    "tt": "Trnavský kraj",
    "tn": "Trenčiansky kraj",
    "nr": "Nitriansky kraj",
    "za": "Žilinský kraj",
    "bb": "Banskobystrický kraj",
    "po": "Prešovský kraj",
    "ke": "Košický kraj",
}

MARGIN_M = 800.0  # data is cut this far outside the region so that sectors at the border are complete


@dataclass(frozen=True)
class SectorSize:
    """Sector size targets in hectares and the other thresholds of the sector builder."""
    min_ha: float = 6.0
    target_ha: float = 7.0
    max_ha: float = 8.0
    tiny_ha: float = 1.0           # faces smaller than this merge into any neighbour
    sliver_max_ha: float = 5.0     # thin faces up to this size merge into any neighbour
    sliver_compactness: float = 0.10
    building_share: float = 0.08   # unlabelled faces with this share of buildings become AREZAS
    min_cover_m2: float = 2500.0   # land-cover polygons smaller than this create no boundaries

    def __post_init__(self):
        if not 0 < self.min_ha <= self.target_ha <= self.max_ha:
            raise ValueError("need 0 < min_ha <= target_ha <= max_ha, got %s/%s/%s" % (self.min_ha, self.target_ha, self.max_ha))

    @property
    def min_m2(self):
        return self.min_ha * 1e4

    @property
    def target_m2(self):
        return self.target_ha * 1e4

    @property
    def max_m2(self):
        return self.max_ha * 1e4

    @property
    def tiny_m2(self):
        return self.tiny_ha * 1e4

    @property
    def sliver_max_m2(self):
        return self.sliver_max_ha * 1e4


def data_root(environ=None, home=None):
    """Patrac data folder (default ~/patracdata, override with $PATRAC_DATA), without a trailing slash."""
    from patrac_paths import default_data_path
    return default_data_path(environ, home).rstrip("/")


def source_dir(root, *parts):
    return os.path.join(root, "source", *parts)


def region_dir(root, key):
    return os.path.join(root, "kraje", key)
