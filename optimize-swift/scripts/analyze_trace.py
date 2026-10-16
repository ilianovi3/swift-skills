#!/usr/bin/env python3
"""analyze_trace.py TRACE [--process NAME] [--label L] [--series] [--pacing-only]

Summary of an xctrace recording made with the Hitches (and optionally Time Profiler) instruments:
  - frames of the app: fps, p50/p95/max interval, share > 8.3 ms and > 16.7 ms, Apple hitches and hitch ms per second;
  - "moving": share of display renders at 120 Hz / 60 Hz while content moves (gaps > 60 ms dropped) — the metric
    that matches what the eye sees; Safari scrolling a long page scores ~95 % / 4 %;
  - main thread: 1 ms Time Profiler samples split by SIGNATURES, and the hottest symbols of the app binary;
  - --series: per half second, display renders, app updates and main-thread ms (for lag that comes and goes).
--process defaults to the process with the most app updates in the trace.
"""
import argparse
import collections
import re
import subprocess
import xml.etree.ElementTree as ET

# Main-thread buckets: label → regex on a frame name. Extend for your app.
SIGNATURES = [
    ("hover hit-test", r"^PlatformHitTestingManager\.hitTest\("),
    ("drag regions", r"_resetDragMargins\]|_regionForOpaqueDescendants"),
    ("text redraw", r"^CABackingStoreUpdate_$"),
    ("view bodies", r"^DynamicBody\.updateValue\(\)$"),
    ("layout", r"LayoutEngineBox\.sizeThatFits|\.sizeThatFits\(proposal:subviews:cache:\)"),
    ("SwiftUI render", r"^ViewGraphRootValueUpdater\.render\("),
    ("window setFrame", r"_setFrameCommon"),
]

ap = argparse.ArgumentParser()
ap.add_argument("trace")
ap.add_argument("--process")
ap.add_argument("--label")
ap.add_argument("--series", action="store_true")
ap.add_argument("--pacing-only", action="store_true")
a = ap.parse_args()
label = a.label or a.trace.rstrip("/").split("/")[-1]


def table(schema):
    x = subprocess.run(["xcrun", "xctrace", "export", "--input", a.trace, "--xpath",
                        f'/trace-toc/run[@number="1"]/data/table[@schema="{schema}"]'],
                       capture_output=True, text=True).stdout
    if not x.strip():
        return [], {}
    ids = {}

    def res(el):  # xctrace writes repeats as ref → id
        if "ref" in el.attrib:
            return ids[el.attrib["ref"]]
        if "id" in el.attrib:
            ids[el.attrib["id"]] = el
        for c in el:
            res(c)
        return el

    return [[res(e) for e in row] for row in ET.fromstring(x).iter("row")], ids


ms = lambda el: int(el.text) / 1e6
B = 500  # ms per series bin

# Display renders (system-wide): pacing while moving.
renders = sorted(ms(r[0]) for r in table("hitches-renders")[0])
moving = [b - x for x, b in zip(renders, renders[1:]) if b - x < 60]
pacing = (f"  moving: 120Hz {100 * sum(i <= 9 for i in moving) / len(moving):.0f}% "
          f"60Hz {100 * sum(9 < i <= 18 for i in moving) / len(moving):.0f}% (Safari ~95% / 4%)") if moving else None
if a.pacing_only:
    print(f"[{label}]")
    print(pacing or "  no display renders in trace")
    raise SystemExit

ups, _ = table("hitches-updates")
procs = collections.Counter(r[2].attrib.get("fmt", "") for r in ups)
proc = a.process or (procs.most_common(1)[0][0].split(" (")[0] if procs else "")
mine = lambda r: proc and proc in r[2].attrib.get("fmt", "")
swaps = {}
for r in filter(mine, ups):
    swaps[r[4].text] = min(swaps.get(r[4].text, ms(r[0])), ms(r[0]))
ts = sorted(swaps.values())
iv = sorted(b - x for x, b in zip(ts, ts[1:]) if b - x < 250)
act = sum(iv) / 1000 or 1
hits = [r for r in table("hitches")[0] if mine(r)]
hit = sum(ms(r[1]) for r in hits)
q = lambda p: iv[min(len(iv) - 1, int(p * len(iv)))] if iv else 0
n = max(len(iv), 1)
print(f"[{label}] process={proc} fps={len(iv) / act:.0f} p50={q(.5):.1f}ms p95={q(.95):.1f}ms "
      f"max={max(iv, default=0):.1f}ms >8.3ms={100 * sum(i > 8.5 for i in iv) / n:.0f}% "
      f">16.7ms={100 * sum(i > 16.8 for i in iv) / n:.0f}% hitches={len(hits)} hitch={hit / act:.0f}ms/s")
if pacing:
    print(pacing)

prof, ids = table("time-profile")
R = lambda el: ids[el.attrib["ref"]] if "ref" in el.attrib else el
cnt, app, total, busy = collections.Counter(), collections.Counter(), 0, collections.Counter()
binary = proc.split(" ")[0]
for r in prof:
    if not r[1].attrib.get("fmt", "").startswith("Main Thread"):
        continue
    total += 1
    busy[int(ms(r[0]) / B)] += 1
    names, seen = [], set()
    for f in (R(f) for f in r[6] if f.tag == "frame"):
        nm = re.sub(r"\s+", " ", f.attrib.get("name", "?"))
        if nm in seen:
            continue
        seen.add(nm)
        names.append(nm)
        b = next((R(c).attrib.get("name", "") for c in f if c.tag == "binary"), "")
        if binary and b.startswith(binary) and "main" not in nm and not nm.startswith(
                ("closure", "partial apply", "thunk", "specialized", "protocol witness", "outlined")):
            app[nm[:100]] += 1
    for k, p in SIGNATURES:
        if any(re.search(p, x) for x in names):
            cnt[k] += 1
if total:
    print(f"  main thread {total} ms: " + ", ".join(f"{k} {cnt[k]}" for k, _ in SIGNATURES if cnt[k]))
    print("  app: " + "; ".join(f"{x} {v}" for x, v in app.most_common(8)))

if a.series:
    rn = collections.Counter(int(t / B) for t in renders)
    un = collections.Counter(int(t / B) for t in ts)
    print("   t,s  renders  app-updates  main-ms")
    for s in sorted(set(rn) | set(un)):
        print(f"  {s * B / 1000:5.1f} {rn[s]:7} {un[s]:10} {busy[s]:8}")
