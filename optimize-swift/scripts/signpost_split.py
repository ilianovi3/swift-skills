#!/usr/bin/env python3
"""signpost_split.py <trace> [--subsystem S] [--name pass|hit] [--pass N|A-B] [--top K] [--dump]

Main-thread Time Profiler samples that fall inside os_signpost intervals of your harness, grouped by the interval's
message "<label> <ordinal>" (e.g. "tabs 1" = first pass with layout after a state change). Prints per group: interval
count, ms per interval (one sample = 1 ms) and the top-K stack frames by inclusive time — so the first pass of two
variants is compared by signatures instead of drowning in the animation that follows it.
  --subsystem  the OSSignposter subsystem of your intervals (default: any subsystem not starting with com.apple.)
  --name       interval name (default "pass"; "hit" = one hit-test, ordinal 0)
  --pass N|A-B ordinals to include (default 1 and 2; a range is merged into one group per label)
  --dump       raw first rows of the os-signpost table (to adapt the columns to your xctrace version)
The exports are cached next to the trace (<trace>.<schema>.xml): a long trace exports for minutes otherwise."""
import collections
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

args = sys.argv[1:]
trace = args[0]
want = [1, 2]
top = 25
name = "pass"
subsystem = None
if "--subsystem" in args:
    subsystem = args[args.index("--subsystem") + 1]
if "--pass" in args:  # N или A-B
    a, _, b = args[args.index("--pass") + 1].partition("-")
    want = list(range(int(a), int(b or a) + 1))
if "--top" in args:
    top = int(args[args.index("--top") + 1])
if "--name" in args:  # «hit» — интервалы одного поиска вида под курсором (номер 0)
    name = args[args.index("--name") + 1]
    want = [0]  # one hit-test per interval, ordinal 0


def export(xpath):
    return subprocess.run(["xcrun", "xctrace", "export", "--input", trace, "--xpath", xpath], capture_output=True, text=True).stdout


def table(schema):
    # Exporting a table takes minutes on a long trace: cache it next to the trace, later runs are instant.
    cache = f"{trace.rstrip('/')}.{schema}.xml"
    try:
        x = open(cache).read()
    except OSError:
        x = export(f'/trace-toc/run[@number="1"]/data/table[@schema="{schema}"]')
        open(cache, "w").write(x)
    if not x.strip():
        return [], {}
    ids = {}

    def res(el):  # xctrace пишет повторы ссылками ref → id
        if "ref" in el.attrib:
            return ids[el.attrib["ref"]]
        if "id" in el.attrib:
            ids[el.attrib["id"]] = el
        for c in el:
            res(c)
        return el

    return [[res(e) for e in row] for row in ET.fromstring(x).iter("row")], ids


if "--dump" in args:
    print(export("/trace-toc")[:4000])
    x = export('/trace-toc/run[@number="1"]/data/table[@schema="os-signpost"]')
    rows = list(ET.fromstring(x).iter("row")) if x.strip() else []
    for r in rows[:3]:
        print(ET.tostring(r, encoding="unicode")[:1500])
    sys.exit(0)

# The os-signpost table is a list of Begin/End events (event-time in ns, signpost-name, subsystem, formatted message in
# os-log-metadata on the End row); an interval is a Begin/End pair of the same name in our subsystem, message "<label> <n>".
spans = []
open_at = None
for r in table("os-signpost")[0]:
    cells = {c.tag: c for c in r}
    sub = cells["subsystem"].attrib.get("fmt", "") if cells.get("subsystem") is not None else ""
    if sub != subsystem if subsystem else sub.startswith("com.apple."):
        continue
    if cells["signpost-name"].attrib.get("fmt") != name:
        continue
    t = int(cells["event-time"].text)
    kind = cells["event-type"].attrib.get("fmt")
    if kind == "Begin":
        open_at = t
    elif kind == "End" and open_at is not None:
        meta = cells.get("os-log-metadata")
        m = re.match(r"\s*(\S+) (\d+)", meta.attrib.get("fmt", "") if meta is not None else "")
        if m and int(m.group(2)) in want:
            spans.append((open_at, t, m.group(1), int(m.group(2))))
        open_at = None
spans.sort()
if not spans:
    sys.exit(f"no «{name}» intervals (subsystem {subsystem or 'any non-Apple'}) — recorded without --instrument os_signpost?")

prof, ids = table("time-profile")
R = lambda el: ids[el.attrib["ref"]] if "ref" in el.attrib else el
count = collections.Counter()
frames = collections.defaultdict(collections.Counter)
starts = [s[0] for s in spans]
import bisect
for r in prof:
    if not r[1].attrib.get("fmt", "").startswith("Main Thread"):
        continue
    t = int(r[0].text)
    i = bisect.bisect_right(starts, t) - 1
    if i < 0 or t > spans[i][1]:
        continue
    key = (spans[i][2], spans[i][3])
    count[key] += 1
    seen = set()
    for f in (R(f) for f in r[6] if f.tag == "frame"):
        n = re.sub(r"\s+", " ", f.attrib.get("name", "?"))[:110]
        if n not in seen:
            seen.add(n)
            frames[key][n] += 1

groups = collections.Counter((v, n) for _, _, v, n in spans)
if len(want) > 1 and "--name" not in args:  # a range of passes — one group per label
    merged = collections.Counter()
    mframes = collections.defaultdict(collections.Counter)
    mcount = collections.Counter()
    for (v, n), k in groups.items():
        merged[(v, f"{want[0]}-{want[-1]}")] += k
        mcount[(v, f"{want[0]}-{want[-1]}")] += count[(v, n)]
        mframes[(v, f"{want[0]}-{want[-1]}")].update(frames[(v, n)])
    groups, count, frames = merged, mcount, mframes
for key in sorted(groups):
    k = groups[key]
    print(f"[{key[0]} pass {key[1]}] intervals={k} samples={count[key]} ≈ {count[key] / k:.1f} ms/interval")
    for n, c in frames[key].most_common(top):
        print(f"  {c / k:6.2f}  {n}")
