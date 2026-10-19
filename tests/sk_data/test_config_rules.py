import ast
import unittest
from pathlib import Path

from tools.sk_data.config import MARGIN_M, REGIONS, SectorSize, data_root, region_dir, source_dir
from tools.sk_data.rules import check_rules, guessed_rows, load_rules, osm_typ

REPO = Path(__file__).resolve().parents[2]


class ConfigTest(unittest.TestCase):
    def test_regions_cover_the_eight_kraje(self):
        self.assertEqual(sorted(REGIONS), ["ba", "bb", "ke", "nr", "po", "tn", "tt", "za"])
        self.assertEqual(REGIONS["ke"], "Košický kraj")

    def test_sector_size_defaults_are_the_user_request(self):
        s = SectorSize()
        self.assertEqual((s.min_ha, s.target_ha, s.max_ha), (6.0, 7.0, 8.0))
        self.assertEqual(s.max_m2, 80000.0)
        self.assertEqual(s.min_m2, 60000.0)

    def test_sector_size_rejects_inconsistent_values(self):
        with self.assertRaises(ValueError):
            SectorSize(min_ha=9.0, target_ha=7.0, max_ha=8.0)

    def test_paths(self):
        self.assertEqual(data_root(environ={"PATRAC_DATA": "/x/pd"}, home="/h"), "/x/pd")
        self.assertEqual(data_root(environ={}, home="/h"), "/h/patracdata")
        self.assertEqual(source_dir("/r", "osm"), "/r/source/osm")
        self.assertEqual(region_dir("/r", "ke"), "/r/kraje/ke")
        self.assertEqual(MARGIN_M, 800.0)


class RulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules()

    def test_rules_are_consistent(self):
        self.assertEqual(check_rules(self.rules), [])

    def test_osm_examples(self):
        r = self.rules
        self.assertEqual(osm_typ(r, {"landuse": "forest"}), "LPSTROM")
        self.assertEqual(osm_typ(r, {"natural": "wood"}), "LPSTROM")
        self.assertEqual(osm_typ(r, {"landuse": "farmland", "natural": "wood"}), "ORNAPU")  # first matching row wins
        self.assertEqual(osm_typ(r, {"water": "lake"}), "VODPLO")                          # '*' matches any value
        self.assertIsNone(osm_typ(r, {"highway": "residential"}))

    def test_worldcover_covers_every_class_value(self):
        self.assertEqual(sorted(self.rules.worldcover), [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100])
        self.assertEqual(self.rules.worldcover[10], "LPSTROM")

    def test_guesses_are_listed_for_review(self):
        guesses = {(r["key"], r["value"]) for r in guessed_rows(self.rules)}
        self.assertIn(("natural", "wetland"), guesses)
        self.assertNotIn(("landuse", "forest"), guesses)

    def test_classes_match_the_plugin_report_code(self):
        """classes.json must agree with the `types` table in main/sectors.py getReportItems."""
        tree = ast.parse((REPO / "main" / "sectors.py").read_text(encoding="utf-8"))
        func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "getReportItems")
        assign = next(n for n in ast.walk(func) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "types")
        plugin = {}
        for cls, codes in enumerate(ast.literal_eval(assign.value), start=1):
            for code in codes:
                plugin[code] = cls
        self.assertEqual(self.rules.classes, plugin)

    def test_guess_report_text(self):
        from tools.sk_data.rules import guessed_rules_text
        text = guessed_rules_text()
        self.assertIn("natural=wetland -> MAZCHU", text)
        self.assertNotIn("landuse=forest", text)


if __name__ == "__main__":
    unittest.main()
