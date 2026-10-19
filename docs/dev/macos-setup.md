# Running Patrac on macOS

## One-time setup
1. `brew install --cask qgis@ltr`. It must be QGIS **3.x**. The plain `qgis` cask is QGIS 4 (Qt6) and this plugin does not support it.
2. `source tools/dev/qgis_env.sh` finds the app and its Python.
3. `tools/dev/link_plugin.sh` links this repo into QGIS as the plugin `qgis_patrac`.
4. Start QGIS once with `tools/dev/run_qgis.sh`, then enable **Patrac** under Plugins > Manage and Install Plugins > Installed. On this first start with the default profile macOS may show a Keychain prompt, or QGIS may ask you to set a master password for its authentication database. Click "Allow", or cancel the master-password dialog. The headless smoke test avoids this only because it uses a throw-away profile.

## Daily use
- Start QGIS with `tools/dev/run_qgis.sh`. Tracebacks print in that terminal.
- After editing code, reload the plugin. Install the "Plugin Reloader" plugin once (Plugins > Manage and Install Plugins > All), then click its button. If it misbehaves, restart QGIS.
- Data lives in `~/patracdata`. The `PATRAC_DATA` environment variable is read only when the plugin first creates `<profile>/patrac_settings/config/config.json` (via `createDefaultConfig` in `patrac.py`). Afterwards the `data_path` value in that file wins. To move the data folder later, edit `data_path` in `config.json` (the file is in your QGIS profile; use a trailing slash).

## Environment notes
The `qgis@ltr` cask (QGIS 3.44.x, Python 3.12, Qt 5.15) installs to `/Applications/QGIS-LTR.app` and differs from the layout assumed in the original plan. `tools/dev/qgis_env.sh` accounts for this:
- QGIS's Python is `$QGIS_APP/Contents/MacOS/python` (a wrapper that sets `PYTHONHOME`), not `Contents/MacOS/bin/python3`.
- The `qgis` package is inside the app's Python framework (`/Applications/QGIS-LTR.app/Contents/Frameworks/lib/python3.12/site-packages/qgis`), which QGIS's own Python finds without help. Only `processing` and the bundled plugins (`plugins/`), plus `console` and `pyplugin_installer`, live under `$QGIS_APP/Contents/Resources/qgis/python`, which is why `PYTHONPATH` adds those entries.
- `qgis_env.sh` also exports `PROJ_LIB` / `PROJ_DATA` (`$QGIS_APP/Contents/Resources/qgis/proj`) and `GDAL_DATA` (`.../qgis/gdal`). Without them, QGIS's Python run from a terminal prints `PROJ: proj_create_from_database: Cannot find proj.db` and `QgsCoordinateTransform(EPSG:4326 -> EPSG:5514).isValid()` is False (this is a real failure, not a harmless warning) until `QgsApplication.initQgis()` runs. The QGIS app itself finds its PROJ data without these variables. The exports are made by every script that sources `qgis_env.sh`, including `run_qgis.sh`; that is harmless there, since they point at the app's own bundled data.
- No `DYLD_FALLBACK_LIBRARY_PATH` was needed. `import processing` prints a harmless "Application path not initialized" line outside the GUI.

## Recreated files
`ui/gpxsource.ui` was missing upstream (never committed); a minimal replacement dialog was recreated (`radioButtonGps`, `radioButtonDisc`, OK/Cancel). Replace it with the author's original if available.

## Extra Python packages (installed into QGIS's Python)
Run once (`run_qgis.sh` sources the env only in its own subshell, so source it in your shell first): `source tools/dev/qgis_env.sh && "$QGIS_PY" -m pip install --user <packages>`
Packages needed: none. `requests` and `networkx` are already available in QGIS 3.44 LTR's Python.

## Running the tests
- Plain Python (path helper only): `python3 -m unittest discover -s tests -t . -v`
- Inside QGIS's Python (includes the import smoke test): `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest discover -s tests -t . -v`

## Headless smoke test
`tools/dev/headless_smoke.sh` starts the real QGIS binary offscreen (no window) with a throw-away profile in a temp folder, enables the plugin, runs `tools/dev/headless_smoke.py` and quits. It prints `SMOKE PASS/FAIL` lines and exits 0 only if all pass (120 s hard limit). The command it runs is essentially:
```bash
source tools/dev/qgis_env.sh
QT_QPA_PLATFORM=offscreen "$QGIS_APP/Contents/MacOS/QGIS" --nologo --profiles-path <tmp> --code tools/dev/headless_smoke.py
```
The throw-away profile sets `[auth] use_password_helper=false`, because a fresh profile otherwise blocks forever on a macOS keychain prompt for the QGIS master password. Harmless offscreen noise: `createPlatformOpenGLContext`, `propagateSizeHints`, `insertAction: Attempt to insert null action`, and debugpy's "frozen modules" notice.

## Debugging in VS Code
1. Start QGIS with `tools/dev/run_qgis.sh` (this puts `QGIS_PY` in QGIS's environment).
2. One-time: `source tools/dev/qgis_env.sh && "$QGIS_PY" -m pip install --user debugpy` (`run_qgis.sh` sources the env only in its own subshell, so your own shell needs it sourced).
3. In QGIS: Plugins > Python Console > Show Editor, open `tools/dev/debug_attach.py`, Run.
4. In VS Code: Run and Debug > "Attach to QGIS (debugpy)". Breakpoints in `*.py` files of this repo now work.
For PyCharm / IntelliJ use a "Python Debug Server" configuration with `pydevd-pycharm` instead of `debugpy`.

## Python interpreter for the IDE
In VS Code use "Python: Select Interpreter" and enter `/Applications/QGIS-LTR.app/Contents/MacOS/python`, so that `qgis.*` imports resolve. `processing` and the bundled plugins live in `/Applications/QGIS-LTR.app/Contents/Resources/qgis/python/plugins`, which must be added through the `python.analysis.extraPaths` setting (Pylance). The checked-in `.vscode/settings.json` already sets both `python.defaultInterpreterPath` and `python.analysis.extraPaths`; if you use a different QGIS app path, change them in `.vscode/settings.json` or in your workspace settings.

## What is checked in
`config/` must exist (the plugin writes `config/lastprojectpath.txt` there). It is created by git via `config/.gitkeep`.

## Manual verification checklist (do once)
These need a human at the screen; the automated parts are covered by `tools/dev/headless_smoke.sh`.
1. Dock panel: start `tools/dev/run_qgis.sh` (on the first start with the default profile macOS may show a Keychain prompt, or QGIS may ask to set a master password for its authentication database: click "Allow" or cancel the master-password dialog), enable **Patrac** (Plugins > Manage and Install Plugins > Installed), then click the Patrac toolbar button / menu entry. Expected: the Patrac dock widget appears next to the Layers panel and the terminal shows no traceback.
2. Breakpoint: open `patrac.py` in VS Code and set a breakpoint on the first line of `showWidget` (`grep -n "def showWidget" patrac.py`). In QGIS run `tools/dev/debug_attach.py` from the Python console editor (expected output: `debugpy listening on 127.0.0.1:5678 - attach from the IDE`). In VS Code run "Attach to QGIS (debugpy)". In QGIS click the Patrac toolbar button. Expected: VS Code stops on the breakpoint; Continue resumes and the dock appears. If it does not stop, check that the listening line was printed and that the `remoteRoot` in `.vscode/launch.json` equals the symlink path (`ls -l "$QGIS_PLUGINS_DIR"`). If breakpoints show as unbound (grey), remove `pathMappings` from `.vscode/launch.json` and try again.

## Test the plugin with Slovak data

The plugin lists municipalities from `~/patracdata/kraje/*/places.csv`; build a region with the pipeline described in `docs/dev/sk-data.md`. When no ZPM map is configured (`kraje/zpm.mbtiles` is missing), a new search gets an OpenStreetMap basemap instead. Start QGIS with the plugin using `tools/dev/run_qgis.sh`.
