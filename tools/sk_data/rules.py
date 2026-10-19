# -*- coding: utf-8 -*-
"""Land-use rules: OSM tags and ESA WorldCover classes -> sector type ('typ'), and typ -> plugin class."""

import json
from dataclasses import dataclass
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent / "rules"


@dataclass(frozen=True)
class Rules:
    osm: tuple          # rows {"key", "value", "typ", "status"}, first match wins
    worldcover: dict    # int class value -> typ
    classes: dict       # typ -> plugin class 1..10


def load_rules(rules_dir=RULES_DIR):
    rules_dir = Path(rules_dir)

    def read(name):
        with open(rules_dir / name, encoding="utf-8") as f:
            return json.load(f)

    return Rules(
        osm=tuple(read("osm_landuse.json")["rows"]),
        worldcover={int(k): v for k, v in read("worldcover.json")["classes"].items()},
        classes=read("classes.json"),
    )


def osm_typ(rules, tags):
    """Sector type for a dict of OSM tags, or None when no rule matches."""
    for row in rules.osm:
        value = tags.get(row["key"])
        if value is None:
            continue
        if row["value"] == "*" or value == row["value"]:
            return row["typ"]
    return None


def guessed_rows(rules):
    """OSM rows that are marked as guesses, for review."""
    return [r for r in rules.osm if r.get("status") == "guess"]


def check_rules(rules):
    """List of problems in the rules (empty when they are consistent)."""
    problems = []
    for row in rules.osm:
        if row["typ"] not in rules.classes:
            problems.append("OSM rule %s=%s -> unknown typ %s" % (row["key"], row["value"], row["typ"]))
        if row.get("status") not in ("verified", "guess"):
            problems.append("OSM rule %s=%s has status %r" % (row["key"], row["value"], row.get("status")))
    for cls, typ in rules.worldcover.items():
        if typ not in rules.classes:
            problems.append("WorldCover class %s -> unknown typ %s" % (cls, typ))
    for typ, cls in rules.classes.items():
        if not 1 <= cls <= 10:
            problems.append("typ %s has class %s outside 1..10" % (typ, cls))
    return problems


def guessed_rules_text(rules=None):
    """Human-readable list of the OSM mappings marked as guesses."""
    rules = rules or load_rules()
    lines = ["OSM mappings marked as guesses (check them against the ground):"]
    lines += ["  %s=%s -> %s" % (r["key"], r["value"], r["typ"]) for r in guessed_rows(rules)]
    return "\n".join(lines)
