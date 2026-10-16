#!/bin/sh
# record_reference.sh APP_NAME LABEL — record display pacing system-wide while the user scrolls a reference app
# (Safari on a long page, Notes, Mail). Hitches only, all processes: attaching profilers to Apple apps is blocked.
# Output: analyze_trace.py --pacing-only. Safari measured ~95 % of frames at 120 Hz while moving.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app=$1; label=$2
out=${TRACES:-./perf-traces}; mkdir -p "$out"
dur=${DURATION:-20}
cue=${CUE:-$here/cue}
[ -x "$cue" ] || swiftc -O "$here/cue.swift" -o "$cue" 2>/dev/null || cue=""
say() { if [ -n "$cue" ]; then "$cue" "$1" "$2"; else echo "$1" | sed "s/%d/$2/"; sleep "$2"; fi; }
osascript -e "tell application \"$app\" to activate" >/dev/null 2>&1 || true
t=$out/$label-$(date +%m%d-%H%M%S).trace
say "$app: scroll in %d s" 5
say "Scroll $app · %d" "$dur" &
xcrun xctrace record --instrument Hitches --all-processes --time-limit "${dur}s" --output "$t" >/dev/null 2>&1
say "Done, you can stop" 3 &
python3 "$here/analyze_trace.py" "$t" --label "$label" --pacing-only
echo "$t"
