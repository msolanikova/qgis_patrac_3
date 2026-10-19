# -*- coding: utf-8 -*-
"""Municipality list read from the region folders (pure Python, no QGIS)."""

import csv
import glob
import os
import unicodedata

MIN_COLUMNS = 7


def _sort_key(row):
    """Sorts by name ignoring diacritics and case (Č after C, not after Z); the original name breaks ties."""
    name = row[0]
    stripped = "".join(c for c in unicodedata.normalize("NFD", name) if not unicodedata.combining(c))
    return stripped.casefold(), name, row[1], row[2]


def read_places(data_path, problems=None):
    """Reads <data_path>/kraje/*/places.csv (x;y;code;name;okres_code;okres;REGION, no header).

    Returns (names, coords, regions): three aligned lists sorted by name (ignoring diacritics
    and case). A name looks like "Ardovo (okres Rožňava)", coords like "x;y". No region folders
    give three empty lists. A file that cannot be read (not UTF-8, unreadable, malformed CSV)
    is skipped as a whole; when problems is a list, a (path, reason) tuple is appended for it.
    """
    rows = []
    pattern = os.path.join(data_path, "kraje", "*", "places.csv")
    for file_name in glob.glob(pattern):
        file_rows = []
        try:
            # utf-8-sig also accepts files saved with a byte-order mark (Excel "CSV UTF-8")
            with open(file_name, "r", encoding="utf-8-sig", newline="") as file_input:
                for row in csv.reader(file_input, delimiter=";"):
                    if not row or len(row) < MIN_COLUMNS:
                        continue
                    file_rows.append((row[3] + " (" + row[5] + ")", row[0] + ";" + row[1], row[6]))
        except (OSError, UnicodeDecodeError, csv.Error) as error:
            if problems is not None:
                problems.append((file_name, str(error)))
            continue
        rows.extend(file_rows)
    rows.sort(key=_sort_key)
    return [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]
