import os
import tempfile
import unicodedata
import unittest

from main.places import read_places


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class ReadPlacesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def region(self, name, text):
        write(os.path.join(self.root, "kraje", name, "places.csv"), text)

    def test_two_regions_are_merged_and_sorted_by_name_with_aligned_lists(self):
        self.region("ke", "-325630;-1257190;0;Ardovo;0;okres Rožňava;KE\n-262580;-1240038;0;Košice;0;okres Košice I;KE\n")
        self.region("ba", "-100;-200;0;Bratislava;0;okres Bratislava I;BA\n")
        names, coords, regions = read_places(self.root)
        self.assertEqual(names, ["Ardovo (okres Rožňava)", "Bratislava (okres Bratislava I)", "Košice (okres Košice I)"])
        self.assertEqual(coords, ["-325630;-1257190", "-100;-200", "-262580;-1240038"])
        self.assertEqual(regions, ["KE", "BA", "KE"])

    def test_name_coords_and_region_columns(self):
        self.region("ke", "-325630;-1257190;0;Ardovo;0;okres Rožňava;KE\n")
        self.assertEqual(read_places(self.root), (["Ardovo (okres Rožňava)"], ["-325630;-1257190"], ["KE"]))

    def test_short_and_blank_rows_are_skipped(self):
        self.region("ke", "\n-1;-2;0;Short;0;okres X\n;;\n-325630;-1257190;0;Ardovo;0;okres Rožňava;KE\n\n")
        names, coords, regions = read_places(self.root)
        self.assertEqual(names, ["Ardovo (okres Rožňava)"])
        self.assertEqual(coords, ["-325630;-1257190"])
        self.assertEqual(regions, ["KE"])

    def test_missing_kraje_folder_gives_three_empty_lists(self):
        self.assertEqual(read_places(self.root), ([], [], []))

    def test_empty_kraje_folder_gives_three_empty_lists(self):
        os.makedirs(os.path.join(self.root, "kraje"))
        self.assertEqual(read_places(self.root), ([], [], []))

    def test_region_folder_without_places_csv_gives_three_empty_lists(self):
        os.makedirs(os.path.join(self.root, "kraje", "ke"))
        self.assertEqual(read_places(self.root), ([], [], []))

    def test_other_files_are_ignored(self):
        write(os.path.join(self.root, "kraje", "ke", "notes.csv"), "-1;-2;0;Nope;0;okres X;KE\n")
        write(os.path.join(self.root, "kraje", "zpm.mbtiles"), "binary")
        write(os.path.join(self.root, "kraje", "places.csv"), "-1;-2;0;TopLevel;0;okres X;KE\n")
        self.region("ke", "-325630;-1257190;0;Ardovo;0;okres Rožňava;KE\n")
        names, _, _ = read_places(self.root)
        self.assertEqual(names, ["Ardovo (okres Rožňava)"])

    def test_data_path_with_and_without_trailing_slash(self):
        self.region("ke", "-325630;-1257190;0;Ardovo;0;okres Rožňava;KE\n")
        self.assertEqual(read_places(self.root), read_places(self.root + "/"))
        self.assertEqual(len(read_places(self.root + "/")[0]), 1)

    def test_non_ascii_names_survive(self):
        self.region("ke", "-1;-2;0;Šaľa;0;okres Šaľa;KE\n-3;-4;0;Košice;0;okres Košice I;KE\n")
        names, _, _ = read_places(self.root)
        self.assertEqual(sorted(names), sorted(["Šaľa (okres Šaľa)", "Košice (okres Košice I)"]))
        self.assertIn("Šaľa (okres Šaľa)", names)


class ReadPlacesRobustnessTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def path(self, region):
        return os.path.join(self.root, "kraje", region, "places.csv")

    def test_bad_files_are_skipped_and_reported_good_rows_survive(self):
        write(self.path("ke"), "-325630;-1257190;0;Ardovo;0;okres Rožňava;KE\n")
        os.makedirs(os.path.dirname(self.path("bad")))
        with open(self.path("bad"), "wb") as f:
            f.write(b"-1;-2;0;Partial;0;okres X;BAD\n\xff\xfe;;\n")
        os.makedirs(os.path.dirname(self.path("bom")))
        with open(self.path("bom"), "wb") as f:
            f.write("\ufeff-262580;-1240038;0;Košice;0;okres Košice I;BOM\n".encode("utf-8"))
        os.makedirs(self.path("dir"))  # a directory named places.csv: IsADirectoryError
        problems = []
        names, coords, regions = read_places(self.root, problems)
        self.assertEqual(names, ["Ardovo (okres Rožňava)", "Košice (okres Košice I)"])
        self.assertEqual(coords, ["-325630;-1257190", "-262580;-1240038"])  # BOM stripped
        self.assertEqual(regions, ["KE", "BOM"])
        self.assertEqual(sorted(p[0] for p in problems), sorted([self.path("bad"), self.path("dir")]))
        for path, reason in problems:
            self.assertIsInstance(reason, str)
            self.assertTrue(reason)

    def test_problems_argument_is_optional(self):
        write(self.path("ke"), "-325630;-1257190;0;Ardovo;0;okres Rožňava;KE\n")
        os.makedirs(self.path("dir"))
        self.assertEqual(read_places(self.root)[0], ["Ardovo (okres Rožňava)"])
        self.assertEqual(read_places(self.root, None)[0], ["Ardovo (okres Rožňava)"])

    def test_no_problems_leaves_list_empty(self):
        write(self.path("ke"), "-325630;-1257190;0;Ardovo;0;okres Rožňava;KE\n")
        problems = []
        read_places(self.root, problems)
        self.assertEqual(problems, [])

    def test_names_sort_ignoring_diacritics_and_case_with_aligned_lists(self):
        rows = [("Šaca", "1"), ("Zvolen", "2"), ("Sečovce", "3"), ("Cejkov", "4"), ("Čaňa", "5"), ("čierna", "6"), ("Žilina", "7")]
        write(self.path("ke"), "".join("%s;0;0;%s;0;okres X;KE\n" % (x, n) for n, x in rows))
        names, coords, regions = read_places(self.root)

        def key(name):
            stripped = "".join(c for c in unicodedata.normalize("NFD", name) if not unicodedata.combining(c))
            return (stripped.casefold(), name)

        expected = sorted((n + " (okres X)" for n, _ in rows), key=key)
        self.assertEqual(names, expected)
        self.assertEqual([n.split(" ")[0] for n in names],
                         ["Čaňa", "Cejkov", "čierna", "Šaca", "Sečovce", "Žilina", "Zvolen"])
        by_name = {n + " (okres X)": x + ";0" for n, x in rows}
        self.assertEqual(coords, [by_name[n] for n in names])
        self.assertEqual(regions, ["KE"] * len(rows))


if __name__ == "__main__":
    unittest.main()
