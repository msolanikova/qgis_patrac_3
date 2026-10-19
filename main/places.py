# -*- coding: utf-8 -*-
"""Municipality list read from the region folders (pure Python, no QGIS)."""

import csv
import glob
import os

MIN_COLUMNS = 7


def read_places(data_path):
    """Reads <data_path>/kraje/*/places.csv (x;y;code;name;okres_code;okres;REGION, no header).

    Returns (names, coords, regions): three aligned lists sorted by name. A name looks
    like "Ardovo (okres Rožňava)", coords like "x;y". No region folders give three empty lists.
    """
    rows = []
    pattern = os.path.join(data_path, "kraje", "*", "places.csv")
    for file_name in glob.glob(pattern):
        with open(file_name, "r", encoding="utf-8", newline="") as file_input:
            for row in csv.reader(file_input, delimiter=";"):
                if not row or len(row) < MIN_COLUMNS:
                    continue
                rows.append((row[3] + " (" + row[5] + ")", row[0] + ";" + row[1], row[6]))
    rows.sort()
    return [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]
