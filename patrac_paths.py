# -*- coding: utf-8 -*-
"""Locations used by the plugin. Pure Python so it can be tested without QGIS."""

import os

SETTINGS_DIR_NAME = "patrac_settings"


def settings_dir(profile_dir=None):
    """Folder with the user's Patrac settings, inside the QGIS profile directory."""
    if profile_dir is None:
        from qgis.core import QgsApplication
        profile_dir = QgsApplication.qgisSettingsDirPath()
    return os.path.join(profile_dir, SETTINGS_DIR_NAME)


def default_data_path(environ=None, home=None):
    """Folder with Patrac data (regions, projects). Always ends with a slash."""
    environ = os.environ if environ is None else environ
    home = os.path.expanduser("~") if home is None else home
    path = environ.get("PATRAC_DATA") or os.path.join(home, "patracdata")
    return os.path.join(path, "")
