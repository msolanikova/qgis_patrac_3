#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/qgis_env.sh"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$QGIS_PLUGINS_DIR"
ln -sfn "$REPO" "$QGIS_PLUGINS_DIR/qgis_patrac"
ls -ld "$QGIS_PLUGINS_DIR/qgis_patrac"
