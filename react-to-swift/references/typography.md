# Typography: matching the browser

Text is where ports drift most, and where the wrong technique also costs the most frames.

## Contents
- Fonts and registration
- Fixed size, no style tracking
- Variable fonts: weight and optical size
- CSS line height (half-leading)
- Tracking
- Smoothing
- Wrapping and pixel positions
- Character classes and graphemes (text logic)
- Coverage test

## Fonts and registration
Bundle the exact font files the web uses (full upstream releases, not Google subsets — they drop glyphs such as
Cyrillic, `№`, curly quotes, narrow no-break space). Register at launch with
`CTFontManagerRegisterFontsForURL(url, .process, nil)`. Address fonts by family name.

Find the files in a SwiftPM package with `Bundle.module`, not `#bundle`. The macro means `Bundle.module` only while
the compiler condition `SWIFT_MODULE_RESOURCE_BUNDLE_AVAILABLE` is set; without it, it silently returns the main
bundle — no font files found, nothing registered, every custom face falls back to the system one (`Font.custom` to
SF, a `CTFontDescriptor` to Helvetica) and nothing fails. The condition vanishes when a build sets
`SWIFT_ACTIVE_COMPILATION_CONDITIONS` on the `xcodebuild` command line (`=DEBUG` for a Release-with-debug-data
profiling build): a command-line setting replaces the value in every target, packages included (`SWIFT_PACKAGE`
goes too, and dependencies switch to their non-SwiftPM code paths). Append instead: `'$(inherited) DEBUG'`. To check
a running build, list its open files: a registered font that has been drawn is mapped (`lsof -p <pid> | grep -i ttf`).

## Fixed size, no style tracking
`Font.custom(name, size:)` is tied to the `.body` text style and applies its tracking: a Geist 14.5 line came out
~3.5 % wider than in Chrome. Use `Font.custom(name, fixedSize:)` — letter spacing then matches CSS and `CTLine`.

## Variable fonts: weight and optical size
- Weight: pass the CSS number through the `wght` axis (`kCTFontVariationAttribute` with tag `0x77676874`) rather
  than relying on named instances.
- Optical size: browsers apply `font-optical-sizing: auto` (`opsz` = font size). `Font.custom` picks a named instance
  (often opsz 8 — wider and coarser). Build the `CTFont` with `opsz` = point size (tag `0x6F70737A`, clamp to the
  font's range) and cache per size and weight.

## CSS line height (half-leading)
CSS puts glyphs in the middle of a line box `size × line-height`, splitting the extra above and below — but Blink
rounds: the font's ascent and descent are rounded to whole px each (the *content area*), and the top half of the extra
is floored to a whole px (`CalculateLeadingSpace`). So the baseline sits `floor((L − round(A) − round(D)) / 2) +
round(A)` below the line top, an integer: Geist 13 px in a 19.5 line → 1 + 13 = 14, not 1.3 + 13.065; 12.5 in 18.75 →
0 + 13, not 1.25 + 12.56. (Verified on plain block lines of sans, serif and mono, 1× and 1.2× zoom: no exceptions.)

What the native side does (macOS, measured with the `firstTextBaseline` guide, which equals the drawn ink):
- `Text` **without** a line height: height `round(A) + round(D)`, baseline `round(A)` — exactly Blink's content area.
- `TextField` (single line and `axis: .vertical`): the same content area; centred in a fixed frame, its top goes to the
  device pixel.
- `Text` with `.lineHeight(.exact(points: L))`: the frame is `L` rounded **up** to the device pixel (20.25 → 20.5) and
  the baseline sits **one font size** below the line top (on the pixel grid), whatever the font's ascent and `L` are.
  For a font with ascent ≈ 1.0 em this looks like "ascent at the top"; a serif with ascent 1.036 sits 0.5–1 pt high
  if you model it with the ascent.
- TextKit 1 with `minimumLineHeight = maximumLineHeight = L`: the extra goes above the glyphs, baseline at
  `L − round(D)` from the fragment top (`location(forGlyphAt:)`); `.baselineOffset` raises the glyphs.
- `baselineOffset` in SwiftUI rounds *up* to the next device pixel; pass values already on the grid.

Port it as one model per primitive:
```swift
let px = size * scale, line = px * lineHeight, s = displayScale
func dev(_ v: CGFloat) -> CGFloat { (v * s).rounded() / s }
let a = (ascent * px).rounded(), d = (descent * px).rounded()   // CTFont ratios per face
let top = ((line - a - d) / 2).rounded(.down), bottom = line - a - d - top   // Blink half-leading
let inLine = top + a                                          // Blink baseline from the line top
// Text with an exact line height: baseline one font size below the line top
var drop = inLine - dev(px)
if let box {                                                  // single line centred in an `h-* items-center` box
    // Chromium snaps the final baseline to a whole CSS px (a point) from the box top; SwiftUI centres the
    // pixel-ceiled frame and puts its top on the pixel grid.
    let frame = (line * s).rounded(.up) / s
    drop = ((box - line) / 2 + inLine).rounded() - dev((box - frame) / 2) - dev(px)
}
text.font(font).lineHeight(.exact(points: line))
    .baselineOffset(-max(drop, 0))                            // move glyphs down to the Blink baseline
    .padding(.top, min(drop, 0)).padding(.bottom, -min(drop, 0))   // line tighter than the font: shift up
// TextField (ignores lineHeight; shown at its content area): pad to the CSS line
field.padding(.top, top).padding(.bottom, bottom)            // minus any shift the text modifier already applied
// TextKit 1 (min = max line height L): raise by the bottom part of the Blink extra
attributes[.baselineOffset] = bottom
```
Unrounded half-leading put a 13 px button label 1 pt (2 device px) below the reference and a 12.5 px one 0.5 pt;
the ascent instead of the font size put a serif heading 1 pt high; with the model above labels, chips, segments,
selects, avatars and fields all match to ≤ 0.13 pt at 1× and 1.2× text size.
- `box` is the height of the block the line is centred in, measured from an ancestor on a whole point: a segment
  inside a padded group (`p-0.5` + border) at 1.2× sits on a fractional offset (3.4) — pass the group's height, the
  line is centred in it too. A bar with `h-12 border-b` centres in 47, not 48.
- `<input>` in Chromium: the content area (not the `line-height` box) is centred in the field and the baseline
  snapped to a whole px: `round((H − round(A) − round(D)) / 2 + round(A))`. A centred `TextField` lands on the pixel
  instead — shift it by the difference (0.5 pt in an `h-8` field).
- `leading-none` chips and `text-[length:…] leading-none` initials have a line *shorter* than the font: the CSS
  baseline rule still holds (negative top half), only the native shift goes up.
- Container-query font sizes (`42cqw` of a bordered circle) follow the *snapped* border: at 1.2× zoom a 1 px border
  stays one device-independent pixel, so the content box is `size × zoom − 2`, not `(size − 2) × zoom`.
- Measuring the reference: Chromium on macOS (no zoom-for-DSF) snaps a box at a fractional page position to a whole
  CSS px but rounds its text separately, so the label of the same button moves ±0.5 pt with its page position. Clone
  the element onto an overlay at a whole CSS px and compare ink by coverage-weighted centroid (sub-pixel, AA-proof),
  not by first/last ink rows.
- A run with its own `baselineOffset` inside a concatenated `Text` replaces the paragraph's offset instead of
  adding to it — account for it when mixing sizes.
- Exact line height takes the TextKit 2 path and rasterizes text on the CPU. Fine for paragraphs and headings; in
  long hot lists prefer single-line labels with a fixed frame height and the natural font line.
- `TextField` ignores line height: use the font without line height and pad its content area to the CSS line with the Blink half-leading (above).
  That only fixes a single line. On macOS `TextField(axis: .vertical)` is an `NSTextField` and ignores both
  `.lineHeight` and `.lineSpacing` (probe, macOS 27): wrapped lines step at the font's own height — 16 px / 26 line
  steps 21, serif 28 / 1.08 steps 38 instead of 30.5. A wrapping editable span with a CSS line height needs a TextKit
  view (`NSTextView` with min = max line height and a `baselineOffset` lift — exact for line ≥ font; for line < font
  check the lift, it came out 4 pt high). `TextEditor` honours `.lineHeight` for the step but sits its first line
  2–3 pt high and drifts on serif at large sizes — not a drop-in either. Test the step with two hard lines against a
  `Text` of the same font: first-line middle, step and height.

## Tracking
`tracking-[-0.01em]` → `.kerning(-0.01 * fontSize * scale)`; `tracking-wide` = 0.025em. Headings with negative
tracking are easy to miss and visibly change line widths. A `TextField` (macOS) applies `.kerning` to its prompt
only, not to the typed text — tracked inputs need `NSTextField` with `.kern` (css-to-swiftui, form controls).
`num` (`tabular-nums`) on a custom font → Core Text feature `kNumberSpacingType`/`kMonospacedNumbersSelector` (Geist
digits are proportional by default: "111111" is 58 % of "000000").

## Smoothing
Browsers on macOS render with `-webkit-font-smoothing: antialiased` (thin). AppKit's default font smoothing makes
the same text ~13 % heavier (measured by ink coverage). If the product must look 1:1 with the web, set the app's
`AppleFontSmoothing` default to 0 in the app's own defaults domain before windows appear (the system setting is not
touched), and state the trade-off: text then differs from other macOS apps. Make this an explicit decision.
```swift
func applicationWillFinishLaunching(_: Notification) {
    if UserDefaults.standard.object(forKey: "AppleFontSmoothing") == nil {   // respect a value the user set
        UserDefaults.standard.set(0, forKey: "AppleFontSmoothing")
    }
}
```

## Wrapping and pixel positions
- One `Text` positions words with sub-pixel precision like the browser; a view per word snaps each word to pixels
  and drifts by 1–3 px toward the end of the line. Prefer one `Text` for paragraphs (also for performance).
- TextKit avoids a single orphan word on the last line; Chrome does not. Occasionally a word moves to the previous
  line. Accept and list it as a native difference rather than fighting the line breaker.
- `line-clamp-N` → `lineLimit(N)`; `truncate` → `lineLimit(1)` + `truncationMode(.tail)`; `whitespace-nowrap` on an
  inline chip → no-break spaces (U+00A0) inside it.

## Character classes and graphemes (text logic)
Ported text logic (initials, "word at the caret", mention suggestions, counters) must agree with the reference on
the same test vectors; the usual drift is in what counts as a letter and what counts as one character.
- JS `/\p{L}/u` → `unicodeScalars.first?.properties.generalCategory` in L* (Lu, Ll, Lt, Lm, Lo). Not
  `Character.isLetter`: it is the Alphabetic property, wider — circled letters ("Ⓐ"), Roman numerals ("Ⅻ") pass it.
  `\p{N}` → Nd/Nl/No the same way (`Character.isNumber` follows Numeric_Type, also wider).
- `Intl.Segmenter(granularity: 'grapheme')` ≈ Swift `Character`, including Indic conjuncts ("क्ष" is one grapheme on
  both sides with current ICU/Swift); code-point code on the web (`Array.from(s)`, `/\p{L}+$/u`) splits NFD "é" and
  syllables — fix the reference, then share vectors (NFD, Devanagari, emoji with ZWJ, U+200B/U+200F before a name).
- Strip invisible format characters (`\p{Cf}`, `generalCategory == .format`) before taking initials, or a leading
  zero-width space hides the first word. Prefix match of a partly typed syllable — by scalars
  (`unicodeScalars.starts(with:)`), length thresholds — in graphemes (`count`).
- A server limit counted in code points (`len()` in Python, `[...s].length` in JS) is `unicodeScalars.count` in Swift,
  never `count` (graphemes) or `utf16.count`.
- An invisible escape inside user text (e.g. U+034F COMBINING GRAPHEME JOINER to keep a typed `@{…}` from being read
  as markup) joins the previous `Character`, so `hasPrefix("@{")` is false on the escaped form — good; but write it
  escaped in source (`"\u{034F}"`) and compare test strings by `unicodeScalars`, because a stray copy is invisible.

## Coverage test
A unit test that every bundled face has glyphs for the characters your content uses
(`CTFontGetGlyphsForCharacters` for e.g. "Ёё Її Ққ № « » “ ” — … $") catches broken subsets before users do.
