import importlib
import os
import sys
import unittest

try:
    import qgis.core  # noqa: F401
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

from main.labels import label_sort_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)

LABELS = ["K142", "K20", "B1012", "B505", "C99", "C1000", "C868-599-140", "C868"]
EXPECTED = ["B505", "B1012", "C99", "C868", "C868-599-140", "C1000", "K20", "K142"]


class LabelSortKeyTest(unittest.TestCase):
    def test_letter_then_number_then_suffix(self):
        self.assertEqual(sorted(LABELS, key=label_sort_key), EXPECTED)

    def test_number_is_compared_as_integer(self):
        self.assertEqual(sorted(["K1042", "K142", "K20", "K2"], key=label_sort_key), ["K2", "K20", "K142", "K1042"])

    def test_suffixes_of_split_sectors_sort_as_strings_after_the_number(self):
        labels = ["K142_B", "K142", "K142_A", "K143", "K141"]
        self.assertEqual(sorted(labels, key=label_sort_key), ["K141", "K142", "K142_A", "K142_B", "K143"])
        labels = ["C868-600-146", "C868-599-140", "C868"]
        self.assertEqual(sorted(labels, key=label_sort_key), ["C868", "C868-599-140", "C868-600-146"])

    def test_labels_of_other_shapes_do_not_raise_and_sort_after_the_matching_ones(self):
        # "MIX", bare numbers (labels set from the id), grid labels without a parent, empty and missing labels
        labels = ["MIX", "12345", "599-140", "", None, "Z9", "A10"]
        result = sorted(labels, key=label_sort_key)
        self.assertEqual(result[:2], ["A10", "Z9"])
        self.assertEqual(sorted(result[2:], key=lambda x: x or ""), sorted(result[2:], key=lambda x: x or ""))
        self.assertEqual(set(result[2:]), {"MIX", "12345", "599-140", "", None})

    def test_non_matching_labels_sort_by_plain_string(self):
        self.assertEqual(sorted(["MIX", "12345", "599-140"], key=label_sort_key), ["12345", "599-140", "MIX"])


@unittest.skipUnless(HAVE_QGIS, "needs QGIS's Python (source tools/dev/qgis_env.sh)")
class GetLabelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.dirname(ROOT))
        cls.sectors = importlib.import_module(PACKAGE + ".main.sectors")

    def test_get_label_orders_features_naturally(self):
        features = [{"label": x} for x in LABELS]
        result = [f["label"] for f in sorted(features, key=self.sectors.get_label)]
        self.assertEqual(result, EXPECTED)


if __name__ == "__main__":
    unittest.main()
