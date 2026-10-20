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
rounds: the font's ascent and descent are rounded to whole px each, and the top half of the extra is floored to a
whole px (`CalculateLeadingSpace`). So the baseline sits `floor((L − round(A) − round(D)) / 2) + round(A)` below the
line top, an integer: Geist 13 px in a 19.5 line → 1 + 13 = 14, not 1.3 + 13.065; 12.5 in 18.75 → 0 + 13, not
1.25 + 12.56. SwiftUI with an exact line height puts the extra below the glyphs, places the line top and the ascent on
the device-pixel grid and rounds a `baselineOffset` *up* to the next pixel. Model both:
```swift
let px = size * scale, line = px * lineHeight, s = displayScale
func dev(_ v: CGFloat) -> CGFloat { (v * s).rounded() / s }
let a = ascent * px, d = descent * px                       // CTFont ratios per face; natural = ascent + descent + leading
let inLine = ((line - a.rounded() - d.rounded()) / 2).rounded(.down) + a.rounded()   // Blink baseline from line top
var drop = dev(inLine - dev(a))                              // already on the grid: the round-up keeps it
if let box {                                                 // single line centred in an `h-* items-center` box
    // Chromium on macOS snaps the final baseline to a whole CSS px (a point, not a device pixel) from the box top.
    drop = dev(((box - line) / 2 + inLine).rounded() - dev((box - dev(line)) / 2) - dev(a))
}
if #available(macOS 26, iOS 26, *) {
    text.font(font)
        .lineHeight(.exact(points: line))
        .baselineOffset(-max(drop, 0))                        // move glyphs down to the Blink baseline
        .padding(.top, min(drop, 0)).padding(.bottom, -min(drop, 0))   // line tighter than the font: trim
} else {
    text.font(font).lineSpacing(max(0, line - px * natural))  // only inter-line spacing; single lines keep natural height
}
```
Unrounded half-leading put a 13 px button label 1 pt (2 device px) below the reference and a 12.5 px one 0.5 pt; with
the model above both match to 0.01 pt at 1× and 1.2× text size. The `box` variant belongs in the button/chip
primitive that knows its height (`h-8` → 32 × scale); free text gets only the in-line part.
- Measuring the reference: Chromium on macOS (no zoom-for-DSF) snaps a box at a fractional page position to a whole
  CSS px but rounds its text separately, so the label of the same button moves ±0.5 pt with its page position. Clone
  the element onto an overlay at a whole CSS px and compare ink by coverage-weighted centroid (sub-pixel, AA-proof),
  not by first/last ink rows.
- A run with its own `baselineOffset` inside a concatenated `Text` replaces the paragraph's offset instead of
  adding to it — account for it when mixing sizes.
- Exact line height takes the TextKit 2 path and rasterizes text on the CPU. Fine for paragraphs and headings; in
  long hot lists prefer single-line labels with a fixed frame height and the natural font line.
- `TextField` ignores line height: use the font without line height and pad to the CSS line (see css-to-swiftui).

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
