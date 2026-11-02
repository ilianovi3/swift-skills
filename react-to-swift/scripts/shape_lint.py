#!/usr/bin/env python3
"""shape_lint.py [--lines] [--ratchet FILE] DIR... — count DOM-port signatures in Swift sources (see
references/dom-port-signatures.md). Prints per-pattern totals; --lines adds file:line. With --ratchet FILE it keeps
ceilings {file: {pattern: n}} in FILE: exit 1 if any count is above its ceiling, and lowers ceilings to current counts
(never raises). Comments are ignored. ponytail: regex, not a parser; add a pattern when a new signature costs frames."""
import json, os, re, sys

PAT = {
    "onHover": r"\.onHover\b", "onContinuousHover": r"\.onContinuousHover\b",
    "stateHover": r"@State\b[^=\n]*\bvar\s+\w*[Hh]over", "help": r"\.help\(",
    "Button": r"\bButton\s*[({]", "AnyView": r"\bAnyView\(",
    "idOffset": r"\bid:\s*\\\.offset\b", "idSelf": r"\bid:\s*\\\.self\b",
    "forEachEnumerated": r"\bForEach\(.*\.enumerated\(\)", "forEachIndices": r"\bForEach\([^)]*\.indices",
    "fixedSize": r"\.fixedSize\(", "geometryReader": r"\bGeometryReader\b",
    "positionMod": r"(?m)(?:\)|^[ \t]*)\.position\(", "offsetMod": r"\.offset\((?:x|y|CGSize)",
    "onTapGesture": r"\.onTapGesture\b", "repeatForever": r"repeatForever",
    "timerUI": r"Timer\.(?:scheduledTimer|publish)|asyncAfter",
    "eventMonitor": r"add(?:Local|Global)MonitorForEvents",
    "clearSpacer": r"Color\.clear\.frame\(height: [1-9]", "idRemount": r'\.id\("\\\(',
    "bindingGetSet": r"Binding\(\s*get:",
    # SwiftUI scroll APIs do nothing inside a wrapped NSScrollView
    "swiftuiScroll": r"\bScrollViewReader\b|\.scrollTo\(|[:(]\s*\.scrollView\b|\.onScrollGeometryChange\b"
                     r"|\.onScrollPhaseChange\b|\.onScrollVisibilityChange\b|\.scrollPosition\(|\.scrollTargetLayout\("
                     r"|\.defaultScrollAnchor\(|pinnedViews:",
}
LAYOUT = re.compile(r"\b(?:struct|extension)\s+\w+[^{]*?:[^{]*\bLayout\b[^{]*\{")


def strip(code):
    code = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group()), code, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", code, flags=re.M)


def scan(code):
    code = strip(code)
    line = lambda i: code.count("\n", 0, i) + 1
    hits = {k: [line(m.start()) for m in re.finditer(p, code)] for k, p in PAT.items()}
    hits["layoutNoCache"] = []
    for m in LAYOUT.finditer(code):  # a custom Layout without makeCache re-measures children every pass
        depth = 0
        for i in range(m.end() - 1, len(code)):
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            if not depth:
                break
        if "makeCache" not in code[m.end():i]:
            hits["layoutNoCache"].append(line(m.start()))
    return {k: v for k, v in hits.items() if v}


def selftest():
    assert scan("x.onHover { }\n// .help(\nstruct L: Layout { }\nScrollViewReader { p in p.scrollTo(1) }\n") == \
        {"onHover": [1], "layoutNoCache": [3], "swiftuiScroll": [4, 4]}


def main(argv):
    selftest()
    lines, ratchet = "--lines" in argv, argv[argv.index("--ratchet") + 1] if "--ratchet" in argv else None
    dirs = [a for a in argv if not a.startswith("--") and a != ratchet]
    found = {}
    for d in dirs:
        for dp, _, fn in os.walk(d):
            for f in sorted(fn):
                if f.endswith(".swift"):
                    p = os.path.join(dp, f)
                    h = scan(open(p, encoding="utf-8").read())
                    if h:
                        found[p] = h
    tot = {}
    for p, h in found.items():
        for k, v in h.items():
            tot[k] = tot.get(k, 0) + len(v)
            if lines:
                print(f"{p}: {k} {v}")
    print(", ".join(f"{k} {n}" for k, n in sorted(tot.items())) or "clean", f"— {sum(tot.values())} total")
    if ratchet:
        ceil = json.load(open(ratchet)) if os.path.exists(ratchet) else None
        cur = {p: {k: len(v) for k, v in h.items()} for p, h in found.items()}
        bad = [(p, k, n, ceil[p].get(k, 0)) for p, h in cur.items() for k, n in h.items()
               if ceil is not None and n > ceil.get(p, {}).get(k, 0)]
        for b in bad:
            print("above ceiling: %s %s %d > %d" % b)
        if ceil is not None:  # only down
            cur = {p: {k: min(n, ceil.get(p, {}).get(k, n)) for k, n in h.items()} for p, h in cur.items()}
        json.dump(cur, open(ratchet, "w"), indent=2, sort_keys=True)
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
