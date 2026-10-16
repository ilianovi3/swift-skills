#!/bin/sh
# record_manual.sh LABEL APP_BINARY [APP ARGS...]   — launch the app, countdown, record while the USER scrolls
# PID=1234 record_manual.sh LABEL                     — attach to a running app instead
#
# Records Hitches + Time Profiler for DURATION seconds (default 20) and prints analyze_trace.py output.
# Env: LEAD (s before countdown, default 7 — time to open the right state), DURATION, TRACES (output dir,
# default ./perf-traces), CUE (countdown panel binary; built from cue.swift next to this script if missing).
# Synthetic input does not move the cursor; decisions about interaction cost need this recording.
set -e
here=$(cd "$(dirname "$0")" && pwd)
label=$1; shift
out=${TRACES:-./perf-traces}; mkdir -p "$out"
dur=${DURATION:-20}
cue=${CUE:-$here/cue}
[ -x "$cue" ] || swiftc -O "$here/cue.swift" -o "$cue" 2>/dev/null || cue=""
say() { if [ -n "$cue" ]; then "$cue" "$1" "$2"; else echo "$1" | sed "s/%d/$2/"; sleep "$2"; fi; }

if [ -n "$PID" ]; then
  pid=$PID; launched=""
else
  "$@" >/dev/null 2>&1 &
  pid=$!; launched=1
  sleep "${LEAD:-7}"
fi
osascript -e "tell application \"System Events\" to set frontmost of (first process whose unix id is $pid) to true" >/dev/null 2>&1 || true
t=$out/$label-$(date +%m%d-%H%M%S).trace
say "Scroll in %d s" 5
say "Scroll · %d" "$dur" &
xcrun xctrace record --instrument Hitches --instrument 'Time Profiler' --attach "$pid" --time-limit "${dur}s" --output "$t" >/dev/null 2>&1
say "Done, you can stop" 3 &
[ -n "$launched" ] && kill "$pid" 2>/dev/null || true
python3 "$here/analyze_trace.py" "$t" --label "$label"
echo "$t"
