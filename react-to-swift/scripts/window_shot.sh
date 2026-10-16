#!/bin/sh
# window_shot.sh OUT.png APP_BINARY [APP ARGS...] — launch the app, wait LEAD seconds (default 8), capture only its
# largest on-screen window (no shadow, no focus change of other apps), quit the app.
# Pass launch arguments / deep links that open the exact state to capture. The window is visible for a few seconds.
set -e
here=$(cd "$(dirname "$0")" && pwd)
out=$1; shift
wid=$here/.wid
[ -x "$wid" ] || swiftc -O "$here/window_id.swift" -o "$wid"
"$@" >/dev/null 2>&1 &
pid=$!
sleep "${LEAD:-8}"
id=$("$wid" "$pid")
if [ "$id" = "0" ]; then echo "no window for pid $pid" >&2; kill "$pid"; exit 1; fi
screencapture -x -o -l "$id" "$out"
kill "$pid" 2>/dev/null || true
echo "$out"
