# Running Patrac on macOS

## One-time setup
1. `brew install --cask qgis@ltr`. It must be QGIS **3.x**. The plain `qgis` cask is QGIS 4 (Qt6) and this plugin does not support it.
2. `source tools/dev/qgis_env.sh` finds the app and its Python.
3. `tools/dev/link_plugin.sh` links this repo into QGIS as the plugin `qgis_patrac`.
4. Start QGIS once with `tools/dev/run_qgis.sh`, then enable **Patrac** under Plugins > Manage and Install Plugins > Installed.

## Daily use
- Start QGIS with `tools/dev/run_qgis.sh`. Tracebacks print in that terminal.
- After editing code, reload the plugin. Install the "Plugin Reloader" plugin once (Plugins > Manage and Install Plugins > All), then click its button. If it misbehaves, restart QGIS.
- Data lives in `~/patracdata` (override with the `PATRAC_DATA` environment variable before starting QGIS).

## Environment notes
The `qgis@ltr` cask (QGIS 3.44.x, Python 3.12, Qt 5.15) installs to `/Applications/QGIS-LTR.app` and has a different layout from what older docs describe. `tools/dev/qgis_env.sh` accounts for this:
- QGIS's Python is `$QGIS_APP/Contents/MacOS/python` (a wrapper that sets `PYTHONHOME`), not `Contents/MacOS/bin/python3`.
- The `qgis` and `processing` Python packages and the bundled plugins live under `$QGIS_APP/Contents/Resources/qgis/python`, so `PYTHONPATH` points there.
- No `DYLD_FALLBACK_LIBRARY_PATH` was needed. `import processing` prints a harmless "Application path not initialized" line outside the GUI.

## Known import issues
Resolved: ui/gpxsource.ui was missing upstream (never committed); a minimal replacement dialog was recreated (radioButtonGps, radioButtonDisc, OK/Cancel). Replace it with the author's original if available.

## Extra Python packages (installed into QGIS's Python)
Run once: `"$QGIS_PY" -m pip install --user <packages>`
Packages needed: none. `requests` and `networkx` are already available in QGIS 3.44 LTR's Python.

## Running the tests
- Plain Python (path helper only): `python3 -m unittest discover -s tests -t . -v`
- Inside QGIS's Python (includes the import smoke test): `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest discover -s tests -t . -v`
