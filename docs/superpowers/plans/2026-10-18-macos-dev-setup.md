# macOS Dev Setup Implementation Plan (sub-project 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Patrac plugin load in QGIS on macOS, run from this git checkout, with a working IDE debugger attach and no import errors.

**Architecture:** Install the Qt5-based QGIS 3 LTR. Symlink this repo into the QGIS profile's plugin folder. The plugin builds its settings path as `<plugin dir>/../../../patrac_settings`, which breaks through a symlink (the OS resolves `..` after following the link). So all of those paths move into one helper module, `patrac_paths.py`, which asks QGIS for the profile directory. The default data folder also becomes `~/patracdata`, because the current code falls back to an empty string and then tries to create `doc/` in the process's working directory (`/` on macOS), which fails.

**Tech Stack:** QGIS 3.44 LTR (Homebrew cask `qgis@ltr`), QGIS's bundled Python 3, `unittest` (stdlib, so the same tests run in plain Python and in QGIS Python), `debugpy`, VS Code.

**Spec:** [docs/superpowers/specs/2026-10-18-slovakia-macos-port-design.md](../specs/2026-10-18-slovakia-macos-port-design.md), sub-project 1.

## Global Constraints

- Work only on branch `feature/slovakia-macos-port`. Never commit to `master`. Never push or merge.
- Every commit message ends with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- QGIS must be a **3.x** release. The plugin uses Qt5 idioms (`QMessageBox.Yes`, `exec_()`, `from PyQt5...`) that break on QGIS 4 / Qt6. The Homebrew cask `qgis` is 4.x, so use `qgis@ltr`.
- `qgisMinimumVersion=3.26` in `metadata.txt` stays unchanged.
- Keep EPSG:5514. Do not touch the Czech data or basemap code in this plan (that is sub-project 3).
- Do not delete the HS ČR / handler code (that is sub-project 3).
- Tests use `unittest` only, no `pytest`, so they run under QGIS's bundled Python.
- No UI translation work. English and Czech are sufficient.

## File Structure

| File | Responsibility |
|---|---|
| `tools/dev/qgis_env.sh` (create) | Sourced by other scripts. Finds the QGIS app, its Python, the profile and plugin folders. |
| `tools/dev/link_plugin.sh` (create) | Symlinks the repo into the QGIS plugin folder as `qgis_patrac`. |
| `tools/dev/run_qgis.sh` (create) | Starts QGIS from a terminal so tracebacks print there. |
| `tools/dev/debug_attach.py` (create) | Snippet run in the QGIS Python console to open a `debugpy` port. |
| `patrac_paths.py` (create) | `settings_dir()` and `default_data_path()`. Pure Python, no QGIS import at module load. |
| `tests/__init__.py` (create) | Makes `tests` a package so `unittest discover` works. |
| `tests/test_patrac_paths.py` (create) | Unit tests for `patrac_paths`. |
| `tests/test_imports.py` (create) | Imports every plugin module under QGIS Python. Skipped without QGIS. |
| `patrac.py`, `patracdockwidget.py`, `main/*.py`, `ui/*.py` (modify) | Replace `.../../../patrac_settings` string building with `settings_dir()`. |
| `config/.gitkeep`, `.gitignore` (modify) | The plugin writes `config/lastprojectpath.txt`, so the folder must exist. |
| `.vscode/launch.json` (create) | VS Code "attach to QGIS" configuration. |
| `docs/dev/macos-setup.md` (create) | Setup, run and debug instructions. |
| `docs/dev/qgis-for-python-devs.md` (create) | Glossary of GIS terms for a Python developer. |

---

### Task 1: Install QGIS LTR and create the environment scripts

**Files:**
- Create: `tools/dev/qgis_env.sh`, `tools/dev/link_plugin.sh`, `tools/dev/run_qgis.sh`, `docs/dev/macos-setup.md`

**Interfaces:**
- Produces: `source tools/dev/qgis_env.sh` exports `QGIS_APP`, `QGIS_PY`, `QGIS_PROFILE`, `QGIS_PLUGINS_DIR`, `PATRAC_DATA`, `PYTHONPATH` (QGIS's python dirs prepended). Later tasks run `"$QGIS_PY" ...` after sourcing it.

- [ ] **Step 1: Confirm the branch**

Run: `git branch --show-current`
Expected: `feature/slovakia-macos-port`

- [ ] **Step 2: Install QGIS LTR**

This downloads about 1 GB and needs the user's go-ahead before running.

Run: `brew install --cask qgis@ltr`
Expected: ends with `qgis@ltr was successfully installed!`

Then run: `ls -d /Applications/QGIS*.app`
Expected: one path, probably `/Applications/QGIS-LTR.app`. Use whatever it prints below.

- [ ] **Step 3: Write `tools/dev/qgis_env.sh`**

```bash
#!/usr/bin/env bash
# Source this file:  source tools/dev/qgis_env.sh
# Finds the QGIS 3 app bundle and exports paths used by the other dev scripts.

QGIS_APP="${QGIS_APP:-$(ls -d /Applications/QGIS-LTR.app /Applications/QGIS*.app 2>/dev/null | head -n1)}"
export QGIS_APP
export QGIS_PY="$QGIS_APP/Contents/MacOS/bin/python3"
export QGIS_PROFILE="$HOME/Library/Application Support/QGIS/QGIS3/profiles/default"
export QGIS_PLUGINS_DIR="$QGIS_PROFILE/python/plugins"
export PATRAC_DATA="${PATRAC_DATA:-$HOME/patracdata}"

# Lets QGIS's Python import qgis.*, processing and the bundled plugins when run from a terminal.
export PYTHONPATH="$QGIS_APP/Contents/Resources/python:$QGIS_APP/Contents/Resources/python/plugins${PYTHONPATH:+:$PYTHONPATH}"
```

- [ ] **Step 4: Verify QGIS's Python can import `qgis`**

Run:
```bash
source tools/dev/qgis_env.sh
"$QGIS_PY" -c "from qgis.core import Qgis; print(Qgis.version())"
```
Expected: prints a version starting with `3.` (for example `3.44.15-...`).

If `QGIS_PY` does not exist, run `find "$QGIS_APP" -maxdepth 5 -name 'python3*' -path '*bin*'`, put the correct path into `qgis_env.sh`, and rerun. If the import fails with a library error, add `export DYLD_FALLBACK_LIBRARY_PATH="$QGIS_APP/Contents/MacOS/lib"` to `qgis_env.sh` and rerun. Record whichever fix was needed in `docs/dev/macos-setup.md` (Step 7).

- [ ] **Step 5: Write `tools/dev/link_plugin.sh`**

The link name `qgis_patrac` matters: the plugin's translation lookup uses `.../python/plugins/qgis_patrac`.

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/qgis_env.sh"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$QGIS_PLUGINS_DIR"
ln -sfn "$REPO" "$QGIS_PLUGINS_DIR/qgis_patrac"
ls -ld "$QGIS_PLUGINS_DIR/qgis_patrac"
```

Run: `chmod +x tools/dev/*.sh && tools/dev/link_plugin.sh`
Expected: a line like `lrwxr-xr-x ... qgis_patrac -> /Users/marketasolanikova/Development/qgis_patrac_3`

- [ ] **Step 6: Write `tools/dev/run_qgis.sh`**

Starting QGIS from a terminal prints Python tracebacks there, which is far easier than the in-app log.

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/qgis_env.sh"
QGIS_BIN="$(ls "$QGIS_APP"/Contents/MacOS/QGIS* | head -n1)"
exec "$QGIS_BIN" "$@"
```

Run: `chmod +x tools/dev/run_qgis.sh`

- [ ] **Step 7: Write `docs/dev/macos-setup.md`**

```markdown
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
(Record here any fix that was needed to make `"$QGIS_PY" -c "from qgis.core import Qgis"` work.)
```

Replace the parenthesised line under "Environment notes" with the actual fix from Step 4, or with the sentence `No extra fixes were needed.` if none were.

- [ ] **Step 8: Commit**

```bash
git add tools/dev docs/dev/macos-setup.md
git commit -m "Add macOS dev environment scripts for QGIS 3 LTR

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The `patrac_paths` helper (TDD)

**Files:**
- Create: `patrac_paths.py`, `tests/__init__.py`, `tests/test_patrac_paths.py`

**Interfaces:**
- Produces: `settings_dir(profile_dir: str | None = None) -> str` returns `<profile>/patrac_settings` with no trailing slash. With `None` it asks `QgsApplication.qgisSettingsDirPath()`.
- Produces: `default_data_path(environ: dict | None = None, home: str | None = None) -> str` returns the data folder **with a trailing slash**. It is `$PATRAC_DATA` if set, otherwise `<home>/patracdata`.

- [ ] **Step 1: Create the package marker**

Run: `touch tests/__init__.py`

- [ ] **Step 2: Write the failing tests** in `tests/test_patrac_paths.py`

```python
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
```

- [ ] **Step 3: Run to verify they fail**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: `ModuleNotFoundError: No module named 'patrac_paths'`

- [ ] **Step 4: Write `patrac_paths.py`**

```python
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
```

- [ ] **Step 5: Run to verify they pass**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: `Ran 5 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add patrac_paths.py tests
git commit -m "Add patrac_paths helper for settings and data locations

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Import smoke test and baseline

**Files:**
- Create: `tests/test_imports.py`
- Modify: `docs/dev/macos-setup.md`

**Interfaces:**
- Consumes: `QGIS_PY` and the environment from Task 1.
- Produces: `tests/test_imports.py`, which later tasks rerun with `"$QGIS_PY" -m unittest discover -s tests -t . -v`.

- [ ] **Step 1: Write `tests/test_imports.py`**

```python
import glob
import importlib
import os
import sys
import unittest

try:
    import qgis.core  # noqa: F401
    HAVE_QGIS = True
except ImportError:
    HAVE_QGIS = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.basename(ROOT)  # the repo folder is itself an importable package


def module_names():
    names = []
    for sub, pattern in (("", "*.py"), ("main", "*.py"), ("ui", "*.py"), ("connect", "*.py")):
        for path in sorted(glob.glob(os.path.join(ROOT, sub, pattern))):
            base = os.path.splitext(os.path.basename(path))[0]
            if base == "__init__":
                continue
            names.append(".".join(p for p in (PACKAGE, sub, base) if p))
    return names


@unittest.skipUnless(HAVE_QGIS, "needs QGIS's Python (source tools/dev/qgis_env.sh)")
class ImportAllModulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.dirname(ROOT))

    def test_every_module_imports(self):
        for name in module_names():
            with self.subTest(module=name):
                importlib.import_module(name)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run under QGIS's Python to get the baseline**

Run:
```bash
source tools/dev/qgis_env.sh
QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest discover -s tests -t . -v 2>&1 | tail -40
```
Expected: either `OK`, or failures listed per module with `ModuleNotFoundError` lines. Record the list.

- [ ] **Step 3: Fix missing third-party modules only**

For each `No module named 'X'`:
- `requests`: `"$QGIS_PY" -m pip install --user requests`
- `networkx`: `"$QGIS_PY" -m pip install --user networkx`
- If `pip` itself is missing: `"$QGIS_PY" -m ensurepip --user` and retry.

Rerun Step 2 until the only remaining failures (if any) are not "missing module" errors. For any other failure (syntax, attribute, Qt6-style errors), do not patch around it here. Write it down in `docs/dev/macos-setup.md` under a new heading `## Known import issues`, with module name and error line, and tell the user.

- [ ] **Step 4: Document installed extras**

Append to `docs/dev/macos-setup.md`:

```markdown
## Extra Python packages (installed into QGIS's Python)
Run once: `"$QGIS_PY" -m pip install --user <packages>`
Packages needed: (list exactly those installed in Step 3, or write "none")

## Running the tests
- Plain Python (path helper only): `python3 -m unittest discover -s tests -t . -v`
- Inside QGIS's Python (includes the import smoke test): `source tools/dev/qgis_env.sh && QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest discover -s tests -t . -v`
```

Replace the parenthesised placeholder in "Packages needed" with the real list.

- [ ] **Step 5: Commit**

```bash
git add tests/test_imports.py docs/dev/macos-setup.md
git commit -m "Add import smoke test for all plugin modules

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Replace the `../../../patrac_settings` paths and the data-path fallback

**Files:**
- Modify: about 20 files in `patrac.py`, `patracdockwidget.py`, `main/`, `ui/` (found by grep, see Step 1)
- Create: `config/.gitkeep`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `settings_dir()` and `default_data_path()` from Task 2.
- Produces: no code in the plugin builds a path with `/../../../` any more. `PatracPlugin.profilePath` keeps its meaning (profile directory with trailing slash).

- [ ] **Step 1: List every occurrence**

Run: `grep -rn '\.\./\.\./\.\./' --include='*.py' . | grep -v 'chinese/lib'`
Expected: about 45 lines. All are either `<plugin path expression> + "/../../../patrac_settings..."`, the `profilePath` line in `patrac.py:94`, or two data-path lines (`main/sectors.py:243`, `main/utils.py:290`) that are relative to a **project** folder, not the plugin, and must be left alone.

- [ ] **Step 2: Write the rewrite script** (temporary; it is deleted in Step 4)

Create `tools/dev/_rewrite_settings_paths.py`:

```python
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXPR = r'(?:self\.(?:widget\.)?)?(?:pluginPath|PLUGIN_PATH|getPluginPath\(\))'
WHOLE = re.compile(EXPR + r'\s*\+\s*"/\.\./\.\./\.\./patrac_settings"')
PREFIX = re.compile(EXPR + r'\s*\+\s*"/\.\./\.\./\.\./patrac_settings/')
FIRST_IMPORT = re.compile(r'^(?:import|from) ', re.M)

changed = []
for path in sorted(ROOT.rglob("*.py")):
    rel = path.relative_to(ROOT)
    if rel.parts[0] in ("chinese", "tools", "tests", "dron", "utils", "i18n", "ptrack"):
        continue
    text = path.read_text(encoding="utf-8")
    new = WHOLE.sub("settings_dir()", text)
    new = PREFIX.sub('settings_dir() + "/', new)
    if new == text:
        continue
    dots = "." if len(rel.parts) == 1 else ".."
    import_line = "from %s.patrac_paths import settings_dir\n" % dots
    match = FIRST_IMPORT.search(new)
    new = new[:match.start()] + import_line + new[match.start():]
    path.write_text(new, encoding="utf-8")
    changed.append(str(rel))

print("\n".join(changed))
```

- [ ] **Step 3: Run it and check the result**

Run: `python3 -I tools/dev/_rewrite_settings_paths.py`
Expected: a list of the changed files (about 20). Then:

Run: `grep -rn 'patrac_settings' --include='*.py' . | grep '\.\./' | grep -v chinese/lib`
Expected: no output.

Run: `git diff --stat | tail -3` and read the diff of `patrac.py`, `main/utils.py` and `ui/ui_settings.py` (`git diff <file>`). Confirm every changed line only swapped the path expression for `settings_dir()` and that each file got exactly one new import line placed before its first import. If a pattern was missed or an import landed somewhere wrong, fix by hand.

- [ ] **Step 4: Delete the temporary script**

Run: `rm tools/dev/_rewrite_settings_paths.py`

- [ ] **Step 5: Fix `profilePath` and the data path in `patrac.py`**

Edit `patrac.py`, line with `self.profilePath = self.pluginPath + "/../../../"`:

```python
        self.profilePath = os.path.join(QgsApplication.qgisSettingsDirPath(), "")
```

Replace the whole body of `getPatracDataPath` (from `letters = ...` to `return ''`) with:

```python
        return default_data_path()
```

`patrac.py` had no `.../../../patrac_settings` expression, so the script did not touch it. Add this line directly before its first import line (`import os, subprocess, sys, json`):

```python
from .patrac_paths import default_data_path
```

- [ ] **Step 6: Create the `config` folder the plugin writes to**

```bash
mkdir -p config && touch config/.gitkeep
printf '\nconfig/lastprojectpath.txt\n' >> .gitignore
```

- [ ] **Step 7: Run the checks**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 5 tests OK (the import test is skipped).

Run:
```bash
source tools/dev/qgis_env.sh
QT_QPA_PLATFORM=offscreen "$QGIS_PY" -m unittest discover -s tests -t . -v 2>&1 | tail -15
```
Expected: same result as the Task 3 baseline or better, with no new failures.

- [ ] **Step 8: Commit**

```bash
git add -A
git status --short   # only the intended files
git commit -m "Resolve settings and data paths via QGIS profile instead of ../../..

The plugin built <plugin dir>/../../../patrac_settings, which breaks when the plugin
dir is a symlink. The data path default is now ~/patracdata (or \$PATRAC_DATA).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: First launch and debugger attach

**Files:**
- Create: `tools/dev/debug_attach.py`, `.vscode/launch.json`
- Modify: `docs/dev/macos-setup.md`

**Interfaces:**
- Consumes: scripts from Task 1, helper from Task 4.
- Produces: a working "Attach to QGIS (debugpy)" VS Code configuration on port 5678.

- [ ] **Step 1: Start QGIS and enable the plugin**

Run: `tools/dev/run_qgis.sh`

In QGIS: Plugins > Manage and Install Plugins > Installed > tick **Patrac**.
Expected: a Patrac toolbar and menu appear. Watch the terminal for tracebacks.

If a traceback appears, fix the cause in the code, using superpowers:systematic-debugging. Commit each separate fix as `Fix <what> for QGIS on macOS`. Repeat until enabling the plugin produces no traceback. Do not touch the Czech data or basemap code.

- [ ] **Step 2: Check what the plugin created**

Run:
```bash
ls "$HOME/Library/Application Support/QGIS/QGIS3/profiles/default/patrac_settings"
cat "$HOME/Library/Application Support/QGIS/QGIS3/profiles/default/patrac_settings/config/config.json"
ls "$HOME/patracdata/doc" | head -3
```
Expected: `config grass styles` exists; `config.json` has `"data_path": "/Users/marketasolanikova/patracdata/"`; `index.html` in `~/patracdata/doc`.

- [ ] **Step 3: Show the dock panel**

Click the Patrac toolbar button.
Expected: the Patrac dock widget appears with no traceback.

- [ ] **Step 4: Install `debugpy` into QGIS's Python**

Run:
```bash
source tools/dev/qgis_env.sh
"$QGIS_PY" -m pip install --user debugpy
```
Expected: `Successfully installed debugpy-...` (if `pip` is missing, run `"$QGIS_PY" -m ensurepip --user` first).

- [ ] **Step 5: Write `tools/dev/debug_attach.py`**

```python
# Run inside QGIS: Plugins > Python Console > Show Editor > open this file > Run.
# QGIS was started with tools/dev/run_qgis.sh, so QGIS_PY is set in its environment.
import os

import debugpy

debugpy.configure(python=os.environ["QGIS_PY"])  # sys.executable is the QGIS binary, not Python
debugpy.listen(("127.0.0.1", 5678))
print("debugpy listening on 127.0.0.1:5678 - attach from the IDE")
```

- [ ] **Step 6: Write `.vscode/launch.json`**

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Attach to QGIS (debugpy)",
      "type": "debugpy",
      "request": "attach",
      "connect": { "host": "127.0.0.1", "port": 5678 },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}",
          "remoteRoot": "${env:HOME}/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_patrac"
        }
      ]
    }
  ]
}
```

- [ ] **Step 7: Verify a breakpoint is hit**

1. In VS Code open `patrac.py`, set a breakpoint on the first line of `showWidget` (find it with `grep -n "def showWidget" patrac.py`).
2. In QGIS run `tools/dev/debug_attach.py` from the Python console editor.
3. In VS Code run "Attach to QGIS (debugpy)".
4. In QGIS click the Patrac toolbar button.
Expected: VS Code stops on the breakpoint; Continue resumes and the dock appears.

If it does not stop, check that `debugpy` printed the listening line, and that the `remoteRoot` path equals the symlink path (`ls -l "$QGIS_PLUGINS_DIR"`).

- [ ] **Step 8: Document the workflow**

Append to `docs/dev/macos-setup.md`:

```markdown
## Debugging in VS Code
1. Start QGIS with `tools/dev/run_qgis.sh` (this puts `QGIS_PY` in QGIS's environment).
2. One-time: `"$QGIS_PY" -m pip install --user debugpy`.
3. In QGIS: Plugins > Python Console > Show Editor, open `tools/dev/debug_attach.py`, Run.
4. In VS Code: Run and Debug > "Attach to QGIS (debugpy)". Breakpoints in `*.py` files of this repo now work.
For PyCharm / IntelliJ use a "Python Debug Server" configuration with `pydevd-pycharm` instead of `debugpy`.

## What is checked in
`config/` must exist (the plugin writes `config/lastprojectpath.txt` there). It is created by git via `config/.gitkeep`.
```

- [ ] **Step 9: Commit**

```bash
git add tools/dev/debug_attach.py .vscode/launch.json docs/dev/macos-setup.md
git commit -m "Add debugpy attach workflow for QGIS

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Glossary for a Python developer new to GIS

**Files:**
- Create: `docs/dev/qgis-for-python-devs.md`

- [ ] **Step 1: Write the document** with exactly this content

```markdown
# QGIS and GIS terms for a Python developer

**QGIS**: a desktop map application (like an IDE for maps). Its engine is a C++ library with Python bindings (`qgis.core`, `qgis.gui`). Patrac is a Python plugin loaded inside it.

**Plugin**: a Python package in the QGIS profile's `python/plugins/` folder with a `metadata.txt` and a `classFactory(iface)` function in `__init__.py`. `iface` is the handle to the running QGIS window. QGIS calls `initGui()` when the plugin is enabled and `unload()` when it is disabled.

**Layer**: one dataset shown on the map. A **vector** layer holds geometry plus attributes, like a table with a geometry column. A **raster** layer is a grid of cell values, like an image. `QgsVectorLayer(path, name, "ogr")` opens a vector file, and `QgsRasterLayer` a raster.

**Shapefile (.shp)**: an old vector file format that is really 4-5 files sharing a name (`.shp` geometry, `.dbf` attributes, `.shx` index, `.prj` CRS, `.cpg` encoding). Patrac still uses it for its data. **GeoPackage (.gpkg)** is the modern single-file replacement (a SQLite database).

**OGR / GDAL**: the C library, with Python module `osgeo`, that reads and writes almost every geo file format. QGIS uses it underneath. `ogr` covers vector data, and `gdal` raster data.

**CRS (coordinate reference system)**: says what the numbers in a coordinate mean. **EPSG:4326** is WGS84 latitude/longitude in degrees, what GPS devices and GPX files use. **EPSG:3857** is Web Mercator, used by web basemaps. **EPSG:5514** is S-JTSK, a Czechoslovak system whose units are metres. Because it is metric, Patrac can compute distances and areas directly. The coordinates in S-JTSK are negative numbers, for example `-548069;-1265300` (x;y), which is normal for this system. Slovakia used the same system, so Patrac keeps it.

**Transform**: converting coordinates between CRSs, with `QgsCoordinateTransform`. Always transform GPX points from 4326 to 5514 before measuring in metres.

**Geometry / feature**: a `QgsGeometry` is a point, line or polygon. A `QgsFeature` is one geometry plus its attribute values, that is one row of a layer.

**WMS / tile service**: a web server that returns map images for a requested area. Patrac's basemaps (orthophoto, topographic maps) are WMS or tile layers added by URL.

**Processing algorithm**: a ready-made GIS operation run with `processing.run("native:buffer", {...})`. Examples: `native:extractbyextent`, `native:zonalstatisticsfb`. `native:` ones are built into QGIS, `gdal:` call GDAL, `grass7:` call GRASS GIS (Patrac no longer uses them).

**QgsTask**: QGIS's background-job class. Patrac runs the heavy steps (clipping data, calculating areas) as tasks so the window does not freeze.

**Sector**: in Patrac, a polygon of about 10-20 hectares with one type of land use. The search area is cut into sectors. Each gets a probability of containing the missing person and is assigned to a search team.

**ISRID distances**: statistics from past searches (International Search & Rescue Incident Database) about how far each type of missing person typically ends up from where they were last seen. They are in `grass/distances.txt`, one row per person type, nine distances for the 10%...95% quantiles.

**POD (probability of detection)**: the chance that a searcher passing through a sector finds the person if the person is there. Used by the GPX analysis (sub-project 4).
```

- [ ] **Step 2: Commit**

```bash
git add docs/dev/qgis-for-python-devs.md
git commit -m "Add GIS glossary for Python developers

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Acceptance for this plan (from the spec, sub-project 1)

On this Mac, with the repo symlinked into QGIS 3 LTR:
- [ ] `tools/dev/run_qgis.sh` starts QGIS and enabling **Patrac** prints no traceback.
- [ ] The Patrac dock panel appears.
- [ ] `patrac_settings` and `config.json` are created inside the QGIS profile, and `~/patracdata/` exists.
- [ ] `python3 -m unittest discover -s tests -t . -v` passes (plain Python), and the same command under QGIS's Python passes with the import test running.
- [ ] A breakpoint in `patrac.py` is hit from VS Code.
- [ ] Project creation is **not** expected to work yet (no regional data; sub-project 2 and 3).

## Known issues deliberately left for later plans

- Czech WMS basemap URLs, the Czech municipality CSV, the `kraje/<region>` data layout, and the `Out of Czech Republic` messages (sub-project 3).
- `ui/ui_gpx.py` looks for a Garmin drive using Windows drive letters and `/media`; macOS mounts under `/Volumes` (sub-project 3).
- Network calls to `hscr.cz` / `sarops.info` in the background request thread (sub-project 3 disables them).
