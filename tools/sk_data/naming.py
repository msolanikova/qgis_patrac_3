# -*- coding: utf-8 -*-
"""Sector ids and names for the plugin: id "1".."N", label = one letter + a number (for example K142).

The letter comes from a 12 km grid in S-JTSK, 16 letters repeating every 4 cells in x and y, so any 3 x 3 block of cells
has 9 different letters and two cells with the same letter are at least 4 cells (more than 36 km) apart. The number
counts the sectors inside one cell, north to south in bands of 500 m and west to east inside a band. A search area
(about 12 x 10 km) therefore never has two sectors with the same label. Pure Python and shapely, no file access.
"""

import math

import shapely

CELL_M = 12000.0                 # a search project covers about 12 x 10 km
LETTERS = "ABCDEFGHJKLMNPRS"     # 16 letters, without I, O and Q (confusable with 1 and 0 over the radio)
BAND_M = 500.0                   # reading order: bands of this height, north to south
MAX_SECTORS = 1000000            # the plugin gives new sectors ids from lastsectorid.txt (1,000,000) upwards


def cell_of(x, y):
    """Grid cell (cx, cy) of a point. S-JTSK coordinates are negative, so this must floor, not truncate."""
    return math.floor(x / CELL_M), math.floor(y / CELL_M)


def letter_of(cx, cy):
    return LETTERS[(cx % 4) + 4 * (cy % 4)]


def _keys(sectors):
    """Sort keys (cy, cx, band, x, y, area, input index) of the sectors, from the reference point of each polygon."""
    polygons = [g for g, _ in sectors]
    points = shapely.get_coordinates(shapely.point_on_surface(polygons))
    areas = shapely.area(polygons)
    keys = []
    for k in range(len(polygons)):
        x, y = float(points[k][0]), float(points[k][1])
        cx, cy = cell_of(x, y)
        keys.append((cy, cx, math.floor(-y / BAND_M), x, y, float(areas[k]), k))
    return keys


def reading_order(sectors):
    """Indices of [(Polygon, typ)] in reading order, the order of the ids: cell row from the south, cell from the west,
    500 m band from the north, then x, y and area (identical polygons keep their input order)."""
    keys = _keys(sectors)
    return sorted(range(len(keys)), key=keys.__getitem__)


def assign_ids_and_labels(sectors):
    """sectors: [(Polygon, typ)]. Returns (ids, labels), two lists of strings in the order of the input.

    ids are "1".."N" in reading order (see reading_order); labels are the cell's letter plus a counter that restarts at 1
    in every cell. The result does not depend on the input order, except between identical polygons, which keep their
    input order.
    """
    n = len(sectors)
    if n >= MAX_SECTORS:
        raise ValueError("%d sectors; sector ids must stay below %d, the first id the plugin gives to a split sector"
                         % (n, MAX_SECTORS))
    keys = _keys(sectors)
    order = sorted(range(n), key=keys.__getitem__)
    ids = [""] * n
    labels = [""] * n
    counters = {}
    for rank, k in enumerate(order, start=1):
        cy, cx = keys[k][0], keys[k][1]
        counters[cy, cx] = counters.get((cy, cx), 0) + 1
        ids[k] = str(rank)
        labels[k] = "%s%d" % (letter_of(cx, cy), counters[cy, cx])
    return ids, labels
