#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/qgis_env.sh"
QGIS_BIN="$(ls "$QGIS_APP"/Contents/MacOS/QGIS* | head -n1)"
exec "$QGIS_BIN" "$@"
