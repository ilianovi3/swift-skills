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
| `shrink-0` | `.fixedSize(horizontal: true, vertical: false)`; on a kit button that can also be `w-full` (label with `frame(maxWidth: .infinity)`), `fixedSize` kills the stretch — use a one-child `Layout` whose width is `max(proposal, ideal)` |
| `whitespace-nowrap shrink-0` button next to links in `flex gap-5` | without the rule above `HStack` gives the button less than its width and `lineLimit(1)` cuts the label to "Contin…"; with it the button keeps its width and the links wrap, as in the browser |
| `grid-cols-[minmax(0,1fr)_auto]` | `HStack { flexible.frame(maxWidth: .infinity) ; control.fixedSize() }` — the auto column sizes to content; without `fixedSize` HStack splits space and truncates the control |
| `max-w-[320px]` on a control followed by a chip (`flex flex-wrap`) | not `.frame(maxWidth: 320)` inside an `HStack`: the frame takes up to 320 of what the stack offers and the chip lands far from a short control; put the row in a wrapping `Layout` that measures children at their ideal size and places them with that size as the proposal — the frame then caps a long label (truncates) and stays at content width for a short one |
| A link inside a sentence (`<p><a>Connect X</a>, to do Y</p>`) | one `Text`: `Text(AttributedString with .link) .underline(color:) + Text(", to do Y")`, color through `.tint`, click via `.environment(\.openURL, OpenURLAction { … .handled })`; a `Button` and a `Text` side by side in an `HStack` split into two columns in a narrow container. native: no `hover:` on the link |
| `ml-auto` on a wrapped item | Push to trailing edge in a custom `Layout` or `ViewThatFits` |
| `space-y-*` on a list | spacing on the stack, not padding on each child (`.padding` on a `Group` applies to every child) |

## Wrapping rows
`flex-wrap` of chips/metadata → a custom `Layout` that measures each child once (`makeCache`) and only breaks lines
per width; center items vertically in the line when the CSS uses `items-center`/`align-middle`. For words of a
paragraph, do not wrap views at all — use one `Text` (see the main skill).
A toolbar of filters that wraps item by item leaves its last control alone on the next line at common window widths
(1280). Fix it in the reference first: put the controls that belong together into one non-wrapping `div` inside the
`flex-wrap` row, so the whole group moves down. Port the group as one `HStack` subview of the wrapping `Layout` — it is
measured and placed as a single item, exactly like the `div`. Prefer this over squeezing labels to fit one line: a
row that barely fits at the default text size breaks again at the largest one.

## Position, overlays, z-order
- `relative` + `absolute top-[11px] left-0` → `.overlay(alignment: .topLeading) { x.padding(.top, 11) }`.
- `inset-0` backgrounds → `.background { … }` (sized to the view, not its children).
- `z-*` → `zIndex` among siblings, or overlay order.
- `sticky top-0` → pinned section header / `safeAreaInset(edge: .top)`.
- `sticky bottom-0` action bar as the last child of a scroll column (a form whose buttons must stay in the first
  screen; short content — the bar right under it, long — at the bottom of the column): its position never depends on
  the scroll offset, so do not port it as a sticky offset inside the scroll content. Put the bar *outside* the
  `ScrollView` in a top-aligned `VStack`, and give the `ScrollView` `.frame(maxHeight: contentHeight)` measured with
  `onGeometryChange` on the content (start at `.infinity`; keep the state in a tiny wrapper view so a height change
  re-evaluates only it). Nothing runs per scroll frame, a focused field is never hidden under the bar (the scroll view
  ends at its line, so `scroll-pb-*` is not needed), and the scroll indicator stops at the bar. The CSS fade above the
  bar (`before:-top-4 bg-linear-to-t from-paper`) is an overlay on the bar offset upward with hit testing off.
- A button row that stops fitting at the largest text size (`flex-wrap` → two rows of buttons): in the reference hide
  the secondary labels with a container query (`@container` on the bar, `@max-[35rem]:sr-only` on the label span, a
  `title` for the tooltip); natively `ViewThatFits(in: .horizontal) { fullRow; compactRow }` as one item of the wrapping
  `Layout` — a flow that measures items `.unspecified` and re-proposes the line width only to an item wider than the line
  lets `ViewThatFits` pick the compact row exactly when the full one does not fit, no threshold needed. Put `.help` and
  an accessibility label only on the icon-only variant.
- Window traffic lights the reference draws in its own bar (three 12 px dots, `h-12 items-center px-4`) are the real
  window buttons natively, moved into the bar — never fake dots (hover glyphs, ⌥-zoom, accessibility). With a hidden
  title bar AppKit lays them out in a 28–32 pt container at the top (macOS 26: 14 pt buttons, step 23, first at x 9);
  make the container (`close.superview.superview`, not flipped) as tall as the bar and center the buttons in it,
  centering the group on the reference's dot group (the system size differs; mark it native). AppKit puts both back on
  resize, title change, appearance change, full-screen exit: observe `frameDidChange` of the container, its titlebar
  view and the three buttons and re-place synchronously (no frame at the old spot), plus `didResize` and `title` KVO —
  after a title change the zoom button moves last without posting a notification — and one coalesced async pass for
  the rest. Measure the button step once before the first move (mid-relayout frames give a wrong step), skip while
  `styleMask` has `.fullScreen` or the tab bar is visible. Shifting only the container's origin does not work: AppKit
  compensates the buttons inside it. Clicks in empty parts of a taller transparent container still reach the content.
  Test it in an unshown `NSWindow` with the same style mask (`.titled .closable .miniaturizable .resizable
  .fullSizeContentView`, transparent title bar): read button frames after `setFrame` and a `title` change. The taller
  container raises the top safe area — the hosted root needs the app's `.ignoresSafeArea(.container, edges: .top)` or
  its content slides under the bar; measure the text's line by ink rows of `cacheDisplay` (the accessibility tree of
  an unshown window is empty); snapshot the theme frame (`contentView.superview`) to get the buttons in the picture.
- `overflow-hidden rounded-*` → `.clipShape(RoundedRectangle(cornerRadius:))` (clip only what the CSS clips).
- `overflow: hidden` clips painting *and* hit testing; `.clipped()` / `.clipShape` clip painting only. Content laid out
  past its frame (a shimmer band 4× wide moved by `offset`, a scaled-to-fill image) still catches clicks outside the
  visible box and silently covers the neighbours drawn before it — a back button next to a loading skeleton stopped
  responding. Decorative animated fills get `.allowsHitTesting(false)`; content that must stay tappable gets
  `.contentShape(Rectangle())` after the clip. Unit tests cannot catch it: synthetic mouse events to an unshown window
  reach no SwiftUI button at all — check by clicking in the running app.

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
- A grid that is one focus stop (arrows move the selection, `.focusable()` + `.focusEffectDisabled()` on the grid) has no
  visible focus at all: draw the reference's `:focus-visible` ring on the selected cell while the grid is focused *from
  the keyboard* (arrow press, or `NSApp.currentEvent?.type == .keyDown` when focus arrives), drop it on click. Draw it
  inside the cell (`strokeBorder` without the negative padding of `outline-offset`): outside, later siblings and the
  scroll view's clip cover it.

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
- Keys of fields, macOS conventions (HIG: Esc cancels the current operation, Return confirms) — decide once in the kit,
  not per screen: an inline edit (`contentEditable` text) commits on Return and on blur, Esc restores the value it had
  on focus and leaves (Finder rename); a form field runs the form action on Return, Esc leaves the field keeping the
  text; inside a popover or sheet Esc closes the container. SwiftUI `TextField` does nothing on Esc by itself:
  `.onKeyPress(.escape)` on the field, leave with `window.makeFirstResponder(nil)` (no `FocusState` binding needed at
  every call site), and give popovers/sheets an environment "close" action the field calls. Store that action in an
  `Equatable` wrapper whose `==` is always true — a bare closure in `@Entry` warns and invalidates every dependent on
  each update of the presenting view.
- Multiline `TextField(axis: .vertical)` on macOS: Return submits, ⌥↩ inserts a newline natively
  (`insertNewlineIgnoringFieldEditor:`). For ⇧↩ (the web's Shift+Enter) send that same action to the first responder —
  `NSApp.sendAction(#selector(NSResponder.insertNewlineIgnoringFieldEditor(_:)), to: nil, from: nil)` — it lands at the
  caret; appending `"\n"` to the binding puts it at the end. A Return handler that sends on every modifier swallows ⌥↩:
  return `.ignored` for Option.
- The web's `if (e.nativeEvent.isComposing) return` (Japanese/Chinese input) has no automatic equivalent: SwiftUI
  `.onKeyPress` on a `TextField` sees ↩, arrows, Esc and ⌫ before the input method, so Enter during conversion sends
  the half-typed text and ⌫ while the bound text is still empty deletes a chip. Check the field editor —
  `(NSApp.keyWindow?.firstResponder as? NSTextView)?.hasMarkedText()` — and return `.ignored` while composing, in
  every key handler of a field (one helper in the kit). Testable without a window: `NSTextView().setMarkedText(…)`
  then `hasMarkedText()`.
- Web keyboard shortcuts become menu items (`Commands`), not hidden key handlers. A SwiftUI app has no Find ▸,
  Spelling and Grammar, Substitutions, Transformations or Speech until `.commands { TextEditingCommands() }`;
  `CommandGroup(replacing: .textEditing)` silently drops them all. A custom ⌘F (focus the page's search field) placed
  `CommandGroup(before: .textEditing)` makes SwiftUI strip ⌘F from the system Find… itself — no duplicate shortcut.
  Verify shortcuts without posting events: `NSEvent(cgEvent: CGEvent(keyboardEventSource: nil, virtualKey:,
  keyDown: true))` with flags, then `NSApp.mainMenu?.performKeyEquivalent(with:)` in a `.prohibited` app; a
  hand-built `NSEvent.keyEvent` with guessed characters gives false negatives (Delete is 0x7F against the item's 0x08,
  ⇧Tab is 0x19). `.keyboardShortcut(.delete)` (⌘⌫), `(.tab, modifiers: .control)` and `[.control, .shift]` all match
  real events, and ⌘-letter shortcuts still fire under a non-Latin layout.
- A plain-style `Button` around an `HStack` of icon and text hit-tests only the glyphs and the icon's strokes (the gap
  and the line box are dead), while a web `<a class="flex gap-1">` is clickable over its whole box. Put
  `.contentShape(Rectangle())` on the label; to give a tiny link a larger target without moving anything, pad inside
  the content shape and cancel the padding outside (`.padding(p).contentShape(Rectangle()).padding(-p)`), the
  `-m-* p-*` trick of the web.
- Selectable text (`user-select` is on by default on the web): `.textSelection(.enabled)` is inherited and the inner
  modifier wins, so it cannot be switched off from outside for one subtree — gate it by your own environment flag and
  turn the flag off for text inside a `Button` that is a link (a click there must stay a click). Put it on the single
  `Text` of a paragraph, before overlays that hold the inline chips' buttons, so the chips stay clickable. Selection
  stays within one `Text` (no dragging across blocks as in a browser) — a `native:` difference worth stating.
- Editing text that carries inline markup (mention tokens, redacted spans) — the web keeps chips atomic in
  `contentEditable` with `contenteditable="false"` islands carrying their source (`data-mark`), inserts them through
  `execCommand('insertHTML')` so ⌘Z covers them, and moves the caret out of a chip after an insert (the browser leaves
  it inside, where typing fails). Natively a plain `TextField` cannot hold atoms (they degrade to text and a
  diff-based token restore that guesses). Use `NSTextView` (explicit TextKit 1 stack) via `NSViewRepresentable`: each
  chip is an `NSTextAttachment` subclass holding its source, drawn by an `NSTextAttachmentCell` whose image is the kit's
  SwiftUI chip rendered with `ImageRenderer` (same look; set the window's backing scale, the environment
  `colorScheme` and `performAsCurrentDrawingAppearance`, re-render on `viewDidChangeEffectiveAppearance`). One
  character per chip gives the web behavior for free: the caret never lands inside, ⌫ deletes it whole, undo restores
  it. Serialize by walking `.attachment` runs. Vertical position: `cellBaselineOffset` = half the x-height minus half
  the image height (`vertical-align: middle`). CSS line height: min = max line height and a positive `baselineOffset`
  of the bottom part of the Blink half-leading (TextKit 1 puts the extra above the glyphs, baseline at
  `L − round(descent)`; typography.md). Give the text view its own `UndoManager`
  (`undoManager(for:)`) so the field's history dies with it; route clipboard and drag through
  `writablePasteboardTypes`/`writeSelection(to:type:)` and `readablePasteboardTypes`/`readSelection(from:type:)`
  (plain text with names outward, a private markup type between fields); handle ↩ ⇥ ↑↓ ⎋ in
  `textView(_:doCommandBy:)` (Esc arrives as `cancelOperation:` or `complete:`). A typeahead above the caret is a
  SwiftUI overlay positioned from `boundingRect(forGlyphRange:)`, not an `NSPopover` (a popover can take key focus and
  break typing); suppress it while `hasMarkedText()` (IME), flip it below when `visibleRect` has no room above.
- Text fields don't take line height: pad the field (its natural height is Blink's content area) with the Blink
  half-leading — `floor((L − round(A) − round(D)) / 2)` above, the rest below — and `baselineOffset(0)`, otherwise
  text and placeholder sit ~2 pt low; an unrounded `(L − natural) / 2` leaves them 0.5 pt off. A fixed-height input
  (`h-8`) centres the content area and snaps the baseline to a whole px (typography.md).
- `text-center tracking-[0.3em]` input (one-time code) can't be a SwiftUI `TextField` on macOS: the `prompt` ignores
  `multilineTextAlignment` (placeholder stays at the leading edge while the empty caret sits in the middle) and
  `.kerning`/`.tracking` reach only the prompt, never the typed text. Wrap `NSTextField`: one attribute set (font,
  `.kern`, centered paragraph style) for `placeholderAttributedString`, `attributedStringValue` and the field
  editor's `typingAttributes`/text storage on every change; Enter via `control(_:textView:doCommandBy:)`;
  `.focused($state)` works on the representable both ways. `autocomplete="one-time-code"` → `contentType = .oneTimeCode`.
  Keep it on one line with `cell.isScrollable = true`, not `usesSingleLineMode`: with a variable web font (Geist) the
  single-line typesetter put the baseline ~9 pt above the field (measured by ink rows in an offscreen render), while
  the system font looked fine.

## Accessibility attributes
`aria-label` → `accessibilityLabel`; `role="heading"`/`h1–h6` → `.accessibilityAddTraits(.isHeader)`;
`aria-selected` → `.isSelected`; `title` → `.help` (also a tooltip — mind density); decorative icons →
`accessibilityHidden(true)`.

What these become on macOS (AX probe of an offscreen `NSHostingView` via `AXUIElementCopyAttributeValue`):
- `.isHeader` turns `Text` into role `AXHeading`: the string moves from `AXValue` to `AXDescription`. An editable title
  with `.isHeader` keeps its text in `AXValue` and the placeholder becomes the label. XCUITest with Xcode 27
  evaluates queries inside the app when it has an automation session, and that path did not match `AXHeading` — neither
  `staticTexts["Title"]` nor `label == "Title"` — while the failure dump (a local snapshot) showed a StaticText with
  that label. Setting `XCTDisableRemoteQueryEvaluation = YES` in the runner's `UserDefaults` (read on every query;
  e.g. from the UI-test bundle's `NSPrincipalClass` init) sends queries down the local path
  (`_matchingSnapshotsForLocallyEvaluatedQuery`, seen in the `XCUIElementQuery _executeWithError:` disassembly), which
  filters the same kind of snapshot the dump shows.
- `LazyVStack` is an `AXOpaqueProviderList` (role description "list", XCUITest type `.other`); the accessibility
  audit reports it as "Element has no description". `.accessibilityLabel` on the `LazyVStack` names the list and
  leaves its rows alone.
- Every `NSHostingView` (window root, a host per row) is an `AXGroup`/`AXHostingView` without `AXEnabled` — the
  audit reports it "Disabled, no description"; `setAccessibilityElement(false)` on the host is ignored (the host
  overrides `isAccessibilityElement()`), `setAccessibilityLabel` is honoured. A host you create: subclass
  `NSHostingView` with `isAccessibilityElement() -> false` — the group disappears, its content joins the enclosing
  group and `AXParent` of the children stays consistent (AppKit reports the unignored ancestor). A host inside an
  `NSHostingController` (needed for `sizeThatFits(in:)`): `object_setClass(controller.view, ThatSubclass.self)`
  after checking `type(of: view) == NSHostingView<Content>.self`. The window root SwiftUI creates can't be
  subclassed — label it (`window.contentView?.setAccessibilityLabel(appName)`). Overriding the container's
  `accessibilityChildren()` to flatten instead breaks `AXParent` and fails the audit's parent/child check.
- `aria-hidden={cond}` must not become `.accessibilityHidden(cond)`: with `false` the modifier is not neutral, it
  un-hides every descendant marked `.accessibilityHidden(true)` (a hidden window-drag background surfaced as a
  full-width `AXUnknown` element, audit "Unknown role"). Use `.accessibilityHidden(true, isEnabled: cond)` (macOS 15,
  iOS 18) — "unchanged" when disabled; a grep in lint for `accessibilityHidden([^t]` keeps it that way.
