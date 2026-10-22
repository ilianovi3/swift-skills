# Patterns: native fixes that keep the look

Working code distilled from a production macOS app (Swift 6, macOS 15+). Adapt names; keep the structure. Each
pattern names the root cause it answers (`root-causes.md`).

## Contents
- HostedStack — AppKit partition of a long document (§1, §3)
- PerItemFlags — hover/selection without fan-out (§3)
- InlineDecorations — chips inside one `Text` (§4) — superseded for paragraphs that wrap: see AttachmentParagraph
- AttachmentParagraph — chips as TextKit 1 attachments, SwiftUI views placed on their rects (§4)
- WordReveal — per-word animation without views per word (§4)
- CachedFlowLayout — measure once (§5)
- ScrollCover — no hover during scroll without toggling content (§8)
- WindowDrag — custom title bars without drag-region recompute (§2)
- ThumbnailCache — images in lists (§9)
- LayerAnimations — idle loops (shimmer, pulsing dot, spinner) off the main thread

---

## HostedStack

Each row in its own `NSHostingController`; AppKit prunes hit-testing by frame, SwiftUI walks one row. All rows are
built up front (no laziness). Pass the whole SwiftUI environment down, or rows lose fonts, scale, colors, actions.

```swift
import AppKit
import SwiftUI

public struct HostedStack: NSViewRepresentable {
    let rows: [AnyView]
    public init(rows: [AnyView]) { self.rows = rows }

    public func makeNSView(context _: Context) -> HostedStackView { HostedStackView() }

    public func updateNSView(_ view: HostedStackView, context: Context) {
        view.set(rows.map { AnyView($0.environment(\.self, context.environment)) })
    }

    public func sizeThatFits(_ proposal: ProposedViewSize, nsView view: HostedStackView, context _: Context) -> CGSize? {
        guard let w = proposal.width, w.isFinite, w > 0 else { return nil }
        return CGSize(width: w, height: view.height(width: w))
    }
}

public final class HostedStackView: NSView {
    private var hosts: [NSHostingController<AnyView>] = []
    private var heights: [CGFloat] = []
    private var measuredWidth: CGFloat = -1
    override public var isFlipped: Bool { true }

    func set(_ views: [AnyView]) {
        while hosts.count < views.count {
            let h = NSHostingController(rootView: AnyView(EmptyView()))
            h.sizingOptions = []          // the stack sizes rows; rows must not push sizes up on their own
            addSubview(h.view)
            hosts.append(h)
        }
        while hosts.count > views.count { hosts.removeLast().view.removeFromSuperview() }
        for (h, v) in zip(hosts, views) { h.rootView = v }
        measuredWidth = -1
        needsLayout = true
    }

    func height(width: CGFloat) -> CGFloat { measure(width); return heights.reduce(0, +) }

    private func measure(_ width: CGFloat) {
        guard width != measuredWidth else { return }
        // No rounding: rounding each row up accumulates into visible pixel drift.
        heights = hosts.map { $0.sizeThatFits(in: NSSize(width: width, height: .greatestFiniteMagnitude)).height }
        measuredWidth = width
    }

    override public func layout() {
        super.layout()
        measure(bounds.width)
        var y: CGFloat = 0
        for (h, ht) in zip(hosts, heights) {
            h.view.frame = NSRect(x: 0, y: y, width: bounds.width, height: ht)
            y += ht
        }
    }
}
```

Use it for the document part of a screen (blocks of a meeting, sections of an article), not for thousands of
uniform rows. Notes: `NSHostingView` has no `sizeThatFits(in:)` — use `NSHostingController`.

**Keyed variant (do this once the stack is in place).** The version above re-sets every row's root on every
`updateNSView`, so any refresh of the screen rebuilds and re-measures every row, and a live-resize step measures every
row at the new width. Measured on a 40-row document (Release, offscreen harness): open 1.75 s, rebuild with the same
data 287 ms, a resize step 187 ms. Three changes, same pixels:
- `HostedStack(key:rows:)` with `Row(id:view)`: rows keep their hosting controller by id; the root is re-set only
  when `key` (a `Hashable` revision of what the rows render — data, edits, language; not callbacks) or a snapshot of the
  environment the rows depend on (scale, color scheme, contrast, locale, reduce motion, display scale, layout
  direction and the app's own entries, compared as an `Equatable` struct) changed. Rebuild 287 → 46 ms.
- Heights cached per width (key: width in half points, ≤ 64 widths per row); on a new width measure only the rows
  within one screen of the visible rect, give the others their previous height (or the mean), and finish the rest
  per frame with `NSView.displayLink(target:selector:)` within a ~6 ms budget, skipping frames while
  `inLiveResize`. Keep the first visible row in place while rows above it change height (scroll the clip view by
  the delta). Open 1.75 s → 0.44 s for the first frame; resize step 187 → 36 ms.
- Measure with `fixedSize(horizontal: false, vertical: true)` on the row root so measure and layout share one
  proposal (SwiftUI reuses the layout cache).

Costs that remain: the deferred rows (~1.1 s on that document) still run, spread over frames — a single heavy row
can exceed the frame budget, and a scroll that starts before they finish completes them synchronously (do it, or
the scroll lands on estimated heights). Offscreen there are no display-link frames: force completion in the harness
(scroll by 1 pt) to measure it, and compare full stack heights between builds to prove nothing stayed estimated.

## PerItemFlags

```swift
@MainActor @Observable public final class HoverState {
    public private(set) var current: Item.ID?              // for the few readers that need the value
    @ObservationIgnored private var flags: [Item.ID: Flag] = [:]
    @MainActor @Observable final class Flag { var on = false }

    public func isHovered(_ id: Item.ID) -> Bool { flag(id).on }   // rows read only their own flag

    public func set(_ id: Item.ID?) {
        guard current != id else { return }
        if let old = current { flags[old]?.on = false }
        current = id
        if let id { flag(id).on = true }
    }

    private func flag(_ id: Item.ID) -> Flag {
        if let f = flags[id] { return f }
        let f = Flag(); flags[id] = f; return f
    }
}
```

Pass it as an object (environment or init), never as a value: a value in the environment re-renders the whole
subtree on each change.

## InlineDecorations

A paragraph with chips stays one `Text`. Each chip reserves its exact width inside the text (an invisible run in the
chip's font plus empty-image spacers for padding and avatar); the real chip view is drawn behind at the run's rect;
an interactive button sits in front. Rects come from `Text.LayoutKey` (iOS 18 / macOS 15).

```swift
struct ChipMark: TextAttribute { let index: Int }

func spacer(_ w: CGFloat) -> Image { Image(size: CGSize(width: w, height: 1)) { _ in } }   // height 1: no line growth

func chip(_ name: String, index: Int) -> Text {
    let mark = ChipMark(index: index)
    return Text(spacer(leadingPadding + avatarWidth + gap)).customAttribute(mark)
        + Text(verbatim: name.replacingOccurrences(of: " ", with: "\u{00A0}"))   // never wrap inside a chip
            .font(chipFont).foregroundStyle(.clear).customAttribute(mark)          // invisible but still read by VoiceOver
        + Text(spacer(trailingPadding)).customAttribute(mark)
}

paragraphText                                    // Text built by concatenating plain runs and chip(...) runs
    .backgroundPreferenceValue(Text.LayoutKey.self) { layouts in
        GeometryReader { proxy in
            ForEach(chipRects(layouts, proxy), id: \.index) { r in
                ChipView(...)                                   // the same component used elsewhere: pixel-identical
                    .frame(width: r.rect.width, height: chipHeight)
                    .position(x: r.rect.midX, y: r.lineMidY)
            }
        }
    }
    .overlayPreferenceValue(Text.LayoutKey.self) { layouts in /* invisible buttons/menus at the same rects */ }

func chipRects(_ layouts: [Text.LayoutKey.AnchoredLayout], _ proxy: GeometryProxy) -> [(index: Int, rect: CGRect, lineMidY: CGFloat)] {
    var out: [Int: (CGRect, CGFloat)] = [:]
    for l in layouts {
        let o = proxy[l.origin]
        for line in l.layout {
            // Vertical anchor: the middle of the line box (size × line-height), which is where a flex/flow
            // layout centers an inline element (`align-middle`). Not the run's glyph box.
            let mid = line.typographicBounds.rect.offsetBy(dx: o.x, dy: o.y).midY
            for run in line {
                guard let m = run[ChipMark.self] else { continue }
                let r = run.typographicBounds.rect.offsetBy(dx: o.x, dy: o.y)
                out[m.index] = (out[m.index].map { $0.0.union(r) } ?? r, mid)
            }
        }
    }
    return out.sorted { $0.key < $1.key }.map { ($0.key, $0.value.0, $0.value.1) }
}
```

Deployment target 26+ (macOS 26 / iOS 26): `Text + Text` is deprecated there (it still builds without warnings for
lower targets). Build the paragraph with interpolation instead — `Text("\(prefix)\(chip)\(rest)")` — and confirm that
`customAttribute` runs survive by reading them back from `Text.LayoutKey` once; keep `+` behind the version check if
you support both.

Trap: preference closures (`backgroundPreferenceValue`/`overlayPreferenceValue` with a `GeometryReader`) run again on
scroll frames; computing rects there showed up as ~300 ms per 20 s of scrolling. Compute rects once per layout
(e.g. `onPreferenceChange` into `@State`, keyed by text and width) and only draw in the closures.

Lessons: drawing the chip's text inside the `Text` and only its background behind was a dead end — run-level
`baselineOffset` replaces (not adds to) the paragraph's offset, and fonts differ in metrics; rendering the real chip
view behind an invisible placeholder is exact. Verify with a pixel diff (capsule rows and text ink rows within 1 px).

Trap (2026-10, measured): the placeholder is **not atomic**. The leading spacer image, the invisible name and the
trailing spacer are separate line-break opportunities even with NBSP inside the name: a sweep of widths 300…700 pt
over a 2-line summary with 4 chips broke a chip across lines at 258 of 401 widths; the union rect then spans the end of
one line and the start of the next, the chip is drawn over the last word and a hole stays where the invisible name sits.
Fix by structure, not by more spacers: AttachmentParagraph.

## AttachmentParagraph

A paragraph with inline chips (people, time links, tags) that must wrap like the web: a TextKit 1 `NSTextView`
(non-editable, selectable) per paragraph; every chip is one `NSTextAttachment` character whose cell draws nothing and
only reserves the chip's size (`cellSize`, `cellBaselineOffset`). The line breaker never splits one character, a comma
after it stays on its line (UAX #14), ⌫/selection/copy treat it as one unit, VoiceOver reads the cell's
`accessibilityLabel`. The chip views themselves stay SwiftUI (same component as everywhere — pixel-identical, hover,
popovers) and are placed by a custom `Layout` in the same pass:

```swift
struct ParagraphLayout: SwiftUI.Layout {             // subviews[0] = the NSTextView host, then one view per attachment
    let engine: Engine                               // owns storage, NSLayoutManager, NSTextContainer, the NSTextView
    let content: Engine.Content                      // runs + style + scale: Hashable, rebuilds storage only on change
    // Chip sizes do not depend on the proposal: measure them (and compare `content`) once per content/subviews change,
    // not in every sizeThatFits / explicitAlignment / placeSubviews — a window resize then never re-measures chips.
    func makeCache(subviews: LayoutSubviews) { sync(subviews) }
    func updateCache(_: inout (), subviews: LayoutSubviews) { sync(subviews) }
    private func sync(_ subviews: LayoutSubviews) {
        MainActor.assumeIsolated { engine.update(content, sizes: subviews.dropFirst().map { $0.sizeThatFits(.unspecified) }) }
    }
    func sizeThatFits(proposal: ProposedViewSize, subviews _: LayoutSubviews, cache _: inout ()) -> CGSize {
        MainActor.assumeIsolated { engine.size(width: proposal.width) }                                  // layout at that width
    }
    func placeSubviews(in b: CGRect, proposal _: ProposedViewSize, subviews: LayoutSubviews, cache _: inout ()) {
        let rects = MainActor.assumeIsolated { engine.attachmentRects(width: b.width) }   // container = placed width
        subviews[0].place(at: b.origin, proposal: ProposedViewSize(b.size))
        for (i, v) in subviews.dropFirst().enumerated() { v.place(at: CGPoint(x: b.minX + rects[i].minX, y: b.minY + rects[i].minY), proposal: ProposedViewSize(rects[i].size)) }
    }
    // Horizontal guides implicit: the default merges subviews' guides by calling placeSubviews at (0,0) on every
    // candidate size while the parent measures — each call re-lays the TextKit container at a width never shown.
    func explicitAlignment(of _: HorizontalAlignment, in _: CGRect, proposal _: ProposedViewSize, subviews _: LayoutSubviews, cache _: inout ()) -> CGFloat? { nil }
    // + explicitAlignment(of: .firstTextBaseline / .lastTextBaseline) from the line fragments, or rows that align
    //   bullets and labels by first baseline lose it (a custom Layout has no text baseline by default).
}
// The text view restores the layout of its own frame before drawing (measurements at other widths stay legitimate):
// override func viewWillDraw() { if bounds.width > 0 { engine?.place(bounds.width) }; super.viewWillDraw() }
```

Rules learned on the way:
- The container width is the engine's, not the view's (`widthTracksTextView = false`): measure and place at the same
  width — and since SwiftUI also measures and even places at widths that never reach the screen (root-causes §20),
  re-lay at the frame width in `NSTextView.viewWillDraw` when the current lines don't fit it. An `NSViewRepresentable.sizeThatFits` that sets `containerSize` for a probe (SwiftUI probes 0, ∞, `nil` and
  other widths without changing the frame) must restore the frame width afterwards — otherwise the text wraps at the
  probe width and overflows the frame (an editor whose text ran under the panel below it).
- Round the reserved width up to a whole point: TextKit 1 advances the next glyph by the integer part of the cell
  width, and a 106.56 pt chip overlapped the following space by 0.56 pt.
- Attachment rect: `lineFragmentRect(forGlyphAt:)` + `location(forGlyphAt:)` gives the baseline; bottom = baseline −
  `cellBaselineOffset`. Do not give the attachment character the paragraph's `.baselineOffset` attribute — fold the
  text's lift into the cell offset, so the rect math stays exact.
- CSS `vertical-align: middle` = cell offset `lift + xHeight / 2 − h / 2` (+1 for `translate-y-[-1px]`); a time link
  is baseline-aligned: offset `lift − (h − firstBaseline)` with the baseline read from the SwiftUI view's dimensions.
- `foregroundStyle` set outside a representable does not reach `NSTextView` (no public environment value): the text
  color, strikethrough, underline and monospaced digits become parameters of the paragraph view; audit call sites for
  `.foregroundStyle` after the paragraph.
- `ImageRenderer` does not draw `NSView`s: snapshot paragraphs with `cacheDisplay(in:to:)` of the hosting view, and
  measure heights with `NSHostingController.sizeThatFits(in:)`.
- A non-selectable paragraph inside a button row must return `nil` from `hitTest`, and display paragraphs must not be
  key views (`canBecomeKeyView = false`), or ⇥ stops at every paragraph of the screen.
- Line metrics equal to `Text`: set every line through `NSLayoutManagerDelegate.shouldSetLineFragmentRect`
  (height = CSS line exactly, `baselineOffset` = the web baseline) instead of a `.baselineOffset` attribute on the text —
  the attribute approach was 0.5–3 pt off and a line taller; with the delegate, ink rows of `Text` and the engine match
  to the pixel in all tested styles. Report the `firstTextBaseline` guide the way `Text` does (one font size below the
  line top, not the drawn baseline), or rows aligning a `Text` bullet with the paragraph shift.
- `location(forGlyphAt:)` of an attachment glyph is the bottom of its cell (rounded), not the baseline: compute the
  rect from the line's known baseline, or the chip lands ~5 pt low.
- A proposal of width 0 is a real width (the narrowest layout): stacks probe 0 and ∞ to learn flexibility; treating 0
  as "unbounded" made `HStack { "—"; paragraph }` wrap the paragraph early.
- Word-by-word reveal on the engine: temporary attributes of the layout manager per word range, driven by an
  `Animatable` modifier on the text host (SwiftUI's clock, the same curve as the chip views) — a `CADisplayLink` of its
  own never ticks in an off-screen window, and the text stayed at 10 % opacity in snapshots.
- An editable `NSTextView` sized only through `NSViewRepresentable.sizeThatFits` kept the height of the previous text
  in a narrow column after typing; a custom `Layout` around it that measures the text at the proposed width each time
  (relayout keyed by an edit counter) fixed it; the container follows the frame (`widthTracksTextView` + the
  `viewWillDraw` guard), not `placeSubviews` — that one also runs for speculative sizes (root-causes §20).
- Measure the paragraph's width from its line fragments (`enumerateLineFragments`, max `usedRect.maxX`), not from
  `NSLayoutManager.usedRect(for:)`: with an `NSTextView` on the container that returns the whole container width (a
  172 pt line reported 100 000 at the one-line probe), and every flow/stack placing the paragraph thinks it fills the
  row — chips after it wrapped to a new line, a screen grew by 201 pt.
- Placing at the paragraph's own width after measuring at the proposed width needs no new layout: at any width between
  the longest line and the container the lines are the same (greedy breaking). Without that check every placement
  re-laid out the paragraph (`atomRects`/baselines → `ensureLayout` again).
- The narrowest probe (proposal 0): lay out at the widest unbreakable word (from the one-line layout), not at 1 pt —
  at 1 pt TextKit breaks words into one line per character (343 → 78 ms for 200 paragraphs in Debug).
- No `kCTLanguageAttributeName` on the text (root-causes §18): an ICU break iterator per layout and browser-unlike breaks.
- An `NSTextView` that joins a window subscribes to frame changes of every view (root-causes §19): remove that
  observation for display paragraphs in `viewDidMoveToWindow` and `viewDidMoveToSuperview`.
- A WORD JOINER (U+2060) used as an invisible padding carrier before a fragment after a space forbids the line break
  after that space (UAX #14 LB11 outranks LB18) — the space and the fragment travel to the next line together; put the
  padding as kern on the space instead. Kern on an attachment character is ignored by TextKit 1.
- Cost (Release, 200 paragraphs × 40 words × 2 chips, width 600): 390 ms vs 124 ms for the same text as `Text`; the
  engine without chips is +0.09 ms per paragraph over `Text`, two SwiftUI chips in a row alone cost 185 ms — the chips,
  not the text engine, dominate. Window resize after the fixes above: equal to or faster than the per-word flow it
  replaced (kitchen screen 1.01/0.90 of the base, document sheet 0.90/0.84). Plain paragraphs stay `Text`.

## WordReveal

```swift
struct WordIndex: TextAttribute { var i: Int }

struct RevealRenderer: TextRenderer, Animatable {
    var count: Int
    var elapsed: Double
    var animatableData: Double { get { elapsed } set { elapsed = newValue } }

    func draw(layout: Text.Layout, in ctx: inout GraphicsContext) {
        for line in layout {
            for run in line {
                var c = ctx
                if let w = run[WordIndex.self] { c.opacity = opacity(w.i, of: count, at: elapsed) }
                c.draw(run)
            }
        }
    }
}
// Tag each word run with WordIndex; .textRenderer(RevealRenderer(count: n, elapsed: elapsed));
// withAnimation(.linear(duration: total)) { elapsed = total }. Decorations behind chips use the same opacity function.
```

## CachedFlowLayout

```swift
struct Flow: Layout {
    struct Cache { var sizes: [CGSize] }
    func makeCache(subviews: Subviews) -> Cache { Cache(sizes: subviews.map { $0.sizeThatFits(.unspecified) }) }
    func updateCache(_ cache: inout Cache, subviews: Subviews) { cache = makeCache(subviews: subviews) }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout Cache) -> CGSize { /* wrap cache.sizes */ }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout Cache) { /* place */ }
}
```

## ScrollCover

```swift
struct CoveredScroll<Content: View>: View {
    @ViewBuilder let content: Content
    @State private var scrolling = false

    var body: some View {
        ScrollView {
            content.overlay {
                Color.clear.contentShape(Rectangle()).allowsHitTesting(scrolling).accessibilityHidden(true)
            }
        }
        .onScrollPhaseChange { _, phase in
            scrolling = phase.isScrolling
            if !scrolling { rehover() }
        }
    }

    // SwiftUI re-hit-tests only on mouse movement: after the scroll stops, post a move at the same spot.
    private func rehover() {
        guard let w = NSApp.keyWindow,
              let e = NSEvent.mouseEvent(with: .mouseMoved, location: w.mouseLocationOutsideOfEventStream,
                                         modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                                         windowNumber: w.windowNumber, context: nil, eventNumber: 0, clickCount: 0,
                                         pressure: 0) else { return }
        NSApp.postEvent(e, atStart: false)
    }
}
```

## WindowDrag

```swift
// Window setup (AppKit): no title-bar dragging → no drag-region recompute over SwiftUI content.
window.isMovable = false

// Every custom title bar / toolbar strip:
TitleBar().gesture(WindowDragGesture())   // macOS 15+, also handles double-click zoom per system setting
```

## ThumbnailCache

```swift
import ImageIO

@MainActor final class Thumbnails {
    static let shared = Thumbnails()
    private let cache = NSCache<NSString, NSImage>()

    func image(_ url: URL, px: Int) -> NSImage? {           // sync: cache hit or local file
        let key = "\(url.absoluteString)#\(px)" as NSString
        if let i = cache.object(forKey: key) { return i }
        guard url.isFileURL, let d = try? Data(contentsOf: url), let i = Self.thumb(d, px) else { return nil }
        cache.setObject(i, forKey: key); return i
    }

    func load(_ url: URL, px: Int) async -> NSImage? {      // remote
        if let i = image(url, px: px) { return i }
        guard let (d, _) = try? await URLSession.shared.data(from: url), let i = Self.thumb(d, px) else { return nil }
        cache.setObject(i, forKey: "\(url.absoluteString)#\(px)" as NSString); return i
    }

    private nonisolated static func thumb(_ d: Data, _ px: Int) -> NSImage? {
        guard let s = CGImageSourceCreateWithData(d as CFData, nil),
              let cg = CGImageSourceCreateThumbnailAtIndex(s, 0, [
                  kCGImageSourceCreateThumbnailFromImageAlways: true,
                  kCGImageSourceCreateThumbnailWithTransform: true,
                  kCGImageSourceThumbnailMaxPixelSize: max(px, 1)] as CFDictionary) else { return nil }
        return NSImage(cgImage: cg, size: .zero)
    }
}
// In the view: px = Int((size * displayScale).rounded(.up)); show image(url:px:) ?? placeholder;
// .task(id: url) { if image(...) == nil { loaded = await load(...) } }
```


## LayerAnimations

Endless SwiftUI animations — `repeatForever`, a `TimelineView(.animation)` per skeleton bar, a fake waveform — keep the
main thread busy at display rate for as long as they are visible, even when nothing else changes. A screen with 60–70
shimmering bars runs ~70 body updates per frame at 120 Hz. Move the loop to Core Animation: the render server runs it
with no main-thread work, and the curves and durations can be kept identical.

- Shimmer: one `CAGradientLayer` per bar with a repeating `CABasicAnimation` on `locations` or a translation; take the
  phase from `CACurrentMediaTime()` modulo the period so bars stay in sync like the old shared clock.
- Pulsing dot: `CABasicAnimation(keyPath: "opacity")`, `autoreverses`, `repeatCount = .infinity`, same timing function.
- Spinner: rotation on `transform.rotation.z`, linear, `repeatCount = .infinity`.
- Honour Reduce Motion (`NSWorkspace.shared.accessibilityDisplayShouldReduceMotion`) by not adding the animation.
- A meter without real levels: cap `TimelineView(.animation(minimumInterval: 1/60))` or drive it from real input.

Gotchas when the layer lives in an `NSViewRepresentable` (verified headlessly):
- A representable that is proposed no size measures 0 (where `GeometryReader`/`Color.clear` would take 10): size the
  slot with `Color.clear.frame(...)` and put the representable in `.overlay`.
- AppKit resets `anchorPoint` on a view's backing layer whenever its frame changes — animate a sublayer you own, or
  re-apply the anchor in `layout()`.
- On a flipped view the layer's mask is top-down too, and a positive `rotation.z` turns clockwise.
- Inherited SwiftUI values (foreground colour, colour scheme) do not reach a nested `NSHostingView` by themselves:
  pass the whole environment with `.environment(\.self, env)` read from `@Environment(\.self)`.

Verify: the trace of an idle screen should show no SwiftUI updates per frame; compare shimmer and dot side by side with
the old build (blend of CA vs SwiftUI colours and rounded edges can differ by a pixel).
