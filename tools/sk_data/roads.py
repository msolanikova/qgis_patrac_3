# -*- coding: utf-8 -*-
"""Road pieces from OSM lines: which ways count as roads or paths for the service bundle, and what they are called."""

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
