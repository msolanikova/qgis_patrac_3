#!/usr/bin/env bash
# Headless smoke test of the Patrac plugin in the real QGIS binary (no window, no keychain prompt).
# Uses a throw-away QGIS profile and a throw-away data folder (PATRAC_DATA) in a temp dir; the real ~/patracdata is not touched.
# Exit status 0 only if every SMOKE line is PASS. Hard limit: SMOKE_TIMEOUT seconds (default 120).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
source "$HERE/qgis_env.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PROFILES="$WORK/profiles"
mkdir -p "$PROFILES/profiles/default/python/plugins" "$PROFILES/profiles/default/qgis.org"
# Hermetic data folder: qgis_env.sh exports a default PATRAC_DATA, so override it after sourcing.
export PATRAC_DATA="$WORK/data"
mkdir -p "$PATRAC_DATA/kraje/xx"
printf '%s\n' \
  '-262580;-1240038;0;Košice;0;okres Košice I;XX' \
  '-325630;-1257190;0;Ardovo;0;okres Rožňava;XX' > "$PATRAC_DATA/kraje/xx/places.csv"
ln -s "$REPO" "$PROFILES/profiles/default/python/plugins/qgis_patrac"
# A fresh profile would otherwise block forever on a macOS keychain prompt for the QGIS master password.
printf '[auth]\nuse_password_helper=false\n' > "$PROFILES/profiles/default/qgis.org/QGIS3.ini"
echo "headless-smoke" > "$WORK/authpw"; chmod 600 "$WORK/authpw"

QGIS_AUTH_PASSWORD_FILE="$WORK/authpw" QT_QPA_PLATFORM=offscreen \
  perl -e 'alarm shift; exec @ARGV' "${SMOKE_TIMEOUT:-120}" \
  "$QGIS_APP/Contents/MacOS/QGIS" --nologo --profiles-path "$PROFILES" \
  --code "$HERE/headless_smoke.py" 2>&1 | tee "$WORK/out.log"
grep -q "^SMOKE RESULT: ALL PASS" "$WORK/out.log"
