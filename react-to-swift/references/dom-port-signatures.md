# DOM-port signatures: what a literal port leaves in the view tree

A literal port of a web component copies the DOM's *shape*, not only its look. SwiftUI pays for that shape on every mouse
event and every layout pass. Count these signatures with `scripts/shape_lint.py` (a per-file counter with ceilings that only
go down) and replace them with the native form. Measure the look before and after: each row below was done with a pixel pair
at 0 px difference, except where noted.

| Web signature | Literal port (count it) | Native form |
| --- | --- | --- |
| `<button role="switch">` | hand-made `Button` + `@State` knob | `Toggle` + a custom `ToggleStyle` (one kit switch) |
| A row that is a `<button>` / `<a>` with `hover:bg-…` | `Button` + `.onHover` + `@State hover` + `.help` per row | A target in the container's hover map (one tracker, `DMPressable`-like): hover, press and tooltip live in the map, the row is passive (root-causes §25) |
| `animate-spin` | `withAnimation(.linear.repeatForever())` + `@State` angle | `TimelineView(.animation(paused: reduceMotion))` + `rotationEffect` from the date; `PhaseAnimator` is the alternative for discrete phases (not measured here) |
| `width: X%` | `GeometryReader` copied at every call site, or `scaleEffect(x:)` | One kit view/modifier with one `GeometryReader`. `scaleEffect` is not the same picture at fractional widths (css-to-swiftui.md) |
| `box-shadow` with negative spread | `.shadow(radius:)` chains | One kit modifier that shrinks the shape and blurs it |
| Link inside a sentence | `Button` + `Text` in an `HStack` | One `Text` from an `AttributedString` with `.link`, click through `.environment(\.openURL, OpenURLAction { … .handled })` |
| `children` / slot props | `AnyView` | Generic parameters; an optional slot is `Slot? = EmptyView?.none` (one init, no overloads) |
| `key={i}` / `key={id + state}` | `id: \.offset`, `.id("\(…)")` | Stable data identity; a state-dependent `.id` remounts the subtree and loses focus and fields |
| Absolutely sized spacers, `top-1/2` | `Color.clear.frame(height:)`, `.position`, `.offset` | Stack `spacing`, alignment guides, `overlay(alignment:)` |
| Scroll-to / sticky headers | SwiftUI `scrollTo`, `scrollPosition`, `pinnedViews` | Only valid inside a SwiftUI `ScrollView`; in a wrapped `NSScrollView` they silently do nothing (root-causes §26) |
