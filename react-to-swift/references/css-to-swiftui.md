# CSS / Tailwind → SwiftUI, value for value

Every rule below fixed a real 0.5–8 pt mismatch in a production port. Scale all reference pixels by your text-size
multiplier if the app has one (`value * k`), except hairlines (1 px borders stay 1).

## Contents
- Units and computed values
- Box model and borders
- Rules between sections
- Flex and grid
- Wrapping rows
- Position, overlays, z-order
- Colors
- Shadows and blur
- Opacity and states
- Motion
- Form controls and disclosure
- Accessibility attributes

## Units and computed values
- `px` → points 1:1 on macOS (CSS px = pt at 100 % zoom). `rem` = root font size (usually 16).
- `em` resolves against the element's own font size; compute it, don't copy the class: `clamp(12px, 0.72em, 16px)`
  inside 14.5 px text = 12.
- `clamp(a, Xvw, b)` resolves at the reference viewport width (e.g. 1280 → 2.6vw = 33.28 px). Pick the reference
  width you compare against and use that value, or recompute from the window width with `onGeometryChange` if the
  native window really resizes the same way.
- `cqw` (container query width) → fraction of the container's width without its border: `max(42cqw, 6.5px)` of a
  24 px avatar with a 1 px border = `max((24 − 2) × 0.42, 6.5)`.
- Read `getComputedStyle` in a headless browser when in doubt; it removes all of the above guesswork.

## Box model and borders
CSS uses `box-sizing: border-box` almost everywhere: the border is inside the declared size and adds to the
content offset.
```swift
// `h-8 px-3 border rounded-md` → height 32 including the border; content inset 12 + 1
content
    .padding(.horizontal, 12 + 1)
    .frame(height: 32)
    .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Color.rule, lineWidth: 1))   // inside, like CSS
```
- `stroke` draws on the path, half outside: every control becomes 1 pt larger and 0.5 pt offset. Use `strokeBorder`.
- A field with `px-3 border` and no explicit height is `content + 2 × (padding + 1)`.
- Rings (`ring-2 ring-paper`) sit outside the border: draw the ring as a background circle larger by 2 × ring, the
  border as `strokeBorder` on top — otherwise the ring covers the border and stacked avatars lose their outlines.

## Rules between sections
`border-t` / `border-b` take their own pixel row: a section with `border-t pt-5` is 1 px taller than its padding.
```swift
extension View {
    func rule(_ edge: VerticalEdge, _ color: Color, on: Bool = true) -> some View {
        VStack(spacing: 0) {
            if edge == .top && on { color.frame(height: 1) }
            self
            if edge == .bottom && on { color.frame(height: 1) }
        }
    }
}
```
- Bars `h-12 border-b`: content is centered in 47 pt above the border, not in 48.
- `last:border-b-0` on rows: let the container decide (SwiftUI `Group(subviews:)` / container values) and omit the
  rule after the last child; per-row flags drift out of sync.
- Underlined tabs `pb-2.5 border-b-2`: tab = text + 10 + 2 (the line has its own rows).

## Flex and grid
| CSS | SwiftUI |
| --- | --- |
| `flex gap-2` | `HStack(spacing: 8)` |
| `flex-col gap-y-1` | `VStack(spacing: 4)` |
| `items-center` / `items-start` / `items-baseline` | `HStack(alignment: .center / .top / .firstTextBaseline)` |
| `justify-between` | `Spacer(minLength: 0)` between groups |
| `flex-1 min-w-0` | `.frame(maxWidth: .infinity, alignment: .leading)` (+ `lineLimit` / `truncationMode`) |
| `shrink-0` | `.fixedSize(horizontal: true, vertical: false)` |
| `grid-cols-[minmax(0,1fr)_auto]` | `HStack { flexible.frame(maxWidth: .infinity) ; control.fixedSize() }` — the auto column sizes to content; without `fixedSize` HStack splits space and truncates the control |
| `ml-auto` on a wrapped item | Push to trailing edge in a custom `Layout` or `ViewThatFits` |
| `space-y-*` on a list | spacing on the stack, not padding on each child (`.padding` on a `Group` applies to every child) |

## Wrapping rows
`flex-wrap` of chips/metadata → a custom `Layout` that measures each child once (`makeCache`) and only breaks lines
per width; center items vertically in the line when the CSS uses `items-center`/`align-middle`. For words of a
paragraph, do not wrap views at all — use one `Text` (see the main skill).

## Position, overlays, z-order
- `relative` + `absolute top-[11px] left-0` → `.overlay(alignment: .topLeading) { x.padding(.top, 11) }`.
- `inset-0` backgrounds → `.background { … }` (sized to the view, not its children).
- `z-*` → `zIndex` among siblings, or overlay order.
- `sticky top-0` → pinned section header / `safeAreaInset(edge: .top)`.
- `overflow-hidden rounded-*` → `.clipShape(RoundedRectangle(cornerRadius:))` (clip only what the CSS clips).

## Colors
- Port tokens as named colors with light/dark values; never hardcode a hex in a screen.
- OKLCH/OKLab tokens must be converted precisely (OKLCH → OKLab → linear sRGB → gamma sRGB); approximate tools
  drift by several units per channel. Keep the converter in code with a unit test against known values.
- `text-ink-2` vs `text-ink` mismatches are frequent: read the computed `color`, including inherited ones.
- Markdown in localized keys turns emails/URLs into blue links (`Text(LocalizedStringKey)`): pass placeholders as
  plain strings.

## Shadows and blur
`box-shadow: 0 12px 40px -14px rgb(0 0 0 / .35)` has a negative spread, which SwiftUI `shadow` cannot express:
```swift
.background {
    Capsule().fill(.black.opacity(0.35))
        .padding(14)          // spread −14: the shadow shape is smaller than the element
        .blur(radius: 20)     // CSS blur radius 40 ≈ Gaussian sigma 20
        .offset(y: 12)
}
```

## Opacity and states
- `disabled:opacity-40` on a filled button fades the whole button at once: `.compositingGroup().opacity(0.4)`.
- Hover/pressed backgrounds animate with the reference's transition duration; on dense repeated rows prefer state
  per item to avoid re-rendering all rows (see `optimize-swift`).
- Focus rings: native focus ring or the reference's ring; decide once per kit component.

## Motion
- `transition-[x] duration-200 ease-out` → `.animation(.easeOut(duration: 0.2), value: x)`.
- `cubic-bezier(.16,1,.3,1)` → `.timingCurve(0.16, 1, 0.3, 1, duration: d)`.
- GSAP `stagger` → per-index delay from the same formula (`stagger.amount` divides by n − 1); `power2.out` →
  `1 − (1 − p)^3`.
- `prefers-reduced-motion` → `accessibilityReduceMotion`: jump to the end state.
- Infinite animations (`animate-pulse`, spinners) run while visible: keep them tiny and isolated.

## Form controls and disclosure
- `<input type="checkbox" class="accent-ink size-3.5">` → native checkbox with tint, or a drawn 14 pt box; both are
  fine for performance — pick the closer look.
- `<details>`/`<summary>` marker is a filled triangle ▸/▾ in the text color (~0.46 em), not a chevron icon.
- `list-style: disc` in serif text is a ~5 pt circle 4 pt from the edge; the glyph "•" is smaller.
- `contentEditable` single line still wraps by words like a span; Enter commits.
- Text fields don't take line height: center the text with padding (`(lineHeight − natural) / 2`) and
  `baselineOffset(0)`, otherwise text and placeholder sit ~2 pt low.

## Accessibility attributes
`aria-label` → `accessibilityLabel`; `role="heading"`/`h1–h6` → `.accessibilityAddTraits(.isHeader)`;
`aria-selected` → `.isSelected`; `title` → `.help` (also a tooltip — mind density); decorative icons →
`accessibilityHidden(true)`.
