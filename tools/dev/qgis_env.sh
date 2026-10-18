#!/usr/bin/env bash
# Source this file:  source tools/dev/qgis_env.sh
# Finds the QGIS 3 app bundle and exports paths used by the other dev scripts.

QGIS_APP="${QGIS_APP:-$(ls -d /Applications/QGIS-LTR.app /Applications/QGIS*.app 2>/dev/null | head -n1)}"
export QGIS_APP
export QGIS_PY="$QGIS_APP/Contents/MacOS/python"
export QGIS_PROFILE="$HOME/Library/Application Support/QGIS/QGIS3/profiles/default"
export QGIS_PLUGINS_DIR="$QGIS_PROFILE/python/plugins"
export PATRAC_DATA="${PATRAC_DATA:-$HOME/patracdata}"

# Lets QGIS's Python import qgis.*, processing and the bundled plugins when run from a terminal.
export PYTHONPATH="$QGIS_APP/Contents/Resources/qgis/python:$QGIS_APP/Contents/Resources/qgis/python/plugins${PYTHONPATH:+:$PYTHONPATH}"
