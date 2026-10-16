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
- Coverage test

## Fonts and registration
Bundle the exact font files the web uses (full upstream releases, not Google subsets — they drop glyphs such as
Cyrillic, `№`, curly quotes, narrow no-break space). Register at launch with
`CTFontManagerRegisterFontsForURL(url, .process, nil)`. Address fonts by family name.

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
CSS puts glyphs in the middle of a line box `size × line-height`, splitting the extra equally above and below.
SwiftUI adds extra space below the glyphs. Model it explicitly:
```swift
let px = size * scale
let natural = (ascent + descent + leading) / pointSize   // from CTFont, per face
let half = px * (lineHeight - natural) / 2
if #available(macOS 26, iOS 26, *) {
    text.font(font)
        .lineHeight(.exact(points: px * lineHeight))
        .baselineOffset(-max(half, 0))                   // move glyphs down to the middle
        .padding(.top, min(half, 0)).padding(.bottom, -min(half, 0))   // line tighter than natural: trim
} else {
    text.font(font).lineSpacing(max(0, 2 * half))         // only inter-line spacing; single lines keep natural height
}
```
- A run with its own `baselineOffset` inside a concatenated `Text` replaces the paragraph's offset instead of
  adding to it — account for it when mixing sizes.
- Exact line height takes the TextKit 2 path and rasterizes text on the CPU. Fine for paragraphs and headings; in
  long hot lists prefer single-line labels with a fixed frame height and the natural font line.
- `TextField` ignores line height: use the font without line height and pad to the CSS line (see css-to-swiftui).

## Tracking
`tracking-[-0.01em]` → `.kerning(-0.01 * fontSize * scale)`; `tracking-wide` = 0.025em. Headings with negative
tracking are easy to miss and visibly change line widths.

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

## Coverage test
A unit test that every bundled face has glyphs for the characters your content uses
(`CTFontGetGlyphsForCharacters` for e.g. "Ёё Її Ққ № « » “ ” — … $") catches broken subsets before users do.
