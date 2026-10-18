import unittest

from patrac_paths import default_data_path, settings_dir


class SettingsDirTest(unittest.TestCase):
    def test_appends_patrac_settings_to_profile(self):
        self.assertEqual(settings_dir("/p/profiles/default"), "/p/profiles/default/patrac_settings")

    def test_profile_with_trailing_slash(self):
        # QgsApplication.qgisSettingsDirPath() returns a trailing slash
        self.assertEqual(settings_dir("/p/profiles/default/"), "/p/profiles/default/patrac_settings")


class DefaultDataPathTest(unittest.TestCase):
    def test_default_is_patracdata_in_home_with_trailing_slash(self):
        self.assertEqual(default_data_path(environ={}, home="/Users/x"), "/Users/x/patracdata/")

    def test_env_variable_overrides_default(self):
        self.assertEqual(default_data_path(environ={"PATRAC_DATA": "/mnt/pd"}, home="/Users/x"), "/mnt/pd/")

    def test_empty_env_variable_is_ignored(self):
        self.assertEqual(default_data_path(environ={"PATRAC_DATA": ""}, home="/Users/x"), "/Users/x/patracdata/")


if __name__ == "__main__":
    unittest.main()
