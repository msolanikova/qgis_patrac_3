import os
import unittest

try:
    from qgis.PyQt import QtWidgets, uic
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

UI_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "gpxsource.ui")


@unittest.skipUnless(HAVE_QGIS, "needs QGIS's Python (source tools/dev/qgis_env.sh)")
class GpxSourceUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_form_has_the_widgets_ui_gpxsource_py_uses(self):
        form_class, _ = uic.loadUiType(UI_FILE)
        dialog = QtWidgets.QDialog()
        form = form_class()
        form.setupUi(dialog)
        self.assertIsInstance(form.radioButtonGps, QtWidgets.QRadioButton)
        self.assertIsInstance(form.radioButtonDisc, QtWidgets.QRadioButton)
        self.assertIsInstance(form.buttonBox, QtWidgets.QDialogButtonBox)

    def test_ok_button_accepts_the_dialog(self):
        form_class, _ = uic.loadUiType(UI_FILE)
        dialog = QtWidgets.QDialog()
        form = form_class()
        form.setupUi(dialog)
        form.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).click()
        self.assertEqual(dialog.result(), QtWidgets.QDialog.Accepted)


if __name__ == "__main__":
    unittest.main()
