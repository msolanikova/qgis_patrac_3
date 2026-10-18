#!/usr/bin/env bash
# Headless smoke test of the Patrac plugin in the real QGIS binary (no window, no keychain prompt).
# Uses a throw-away QGIS profile in a temp dir; ~/patracdata is the normal data folder.
# Exit status 0 only if every SMOKE line is PASS. Hard limit: SMOKE_TIMEOUT seconds (default 120).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
source "$HERE/qgis_env.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PROFILES="$WORK/profiles"
mkdir -p "$PROFILES/profiles/default/python/plugins" "$PROFILES/profiles/default/qgis.org"
ln -s "$REPO" "$PROFILES/profiles/default/python/plugins/qgis_patrac"
# A fresh profile would otherwise block forever on a macOS keychain prompt for the QGIS master password.
printf '[auth]\nuse_password_helper=false\n' > "$PROFILES/profiles/default/qgis.org/QGIS3.ini"
echo "headless-smoke" > "$WORK/authpw"; chmod 600 "$WORK/authpw"

QGIS_AUTH_PASSWORD_FILE="$WORK/authpw" QT_QPA_PLATFORM=offscreen \
  perl -e 'alarm shift; exec @ARGV' "${SMOKE_TIMEOUT:-120}" \
  "$QGIS_APP/Contents/MacOS/QGIS" --nologo --profiles-path "$PROFILES" \
  --code "$HERE/headless_smoke.py" 2>&1 | tee "$WORK/out.log"
grep -q "^SMOKE RESULT: ALL PASS" "$WORK/out.log"
