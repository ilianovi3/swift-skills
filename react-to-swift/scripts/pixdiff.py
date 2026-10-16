#!/usr/bin/env python3
"""pixdiff.py A.png B.png [--crop x0,y0,x1,y1] [--out view.png] [--side] [--ink x0,y0,x1,y1[:threshold]]...

Compare two screenshots of the same state (reference vs app, or build A vs build B) at the same pixel scale.
  - prints the bounding box and the count of pixels that differ by more than --tol (default 24) on any channel;
  - --out writes A above B (or side by side with --side) and an amplified difference strip below them;
  - --ink BOX prints, for both images, the first/last row and column inside BOX whose luminance is below the
    threshold (default 120): the quickest way to read offsets such as "capsule 2 px lower" or "text starts later".
Requires Pillow (pip install pillow).
"""
import argparse

from PIL import Image, ImageChops

ap = argparse.ArgumentParser()
ap.add_argument("a")
ap.add_argument("b")
ap.add_argument("--crop")
ap.add_argument("--out")
ap.add_argument("--side", action="store_true")
ap.add_argument("--tol", type=int, default=24)
ap.add_argument("--ink", action="append", default=[])
x = ap.parse_args()

box = lambda s: tuple(int(v) for v in s.split(","))
A = Image.open(x.a).convert("RGB")
B = Image.open(x.b).convert("RGB")
if x.crop:
    A, B = A.crop(box(x.crop)), B.crop(box(x.crop))
if A.size != B.size:
    print(f"sizes differ: {A.size} vs {B.size} — comparing the common area")
    w, h = min(A.width, B.width), min(A.height, B.height)
    A, B = A.crop((0, 0, w, h)), B.crop((0, 0, w, h))

d = ImageChops.difference(A, B)
data = d.get_flattened_data() if hasattr(d, "get_flattened_data") else d.getdata()
n = sum(1 for p in data if max(p) > x.tol)
print(f"diff px {n} of {A.width * A.height} ({100 * n / (A.width * A.height):.2f}%), bbox {d.getbbox()}")

for spec in x.ink:
    b, _, thr = spec.partition(":")
    thr = int(thr or 120)
    x0, y0, x1, y1 = box(b)
    for name, im in (("A", A), ("B", B)):
        g = im.convert("L")
        rows = [y for y in range(y0, y1) if any(g.getpixel((xx, y)) < thr for xx in range(x0, x1))]
        cols = [xx for xx in range(x0, x1) if any(g.getpixel((xx, y)) < thr for y in range(y0, y1))]
        print(f"ink {b} <{thr} {name}: rows {(rows[0], rows[-1]) if rows else None} cols {(cols[0], cols[-1]) if cols else None}")

if x.out:
    amp = d.point(lambda v: 255 - min(255, v * 4))
    if x.side:
        out = Image.new("RGB", (A.width * 2 + 8, A.height * 2 + 8), "red")
        out.paste(A, (0, 0)); out.paste(B, (A.width + 8, 0)); out.paste(amp, (0, A.height + 8))
    else:
        out = Image.new("RGB", (A.width, A.height * 3 + 16), "red")
        out.paste(A, (0, 0)); out.paste(B, (0, A.height + 8)); out.paste(amp, (0, 2 * A.height + 16))
    out.save(x.out)
    print(x.out)
