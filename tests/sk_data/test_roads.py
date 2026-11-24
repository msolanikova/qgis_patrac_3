import unittest

from tools.sk_data import roads


def tags(highway=None, **extra):
    result = dict(extra)
    if highway is not None:
        result["highway"] = highway
    return result


class ClassifyTest(unittest.TestCase):
    def check(self, cases):
        for given, expected in cases:
            with self.subTest(tags=given):
                self.assertIs(roads.classify(given), expected)

    def test_highway_values(self):
        good = ["residential", "unclassified", "tertiary", "service", "living_street", "cycleway", "footway"]
        worse = ["track", "path", "bridleway"]
        none = ["motorway", "trunk", "primary", "secondary", "tertiary_link", "secondary_link", "steps",
                "construction"]
        self.check([(tags(h), False) for h in good] + [(tags(h), True) for h in worse]
                   + [(tags(h), None) for h in none] + [({}, None), ({"waterway": "stream"}, None)])

    def test_surface(self):
        self.check([
            (tags("residential", surface="gravel"), True),
            (tags("residential", surface="asphalt"), False),
            (tags("residential", surface="asphalt;gravel"), True),
            (tags("residential", surface="asphalt;paved"), False),
            (tags("residential", surface="asphalt; gravel"), True),
            (tags("track", surface="asphalt", tracktype="grade1"), True),
        ])

    def test_excluded_by_tags(self):
        self.check([
            (tags("residential", tunnel="yes"), None),
            (tags("residential", tunnel="culvert"), None),
            (tags("footway", footway="sidewalk"), None),
            (tags("footway", footway="crossing"), None),
            (tags("service", service="driveway"), None),
            (tags("service", service="parking_aisle"), None),
            (tags("track", access="private"), None),
            (tags("track", access="no"), None),
            (tags("track", access="yes"), True),
            (tags("service", service="alley"), False),
            (tags("footway", footway="path"), False),
        ])

    def test_display_name(self):
        self.assertEqual(roads.display_name({"name": "Hlavná", "ref": "III/3345"}), "Hlavná")
        self.assertEqual(roads.display_name({"ref": "III/3345"}), "III/3345")
        self.assertIsNone(roads.display_name({}))
        self.assertEqual(roads.display_name({"name": "", "ref": "III/3345"}), "III/3345")
        self.assertIsNone(roads.display_name({"name": ""}))


if __name__ == "__main__":
    unittest.main()
