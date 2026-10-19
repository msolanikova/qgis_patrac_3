import os
import tempfile
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


if __name__ == "__main__":
    unittest.main()
