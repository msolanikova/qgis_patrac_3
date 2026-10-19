import json
import os
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEW_TYPES = {
    "AREZAS": "#bdbdbd",
    "ARUCZA": "#7b7b7b",
    "HRBITO": "#8c6bb1",
    "ZAHPAR": "#41ab5d",
    "SADZAH": "#f4a582",
    "MAZCHU": "#41b6c4",
}

NEW_LABELS = {
    "cs": {"AREZAS": "Zastavěná plocha", "ARUCZA": "Průmyslová a účelová plocha", "HRBITO": "Hřbitov",
           "ZAHPAR": "Park a sportoviště", "SADZAH": "Sad, zahrada", "MAZCHU": "Mokřad"},
    "en": {"AREZAS": "Built-up area", "ARUCZA": "Industrial and institutional area", "HRBITO": "Cemetery",
           "ZAHPAR": "Park, sports ground", "SADZAH": "Orchard, garden", "MAZCHU": "Wetland"},
    "uk": {"AREZAS": "Забудована територія", "ARUCZA": "Промислова та інституційна територія", "HRBITO": "Цвинтар",
           "ZAHPAR": "Парк, спортмайданчик", "SADZAH": "Сад, город", "MAZCHU": "Болото"},
}

OLD_TYPES = ["ELEKTR", "INTRAV", "KOLEJI", "LETISTE", "LPKOSO", "LPKROV", "LPSTROM", "ODPOCI", "ORNAPU", "POTELO",
             "SKLADK", "TRTRPO", "ULOMIS", "VINICE", "VODPLO"]


def pipeline_types():
    """Every typ the data pipeline can write into the sectors layer (OTHER is meant to fall into the catch-all category)."""
    rules = os.path.join(ROOT, "tools", "sk_data", "rules")
    with open(os.path.join(rules, "osm_landuse.json"), encoding="utf-8") as f:
        types = {row["typ"] for row in json.load(f)["rows"]}
    with open(os.path.join(rules, "worldcover.json"), encoding="utf-8") as f:
        types |= set(json.load(f)["classes"].values())
    types.add("AREZAS")
    types.discard("OTHER")
    return types


def hex_to_rgb(colour):
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


class SectorsUniqueStyleTest(unittest.TestCase):
    def load(self, lang):
        tree = ET.parse(os.path.join(ROOT, "styles", "sectors_unique_%s.qml" % lang))
        renderer = tree.getroot().find("renderer-v2")
        self.assertEqual(renderer.get("type"), "categorizedSymbol")
        self.assertEqual(renderer.get("attr"), "typ")
        categories = renderer.find("categories").findall("category")
        symbols = {s.get("name"): s for s in renderer.find("symbols").findall("symbol")}
        return categories, symbols

    def test_every_pipeline_type_has_a_category(self):
        for lang in NEW_LABELS:
            with self.subTest(lang=lang):
                categories, _ = self.load(lang)
                values = {c.get("value") for c in categories}
                self.assertEqual(sorted(pipeline_types() - values), [])

    def test_existing_categories_are_kept_and_other_stays_last(self):
        for lang in NEW_LABELS:
            with self.subTest(lang=lang):
                categories, _ = self.load(lang)
                values = [c.get("value") for c in categories]
                self.assertEqual(values[:len(OLD_TYPES)], OLD_TYPES)
                self.assertEqual(values[-1], "")

    def test_every_category_references_an_existing_symbol_once(self):
        for lang in NEW_LABELS:
            with self.subTest(lang=lang):
                categories, symbols = self.load(lang)
                refs = [c.get("symbol") for c in categories]
                self.assertEqual([r for r in refs if r not in symbols], [])
                self.assertEqual(len(refs), len(set(refs)), "two categories share a symbol")
                self.assertEqual(len(values_unique(categories)), len(categories))

    def test_new_symbols_have_the_expected_colour(self):
        for lang in NEW_LABELS:
            with self.subTest(lang=lang):
                categories, symbols = self.load(lang)
                by_value = {c.get("value"): c for c in categories}
                for typ, colour in NEW_TYPES.items():
                    symbol = symbols[by_value[typ].get("symbol")]
                    layer = symbol.find("layer")
                    props = {p.get("k"): p.get("v") for p in layer.findall("prop")}
                    props.update({o.get("name"): o.get("value") for o in layer.iter("Option") if o.get("name")})
                    r, g, b, a = (int(x) for x in props["color"].split(","))
                    self.assertEqual((r, g, b), hex_to_rgb(colour), typ)
                    self.assertEqual(a, 255, typ)
                    # Outline is the same as in the existing categories.
                    old = symbols[by_value["ELEKTR"].get("symbol")].find("layer")
                    old_props = {p.get("k"): p.get("v") for p in old.findall("prop")}
                    for key in ("outline_color", "outline_style", "outline_width", "outline_width_unit", "style", "joinstyle"):
                        self.assertEqual(props[key], old_props[key], "%s %s" % (typ, key))

    def test_new_labels(self):
        for lang, labels in NEW_LABELS.items():
            with self.subTest(lang=lang):
                categories, _ = self.load(lang)
                by_value = {c.get("value"): c.get("label") for c in categories}
                for typ, label in labels.items():
                    self.assertEqual(by_value[typ], label)


def values_unique(categories):
    return {c.get("value") for c in categories}


if __name__ == "__main__":
    unittest.main()
