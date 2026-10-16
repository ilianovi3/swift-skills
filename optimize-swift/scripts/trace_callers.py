#!/usr/bin/env python3
"""trace_callers.py callers TRACE REGEX [DEPTH]   — who triggers the matched frame (chains above it)
   trace_callers.py inside  TRACE REGEX           — what the matched frame spends time on (self and inclusive)

Works on main-thread samples of the Time Profiler table of an xctrace recording. Typical use:
  trace_callers.py callers t.trace '^PlatformHitTestingManager\\.hitTest' 6
  trace_callers.py callers t.trace '_performHitTestForContext|_hitTestForContext' 4
  trace_callers.py inside  t.trace '^PlatformHitTestingManager\\.hitTest'
"""
import collections
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

mode, trace, target = sys.argv[1], sys.argv[2], sys.argv[3]
depth = int(sys.argv[4]) if len(sys.argv) > 4 else 5
x = subprocess.run(["xcrun", "xctrace", "export", "--input", trace, "--xpath",
                    '/trace-toc/run[@number="1"]/data/table[@schema="time-profile"]'], capture_output=True, text=True).stdout
ids = {}


def res(el):
    if "ref" in el.attrib:
        return ids[el.attrib["ref"]]
    if "id" in el.attrib:
        ids[el.attrib["id"]] = el
    for c in el:
        res(c)
    return el


rows = [[res(e) for e in row] for row in ET.fromstring(x).iter("row")]
R = lambda el: ids[el.attrib["ref"]] if "ref" in el.attrib else el
chains, leaf, incl, n = collections.Counter(), collections.Counter(), collections.Counter(), 0
for r in rows:
    if not r[1].attrib.get("fmt", "").startswith("Main Thread"):
        continue
    # frames are leaf-first
    names = [re.sub(r"\s+", " ", R(f).attrib.get("name", "?")) for f in r[6] if f.tag == "frame"]
    hits = [i for i, nm in enumerate(names) if re.search(target, nm)]
    if not hits:
        continue
    n += 1
    if mode == "callers":
        i = max(hits)  # outermost occurrence
        chains[" <- ".join(re.sub(r"\(.*", "", nm)[:60] for nm in names[i + 1:i + 1 + depth])] += 1
    else:
        inner = names[:min(hits)]
        if inner:
            leaf[inner[0][:90]] += 1
        for nm in set(inner):
            incl[nm[:90]] += 1
print(f"samples (ms) matching /{target}/: {n}")
if mode == "callers":
    for c, k in chains.most_common(12):
        print(f"{k:6} {c}")
else:
    print("self:")
    for c, k in leaf.most_common(12):
        print(f"{k:6} {c}")
    print("inclusive:")
    for c, k in incl.most_common(25):
        print(f"{k:6} {c}")
