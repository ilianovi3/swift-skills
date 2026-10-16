# Patterns: native fixes that keep the look

Working code distilled from a production macOS app (Swift 6, macOS 15+). Adapt names; keep the structure. Each
pattern names the root cause it answers (`root-causes.md`).

## Contents
- HostedStack — AppKit partition of a long document (§1, §3)
- PerItemFlags — hover/selection without fan-out (§3)
- InlineDecorations — chips inside one `Text` (§4)
- WordReveal — per-word animation without views per word (§4)
- CachedFlowLayout — measure once (§5)
- ScrollCover — no hover during scroll without toggling content (§8)
- WindowDrag — custom title bars without drag-region recompute (§2)
- ThumbnailCache — images in lists (§9)

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
uniform rows. Notes: `NSHostingView` has no `sizeThatFits(in:)` — use `NSHostingController`. Open/resize then costs
one measure per row per width; next step for long documents is measuring visible rows first and caching heights.

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

Trap: preference closures (`backgroundPreferenceValue`/`overlayPreferenceValue` with a `GeometryReader`) run again on
scroll frames; computing rects there showed up as ~300 ms per 20 s of scrolling. Compute rects once per layout
(e.g. `onPreferenceChange` into `@State`, keyed by text and width) and only draw in the closures.

Lessons: drawing the chip's text inside the `Text` and only its background behind was a dead end — run-level
`baselineOffset` replaces (not adds to) the paragraph's offset, and fonts differ in metrics; rendering the real chip
view behind an invisible placeholder is exact. Verify with a pixel diff (capsule rows and text ink rows within 1 px).

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
