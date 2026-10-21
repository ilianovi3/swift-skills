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
14. A non-lazy container inside a lazy stack
15. Rebuilds the framework cannot skip: unchanged data, uncomparable inputs, equal writes
16. Core ML first load after every install or update
17. Whole audio files in memory for a speech model

---

## 1. SwiftUI hit-testing fan-out (macOS)

**Why.** To find the view under the cursor, SwiftUI walks responders (`HoverResponder`, `ContentShapeResponder`,
`GestureResponder`, `StyledTextResponder` for every `Text` that might contain links) and transforms the point into
each one's space. It does this up to three times per frame while scrolling: AppKit's cursor update in the display
cycle (`-[_NSTrackingAreaAKManager setCursorForMouseLocation:]`), scroll-wheel routing (`_routeScrollWheelEvent`) and
SwiftUI's own hover update (`EventBindingManager.enqueueHoverUpdateIfNeeded`). On a non-lazy screen with thousands of
buttons, chips, tooltips and hover zones this was 2.5 s of 7 s main-thread time per 20 s of scrolling, and it made
lag depend on what passed under the cursor ("it lags on some parts of the screen").

Scrolling is not the only trigger. SwiftUI re-runs the search at the end of **every render frame in which responders
moved**: `ViewGraphRootValueUpdater.render` → `UpdateGroup.dispatchActions` → `enqueueHoverUpdateIfNeeded` →
`NSHostingView.didRequestHoverUpdate` → `HitTestBindingResponder.bindEvent` → `ViewResponder.hitTest`. A 0.25 s
"rows slide into place" animation after a filter change is 30 frames × one full search while the cursor rests over the
list; in a recording of filter switching that chain was 1.75 s of 7.7 s main-thread time, and a single `mouseMoved`
event over the same list cost 10–18 ms. Note the nesting: when the list lives in a `ScrollView`, the search descends
through the platform `NSScrollView` (`PlatformViewResponderBase.containsGlobalPoints` → `NSScrollView.hitTest` →
`NSClipView` → `PlatformGroupContainer.hitTest` → `PlatformHitTestingManager.hitTest`), so the `hover hit-test` bucket
of `analyze_trace.py` sits *inside* the `SwiftUI render` bucket — do not add them up.

**Confirm.** Bucket `hover hit-test` (`PlatformHitTestingManager.hitTest`) is large; `trace_callers.py callers` shows
the three sources above; `inside` shows `HoverResponder.containsGlobalPoints` and friends. Scrolling with the cursor
over the scroll bar is clearly smoother than over content.

**Fix.** Let AppKit prune before SwiftUI searches: host each row of a long document in its own `NSHostingView`
inside an AppKit stack (pattern `HostedStack` in `patterns.md`). `NSView.hitTest` only descends into the row whose
frame contains the point, so SwiftUI walks one row instead of the whole screen. Build all rows up front, exactly like
a `VStack` (no laziness, see §7). In the production case: hit-testing 2.6 → 0.9 s, frames at 120 Hz 74 → 89 %.

**When the partition does not pay.** Every hosting view on the path costs a fixed amount per search (its own
`PlatformHitTestingManager.hitTest`, `ViewRendererHost.updateViewGraph`, the AppKit descent) — about 0.3 ms offscreen —
so it only wins when the responders it fences off cost more than that: thousands of chips and words in a document, yes;
a list of ~15 visible rows with a button, hover, drag, menu and a few tooltips each, no. Measured on such a list with one
`NSHostingView` per lazy row (pooled hosts, rows keyed so an unchanged row is not re-rooted): a search *beside* the rows
fell 0.6 → 0.3 ms (that is all the rows cost), a search *on* a row stayed 0.5–0.7 ms (the inner host ate the saving),
and the first pass of a switch that inserts rows rose 27–31 → 46–52 ms — about 3.5 ms per new row even from a pool
(its own graph, `NSHostingController.sizeThatFits`, two body evaluations), which would hit every row created while
scrolling. Before partitioning, measure a search beside the rows: the gap between "on a row" and "beside the rows" is the
most the partition can ever save.

**Cheap partial fix.** Make the row's static content inert: wrap labels, icons and status dots in
`Group { … }.allowsHitTesting(false)` (a `Group` inside a stack keeps the children as separate stack items, so layout and
pixels stay the same), leave the row's `contentShape`, its button/drag gestures and anything with `.help` alone. One
search went 0.9 → 0.7 ms offscreen (the per-animation total 55–66 → 48–53 ms was taken over rows that did not move —
see the `Binding?` trap in `measure.md`); the rest is the row's own responders
(`Button`, `.onHover`, `.draggable`, `.contextMenu`, avatars with tooltips) times visible rows, which only the AppKit
partition removes.

**Traps.**
- A custom `contentShape` on a row does not stop the walk — SwiftUI still asks the children
  (`ContentShapeResponder.containsGlobalPoints` → `superValue`: 562 of 611 ms in one trace were spent below the shape).
- A transparent cover on top (§8) does not make the search cheaper either: `ViewResponder.hitTest` collects every
  responder under the point with weights, there is no early exit at the topmost hit. Measured offscreen with a cover
  raised for the whole 0.25 s row animation (rows really moving): 28–34 → 27.5–32 ms of searches per switch (50–79
  searches), one search at rest unchanged — noise. The cover only keeps rows from flipping their hover state. It also
  seemed to lower the first pass of switches that insert many rows (26–29 → 19–21 ms); that was not the cover but the
  state change that raised it (`onChange(of: rowKey) { motion += 1 }` in the same update as the row change) — with
  that extra transaction SwiftUI brought back the rows removed on the previous switch with their old graphs (`onAppear`
  fired for 6 rows, `body` for none; zero `_LazyLayout_Subviews.apply` samples in any later pass), which only helps a
  harness that walks between the same two tabs. Rows new to the tree are built in the first pass either way.
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
under a stationary cursor highlights again. The cover changes *which* view wins the hit, not how much the search
costs (§1 traps) — it is a tool against hover-state churn and the redraws it causes, not against hit-testing time.

## 9. Images in lists

**Why.** `AsyncImage` has no shared cache for decoded images and no downsampling: every row re-loads and decodes the
full image and flashes a placeholder.

**Fix.** ImageIO thumbnail at display pixel size (`kCGImageSourceThumbnailMaxPixelSize`) cached in `NSCache` keyed by
URL and size; synchronous for local files (no flicker), async for remote (pattern `ThumbnailCache`).

## 10. Frame feedback loops

**Why.** A floating panel sized from SwiftUI to a fractional width (405.5) gets rounded by AppKit, which triggers a
new layout, which sets the fractional frame again — 150 frame changes per second with nothing visible happening.

**Fix.** Apply frame updates only when they differ by more than 1 pt; round sizes yourself.

**Dragging such a panel.** Let the system move it: `WindowDragGesture` on the panel's content with `isMovable = false`
(AppKit then does not keep drag regions for the window, and nothing in the app runs per frame); buttons inside keep
their clicks, a tap gesture fails on movement and lets the drag win. Do not re-place the panel from `didMove` of every
window — observe only the panel's own `didMove`, ignore frames you set yourself (within 1 pt), and while
`NSEvent.pressedMouseButtons` is non-zero only wait (re-check ~0.1 s); on release store the position as edges + offsets
of the visible frame and clamp it back on screen. A test can prove "no layout per frame": a hosting view subclass
counting `layout()` in an unshown panel, first wait out appear animations (count flat with no moves), then 240 ×
`setFrameOrigin` — measured: one pass for the whole run (SwiftUI updates the window position once), not one per frame.

## 11. Small constant costs worth removing

- `MenuBarExtra` with live SwiftUI content rebuilds via KVO of status-bar buttons between frames (~15 % of the main
  thread on one screen). Use `NSStatusItem` with a menu built when it opens.
- Icon paths parsed from strings on every draw (5 % in Debug, 1–2 % in Release): parse once, cache.
- Localized-bundle lookups per string call: cache the bundle. Measured (Release, M-series): `String(localized:
  LocalizedStringResource(key, locale:, bundle: .atURL(bundleURL)))` costs ~1.2 ms per call — it resolves the bundle and
  the language each time; a plural label in a row or an "unnamed speaker" default in a screen-wide value paid it on
  every rebuild. Build `<lang>.lproj` sub-bundles once (`Bundle(path: bundle.path(forResource: lang, ofType:
  "lproj"))`) and call `String(localized: key, bundle: langBundle, locale:)`: 20 µs, same strings and plural variants
  (the language is chosen by the bundle; `locale:` only formats arguments).
- Derived lists (sort/filter) computed in `body`: compute when inputs change.
- Client-side search on every keystroke: the cost is the no-match case, every string scanned to the end. Measured on
  500 strings × 2.5 KB (Cyrillic, `-O`, M-series): `localizedStandardContains` 18.6 ms per pass;
  `range(of:options: [.caseInsensitive, .diacriticInsensitive])` without a locale 119 ms (6× slower — do not "simplify"
  to it); haystack folded once at write time (`folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)`)
  plus `NSString.range(of:options: .literal)` with the folded query 5.4 ms; Swift `String.contains` on the folded text
  23.6 ms. Keep `localizedStandardContains` while texts are short (~700 chars → ~5 ms); precompute the haystack when
  it is not, and never decode the stored record per keystroke — store the search text next to the row.

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

Measured and rejected later (offscreen harness, Release): a dictionary instead of a linear search over ~20 people
(0.5 µs per lookup either way); a cache of dynamic colors (0.5 µs per color); `.equatable()` per node of a document
sheet plus one `Text` per paragraph with inline chips — the rebuild of the sheet got *slower* (34 → 48 ms; equality
checks and bindings per node cost more than the bodies they skip when the whole sheet re-renders anyway); a one-line
`Text` framed to the CSS line height instead of `lineHeight(.exact)` — no measurable gain offscreen and 2–5 % of the
pixels moved (baselines shift by a fraction of a point).

## 14. A non-lazy container inside a lazy stack

**Symptom.** A grouped list (sections by day, pinned headers) has many more rows built than visible: software raster
of the page grows with the list, every hover hit-test walks the responders of every built row, and each row carries
its platform views (`draggable`, `contextMenu`, `help`).

**Cause.** `LazyVStack { ForEach(groups) { Section { VStack { ForEach(rows) { Row } } } } }`: the `VStack` is one
lazy child, so the moment a group is visible *all* its rows are built — including the dozens below the fold. A grouped
list of 500 meetings builds every row of every visible month.

**Fix.** Make rows direct children of the `Section` (`Section { ForEach(rows) { Row } }`); the lazy stack then
realizes only the rows on screen. Decorations the `VStack` carried (a top rule with padding, a bottom gap) become
their own cheap lazy items (`Color.clear.frame(height:).rule(.top)` first, a footer spacer last) — pixels unchanged.
A `.transition` on rows and `.animation(value: rowIdsKey)` on the stack still animate insertions and moves.

**What it does and does not buy (measured offscreen, Release).** The synchronous update after a filter change stayed
at 10–16 ms with both structures, at 46 and at 332 rows — the lazy stack even costs 2–4 ms more in bookkeeping; the
software raster of built rows fell 98–112 → 73–79 ms on 500 rows. So this is not a fix for "the first frame is slow";
it caps the number of built rows, which is what hover hit-testing and per-row platform views scale with. If a filter
switch still feels slow after it, record with the cursor: the suspect is hover re-evaluated on every frame of the
control's own animation (§1), not the graph update.

## 15. Rebuilds the framework cannot skip: unchanged data, uncomparable inputs, equal writes

**Why.** SwiftUI skips a subtree only when it can prove the inputs are equal. A screen value that carries closures
(an action, a "patch" callback), an `AnyView` root handed to a hosting controller, or an environment value that is a
struct of closures is never equal to its previous self, so every refresh of the parent rebuilds everything under it.
`@Observable` (Swift 6.2+ macro) skips a plain `set` of an equal `Equatable` value (`shouldNotifyObservers` →
`lhs != rhs`; check with `swiftc -Xfrontend -dump-macro-expansions`), but every `_modify` write notifies, equal or not:
a nested write (`state.settings.profile = p`), a subscript (`items[i] = x`, `dict[k] = v`), `+=`, a mutating method.
Non-`Equatable` types notify on every write. And a global "data revision" bumped after a fetch that returned
the same data invalidates every screen that reads it. Each of these turns a no-op into a full rebuild.

**Confirm.** Build the screen offscreen and trigger a refresh that changes nothing (bump the revision, write the same
profile, tick a clock): the "work until quiet" should be near zero. In the production case it was 50–290 ms on a
document-like screen; writing the same user profile back after every sync (settings saved to disk, every settings
reader rebuilt) cost 3–8 ms per list-like page and 44 ms on the document-like screen, 13 ms per second of recording because the clock lived inside the
recorder's phase enum (`case recording(id, t, paused)`), so every reader of "is it recording?" re-rendered each second.

**Fix.**
- Hosted rows (patterns.md, `HostedStack`): give the stack a revision key (the content the rows render, without the
  callbacks) and compare the environment the rows depend on (scale, theme, locale, the few custom entries) as a value;
  re-set a row's root only when either changed. Rebuild with the same data 287 → 46 ms, a click that changes a
  sidebar-only value 284 → 36 ms (the rows no longer re-render).
- Environment values with closures: make them `Equatable` by a revision of the data they were built from; build the
  expensive parts (a name-matching regex, parsed texts) once per revision in a shared memo.
- Move fast-changing UI state out of the screen's `@State` into a small `@Observable` with per-item flags (§3): the
  "open moment" and search text of a side panel lived in the screen's state, so a click on a timestamp rebuilt the
  whole screen (50–68 ms); with flags it rebuilds two rows (2 ms).
- Split values that change at different rates: the phase of a recording (start/pause/stop) and its clock (every second)
  as separate properties; the timer label, the progress bar and the pause button read the clock themselves.
  13–14 → 4.5 ms per tick across a list, the recording screen and another open screen.
- Guard writes where all callers route (`set { if store.profile != newValue { store.profile = newValue } }`), not at
  each call site; same for "server answered the same": compare before bumping the shared revision (a 304 or an
  identical body is not a change).
- Cache derived values whose inputs did not change (a document built from the screen's data: 3.4 ms per rebuild).
- Two endpoints, two forms of one entity: a summary list (only my membership) and a detail (all members) written
  to the same array on every sync flip the value summary → detail → summary — two *real* changes per refresh that no
  equality guard catches. Apply the summary over the known detail (keep the detail-only fields, take the summary's
  own) and guard the detail's subscript write: every reader of the current team 3–7 ms → 0.1–0.3 ms per sync.
  Before adding an "only if changed" guard to a plain `set`, check it is not already the macro's — the guard that
  matters sits before `_modify`.

**Trap.** Keys must include everything the rows read that is not observed by the rows themselves. Observation inside a
hosted row still works (each host tracks its own reads), so app-state objects read in rows need not be in the key;
plain values passed down (a moment, a fetch state, a language) must be.

## 16. Core ML first load after every install or update

**Why.** Loading an `.mlmodelc` for the Neural Engine makes the system specialize (compile) it once and cache the
result in the app's caches (`Caches/<bundle id>/com.apple.e5rt.e5bundlecache/<OS build>/<model hash>`). The cache is
tied to the binary's code signature: a new build, an installed update or a macOS update makes the next load cold.
A speech model measured on M3 Max: Parakeet 0.6B 16–18 s cold vs 0.1 s from the cache, Whisper large-v3 80 s vs 1.6 s;
peak memory 480–500 MB cold vs 40–120 MB warm. An app that loads the model lazily on first use pays this on the first
action after each update — and if the UI shows that wait as "processing…", people read it as a slow feature.

**Confirm.** Copy the binary (inode change only) — the load stays warm; re-sign it (`codesign -f -s -`) — the load is
cold again. Watch the cache folder's entries get rewritten at the moment of the slow first use.

**Fix.**
- Load in the background as soon as the model is on disk: at launch, after the download finishes, when the user picks
  another model — at utility priority, not on the first action. Keep it loaded (warm residency is small: weights are
  memory-mapped); unload on memory pressure if that matters.
- Make the load single-flight: an actor is reentrant, so every caller that arrives while `load()` awaits starts its own
  load unless the actor stores the running `Task` and makes later callers await it (reset it on failure so a retry runs).
- When the user still has to wait, show a distinct state ("loading the model, usually up to 30 s"), not the generic
  "processing"; downloading (with progress) and loading are different states.

**Trap.** A harness or unit test that loads the same model twice in one build sees only the warm number; measure cold
with a fresh binary name (new cache folder) or a re-signed binary.

## 17. Whole audio files in memory for a speech model

**Why.** Convenience entry points of speech libraries (`transcribe(audioPath:)` in WhisperKit and similar) read the whole
file into one `[Float]` and then chunk it into windows by copying slices — every chunk lives until the batch ends. An hour
of 16 kHz mono is 230 MB per copy; measured on a 70-minute file: peak RSS 1276 MB (124 MB after the model load), a
pass-through test showed +1080 MB over the start vs +313 MB for 10 minutes — memory grows with the recording, and long
meetings or lectures push the app into swap or a jetsam kill.

**Confirm.** Peak `phys_footprint` growth for a 10-minute and a 70-minute file after a warm-up run; growth that scales
with length is the file in memory. Measure in a separate process (Swift Testing exit test, a CLI harness): parallel
tests that load other models in the same process add hundreds of MB of noise.

**Fix.** Keep the library's own windowing rule, but feed it windows read from disk: compute window bounds with the
library's chunker logic (for WhisperKit `VADAudioChunker`: at most 30 s, cut in the middle of the longest
`EnergyVAD` silence in the window's second half, drop a final tail ≤ 1 s), read each window with a seekable PCM reader,
and send batches of `concurrentWorkerCount` windows to the array API (`transcribeWithResults(audioArrays:)`) — the same
batches and parallelism the library used internally, so speed stays the same. Shift word times by the window start.
Measured: 70 minutes 1276 → 486 MB peak RSS, 258 → 255 s; the remaining ~360 MB is the working memory of 16 parallel
decoders and does not depend on length. A unit test without the model can assert that your window bounds equal the
library chunker's on synthetic audio (tone bursts with and without pauses, shorter than one window, a short tail).

**Trap.** Match the old input scale exactly: AVFoundation converts Int16 to Float by / 32768, a hand-written WAV reader
often divides by 32767. The 0.003 % amplitude difference changed 0.65 % of words on a 41-minute multilingual corpus
(deterministic decoding, different but not better); dividing by 32768 made the text identical. Multiplying an already
scaled sample by 32767/32768 is not enough for long files — double rounding still flipped a few windows. Cutting at fixed
30 s instead of in a pause costs ~3 WER points; long files can differ between two runs of the unchanged library, so
compare against a repeat of the old code, not against zero.
