# Root causes, how to confirm them, and the native fixes

Each entry: why it costs, the signature to look for (`scripts/analyze_trace.py` buckets and
`scripts/trace_callers.py`), the fix, and traps. Numbers come from real recordings of a production macOS app
(Release, M-series, 120 Hz) and are there to calibrate expectations, not to promise them.

## Contents
1. SwiftUI hit-testing fan-out (macOS)
2. Window drag regions under a hidden title bar (macOS)
3. Observation fan-out from shared hover/selection state
4. Views per word: flow layouts for inline text
5. Layouts that re-measure every pass
6. CPU text rasterization in rows
7. Laziness that moves cost into scrolling
8. Toggling hit-testing or visibility on big subtrees
9. Images in lists
10. Frame feedback loops
11. Menu bar extras, icons and other small constant costs
12. When the main thread is idle but frames are slow
13. Things that look guilty but were not

---

## 1. SwiftUI hit-testing fan-out (macOS)

**Why.** To find the view under the cursor, SwiftUI walks responders (`HoverResponder`, `ContentShapeResponder`,
`GestureResponder`, `StyledTextResponder` for every `Text` that might contain links) and transforms the point into
each one's space. It does this up to three times per frame while scrolling: AppKit's cursor update in the display
cycle (`-[_NSTrackingAreaAKManager setCursorForMouseLocation:]`), scroll-wheel routing (`_routeScrollWheelEvent`) and
SwiftUI's own hover update (`EventBindingManager.enqueueHoverUpdateIfNeeded`). On a non-lazy screen with thousands of
buttons, chips, tooltips and hover zones this was 2.5 s of 7 s main-thread time per 20 s of scrolling, and it made
lag depend on what passed under the cursor ("it lags on some parts of the screen").

**Confirm.** Bucket `hover hit-test` (`PlatformHitTestingManager.hitTest`) is large; `trace_callers.py callers` shows
the three sources above; `inside` shows `HoverResponder.containsGlobalPoints` and friends. Scrolling with the cursor
over the scroll bar is clearly smoother than over content.

**Fix.** Let AppKit prune before SwiftUI searches: host each row of a long document in its own `NSHostingView`
inside an AppKit stack (pattern `HostedStack` in `patterns.md`). `NSView.hitTest` only descends into the row whose
frame contains the point, so SwiftUI walks one row instead of the whole screen. Build all rows up front, exactly like
a `VStack` (no laziness, see §7). In the production case: hit-testing 2.6 → 0.9 s, frames at 120 Hz 74 → 89 %.

**Traps.**
- A custom `contentShape` on a row does not stop the walk — SwiftUI still asks the children.
- Removing off-screen rows from hit-testing with `allowsHitTesting(visible)` + `onScrollVisibilityChange` cut the
  search by 40 % but every toggle redraws text (§8). Prefer the AppKit partition.
- Separate hosting views do not share one layout pass: a change every row observes now re-lays out every row
  separately. Narrow observation first (§3).
- Replacing system checkboxes (`NSButton`) with SwiftUI-drawn ones did not change anything; platform views were not
  the cause, the number of SwiftUI responders was.
- iOS has no cursor or hover in the common case; the same tree costs much less there. The analogous fix on iOS is
  ordinary: lazy containers with cheap rows, `UICollectionView` for very long lists.

## 2. Window drag regions under a hidden title bar (macOS)

**Why.** With `.windowStyle(.hiddenTitleBar)` (content extending under the title strip) AppKit asks which views
cover the title area to compute draggable regions, and SwiftUI answers by walking every interactive view in the
window, including the whole scroll content — whenever hover or layout changes, i.e. every frame of scrolling.
Measured at 37–59 % of the main thread on content-heavy screens.

**Confirm.** `_resetDragMargins` / `_regionForOpaqueDescendants` high in the profile; a test build with a regular
title bar removes it.

**Fix.** Keep the look, stop AppKit from asking: `window.isMovable = false`, and make your own title bars draggable
with SwiftUI `WindowDragGesture()` (macOS 15+), which also handles double-click zoom per the system setting. Verify
dragging and double-click on every bar that used to act as a title bar. Transcript scroll went from 94–170 ms/s of
hitches to 0–2.

## 3. Observation fan-out from shared hover/selection state

**Why.** A single `@Observable` property such as `hoveredID` read by every row (`row.id == model.hoveredID`)
invalidates all rows whenever the cursor crosses a row — which happens constantly while scrolling under a stationary
cursor. In one hosting view SwiftUI absorbs it cheaply; split into many hosts (§1) every host re-lays out.

**Confirm.** Many `DynamicBody` updates per second, row `body` getters in the app symbols, cost grows with row count.

**Fix.** Per-item flags (pattern `PerItemFlags`): each row reads only its own flag; changing the hovered item
flips two flags, so two rows update. Keep the whole value for the few readers that need it (a ribbon, a minimap).

## 4. Views per word: flow layouts for inline text

**Why.** Rich text with inline chips (mentions, tags, redactions) is often ported from the web as a wrap layout of
one view per word. A 100-word paragraph becomes 100+ views to measure, place and hit-test, and every word snaps to
whole pixels (unlike the browser).

**Confirm.** Custom `Layout.sizeThatFits` / `LayoutEngineBox.sizeThatFits` in hot frames, app symbols like
`Flow.rows`, hit-test growth when such paragraphs are on screen. In a blind A/B, paragraphs as words cost
37 ms/s of hitches against 7 ms/s as one `Text` on the same screen.

**Fix.** One `Text` per paragraph (pattern `InlineDecorations`): reserve each chip's width inside the text
(invisible run in the chip's font plus image spacers for padding and avatar), read the run rectangles from
`Text.LayoutKey` (iOS 18 / macOS 15), draw the chip view behind at those rects and put the interactive button
in front. Word-by-word reveal animations become a `TextRenderer` that sets opacity per tagged run. Keep the word
layout only where an arbitrary interactive view must sit inside the line.

## 5. Layouts that re-measure every pass

**Why.** A custom `Layout` that calls `subview.sizeThatFits(.unspecified)` in both `sizeThatFits` and
`placeSubviews` measures every child on every layout pass; window resize runs a pass per frame.

**Fix.** Measure natural sizes once in `makeCache` (they do not depend on the proposed width for single-line items),
then only break lines per width. Invalidate in `updateCache` when subviews change.

## 6. CPU text rasterization in rows

**Why.** Text with an exact CSS-like line height (`.lineHeight(.exact)` on macOS 26 / iOS 26, or attributed text with
paragraph styles) takes the TextKit 2 path and is rasterized on the CPU. If the text shares a layer with a hover
background, every hover change redraws the text.

**Confirm.** `CABackingStoreUpdate_` bucket grows with hover or scroll.

**Fix.** Give row content its own layer (`.compositingGroup()` on the row's content, background outside it) so
hover only recomposites; prefer a fixed frame height for single-line labels instead of exact line height in hot
lists; check pixel parity after.

## 7. Laziness that moves cost into scrolling

**Why.** `LazyVStack`/lazy grids help long, uniform, cheap rows. For a document of heterogeneous, expensive blocks
they move build, layout and text rasterization into the middle of scrolling: one lazy block grid turned a smooth
scroll (1–6 ms/s) into 46–63 ms/s, and was rejected twice.

**Rule.** Lazy when rows are cheap and many (transcripts, lists of thousands); build-all-then-partition (§1) when
rows are expensive and few dozen. Opening and resizing such a document is then the remaining cost: lay out visible
rows first and use cached heights for the rest, like `NSTableView` does.

## 8. Toggling hit-testing or visibility on big subtrees

**Why.** `.allowsHitTesting(flag)` or opacity/visibility toggled on a large subtree at scroll start/stop, or per
block from `onScrollVisibilityChange`, invalidates and redraws that subtree.

**Fix.** Leave the content alone; while scrolling, put a transparent cover over it that catches the cursor
(pattern `ScrollCover`), and after the scroll ends post a synthetic `mouseMoved` at the current location so the row
under a stationary cursor highlights again.

## 9. Images in lists

**Why.** `AsyncImage` has no shared cache for decoded images and no downsampling: every row re-loads and decodes the
full image and flashes a placeholder.

**Fix.** ImageIO thumbnail at display pixel size (`kCGImageSourceThumbnailMaxPixelSize`) cached in `NSCache` keyed by
URL and size; synchronous for local files (no flicker), async for remote (pattern `ThumbnailCache`).

## 10. Frame feedback loops

**Why.** A floating panel sized from SwiftUI to a fractional width (405.5) gets rounded by AppKit, which triggers a
new layout, which sets the fractional frame again — 150 frame changes per second with nothing visible happening.

**Fix.** Apply frame updates only when they differ by more than 1 pt; round sizes yourself.

## 11. Small constant costs worth removing

- `MenuBarExtra` with live SwiftUI content rebuilds via KVO of status-bar buttons between frames (~15 % of the main
  thread on one screen). Use `NSStatusItem` with a menu built when it opens.
- Icon paths parsed from strings on every draw (5 % in Debug, 1–2 % in Release): parse once, cache.
- Localized-bundle lookups per string call: cache the bundle.
- Derived lists (sort/filter) computed in `body`: compute when inputs change.

## 12. When the main thread is idle but frames are slow

If lag windows in `analyze_trace.py --series` show fewer frames while the main thread is less busy than in smooth
windows, the app is not CPU-bound there. Check, in order:
1. Display renders vs app updates (`--series` columns): the window server renders only when the app commits. If both
   drop together, the app did not request frames.
2. Scroll-event rate: log `NSEvent` scroll events (timestamp, `phase`, `momentumPhase`) behind an environment
   variable for one recording. Trackpads deliver ~120 events/s in both finger and momentum phases; if yours do too,
   the input is fine.
3. Compare with the reference app at similar speeds. In the production case the remaining 60 Hz share fell from 24 %
   to 8–10 % once the hit-testing and observation fixes landed; Safari sits at ~4 %.

## 13. Things that looked guilty but were not

Fonts (already cached), mention parsing (< 1 %), database reads on the main thread, shadows, a wave animation, a
blinking record dot, system checkboxes, a 300 ms hover delay idea (the cost is the search, not the reaction).
Measure before rewriting any of these.
