---
name: optimize-swift
description: Find and fix performance problems in a Swift client app (SwiftUI, AppKit, UIKit; macOS and iOS) — janky or "not smooth" scrolling, lag that switches on and off, slow hover, slow screen opening, stuttering window resize, high CPU, 60 Hz instead of 120 Hz, "feels worse than Safari/native apps". Use it whenever the user says an app, screen, list or component is slow, laggy, choppy, stuttering, drops frames, or asks to optimize, speed up, profile or "make it native-smooth" — even if they never mention Instruments or traces. Covers real-input measurement, a catalogue of root causes with their trace signatures, and native fixes that keep the look unchanged.
---

# Optimize Swift

The goal is a client that feels like a first-party native app, proven by numbers from real input — not a list of
plausible tweaks. Most "SwiftUI is slow" cases are structural: the view tree is shaped like a web page (one huge
non-lazy screen, a view per word, hover everywhere) and the framework pays for that shape on every frame. Fix the
shape, measure the result, keep the look identical.

Companion skills: `swiftui-performance` (Instruments lanes, identity, lazy containers), `swift-performance-optimization`
(general Swift/memory), `swiftui-uikit-interop` (representables). This skill adds what those don't: measuring with the
user's real input, a catalogue of root causes found in production traces, and the fixes that removed them.

## Principles

1. **Release only.** Debug SwiftUI is several times slower and lies about where time goes. Build `-O` (a perf build
   may keep a Debug flag for demo data, but must be optimized). Say so whenever you hand the user a build to try.
2. **Real input decides.** Synthetic scroll (posting `CGEvent` wheel events) does not move the cursor and skips the
   hit-testing path under it — exactly where many lags live. Use synthetic runs only for regression checks; decide
   with recordings of the user's own scroll (`scripts/record_manual.sh`).
3. **The right metric.** "Hitches ms/s" misses steady 60 Hz on a 120 Hz display. Primary metric: share of frames at
   full refresh while the content moves (`moving: 120Hz N%` from `scripts/analyze_trace.py`). Reference: Safari on a
   long page scores about 95 % / 4 % on the same Mac — record it (`scripts/record_reference.sh`) before blaming macOS.
4. **Roots, not symptoms.** If the trace points at structure (window, list, data flow), change the structure. A
   patch is acceptable only as a marked temporary step with the real fix named.
5. **One change per experiment, blind A/B.** Build variant B with exactly one change, record A and B in random order
   without telling the user which is which, compare numbers and the user's impression. Keep every rejected experiment
   with its numbers in the project's perf doc — they stop the next person from repeating it.
6. **Don't take the user's screen by surprise.** Recordings need the screen; announce them, run them only when the
   user says "ready", and show a countdown (`scripts/cue.swift`, top-right panel). Never use notifications or sound
   for cues. UI tests are not a tool for finding causes.

## Workflow

### 1. Code review first (no screen needed)
Read the screen and its kit components before measuring. Check every item of the root-cause checklist below; most
hits are visible in code. Note each suspect with file and line — it becomes a hypothesis, not yet a fix.

### 2. Baseline
- Build Release and pick scenarios: scroll content with the cursor over it; the same with the cursor over the
  scroll bar (separates hover/hit-test cost from everything else); hover sweep without scroll; open the screen;
  resize and drag the window; type in a field.
- Record each scenario 20 s with the user (`record_manual.sh`), plus one reference recording of Safari.
- Analyze (`analyze_trace.py`): fps, `moving` pacing, hitches, longest frame, main-thread time split by signature,
  top app symbols.

### 3. Attribute
- For each big bucket, find who triggers it: `trace_callers.py callers <trace> '<signature>' 6`.
- Find what it spends time on inside: `trace_callers.py inside <trace> '<signature>'`.
- Offscreen harness traces: bucket samples by the harness's own `os_signpost` intervals (`signpost_split.py <trace>
  --pass 1`) — the first pass of a state change by signatures, variant against variant, instead of the whole run where
  it drowns under the animation that follows.
- Split by time when lag "comes and goes": `analyze_trace.py --series`. If lag windows show an idle main thread,
  the cost is not your CPU work — check display renders vs app updates and scroll-event rate (see
  `references/measure.md`) and compare with the reference app before touching code.

### 4. Experiment and land
- One hypothesis per build, blind pair with the user, compare `moving`, hitches, main thread and the bucket you
  targeted. Visual check after every change: window snapshot and pixel diff against the previous build
  (`react-to-swift/scripts/window_shot.sh` + `pixdiff.py` if available).
- When a fix wins: remove experiment markers, write the before/after table and rejected experiments into the
  project's perf doc and changelog, run the full headless gate (build, tests, lint), commit once.

## Root-cause checklist (details and fixes: `references/root-causes.md`)

| Symptom in code | Trace signature | Native fix |
| --- | --- | --- |
| Long non-lazy screen with many buttons/hover zones (macOS) | `PlatformHitTestingManager.hitTest`, `HoverResponder`, `ContentShapeResponder`, `StyledTextResponder` | Partition into AppKit-hosted rows (`NSHostingView` per row) so AppKit prunes by frame — only when the rows cost more than a hosting view's fixed ~0.3 ms per search (measure a search beside the rows first); fewer responders per row |
| `.windowStyle(.hiddenTitleBar)` + content under the title strip | `_resetDragMargins`, `_regionForOpaqueDescendants` | `window.isMovable = false` + `WindowDragGesture` on your own title bars |
| One `@Observable` value (hovered id, selection) read by every row | many `DynamicBody` updates per hover change | Per-item observable flags: a change touches two rows, not all |
| Paragraph built as a view per word (flow layout for inline chips) | `LayoutEngineBox.sizeThatFits`, custom `Layout.sizeThatFits`, hit-test growth | One `Text`; decorate chips from `Text.LayoutKey` rects; reveal with `TextRenderer` |
| Custom `Layout` measuring subviews on every pass | `Layout.sizeThatFits` in hot frames | Measure once in the layout cache; only wrap lines per width |
| Row text redrawn while hover background changes | `CABackingStoreUpdate_` | Give the row content its own layer (`compositingGroup()`); avoid exact line height in hot rows |
| `AsyncImage` in lists | repeated decode, flicker | ImageIO thumbnail at display size + `NSCache` |
| Lazy grid of expensive blocks | build/rasterize spikes during scroll | Laziness only when rows are cheap; otherwise build all and partition |
| Toggling `allowsHitTesting`/visibility on big subtrees during scroll | redraw bursts at scroll start/stop | A transparent cover over content while scrolling; never toggle the content |
| Floating panel resized to fractional sizes | layout loop, `setFrame` storms | Apply frame changes only beyond a 1 pt threshold |
| `MenuBarExtra` with live content | KVO rebuilds of the status item between frames | `NSStatusItem` with a menu built on open |
| Shapes/icons parsed per draw | path parsing in hot frames | Parse once, cache static paths |
| Screen rebuilt with the same data (server answered the same, a hosted row's root re-set, an env value with closures) | the same `body` work on every refresh; cost scales with the screen, not with the change | Equality the framework can see: a revision key on hosted rows, `Equatable` env values, no global "revision" bump for unchanged data (`references/root-causes.md` §15) |
| `@Observable` written with an equal value through `_modify` (nested or subscript write — a plain `set` of an `Equatable` is already skipped); two forms of one entity overwriting each other per sync; a clock inside a phase enum | every reader of the property re-renders on each write / each second | Guard at the setter all callers route through; split the fast-changing value into its own property (§15) |
| First Core ML / Neural Engine use after an install or update is slow ("processing" takes 20–80 s once) | the model's load, not its inference: cache entries in `com.apple.e5rt.e5bundlecache` rewritten at that moment | Load in the background at launch / after download, single-flight load, a distinct "loading the model" state (`references/root-causes.md` §16) |
| Per-call `LocalizedStringResource(locale:bundle:)` | ~1 ms per string in `body` | Cache the `<lang>.lproj` bundle, `String(localized:bundle:locale:)` (§11) |
| `kCTLanguageAttributeName` on TextKit 1 paragraphs (`NSLayoutManager`) | `ubrk_open` → `icu::BreakIterator::buildInstance` under `NSParagraphArbitrator` on every `ensureLayout`; lines also break unlike a browser | No language attribute on TextKit-laid text (−60 % layout time); language for speech by another route (§18) |
| Hundreds of `NSTextView`s (one per paragraph) in a window | `_postFrameChangeNotification` → `_CFXNotificationPost` → `-[NSTextView _anyViewFrameChangedWithNotification:]` on every view move | Remove that observation for display text views on joining a window; test hosts never free text views — purge before measuring (§19) |

## Output

Report to the user, in this order: what you measured (scenarios, Release build), the before/after table with the
`moving` pacing and hitches, the root cause in one sentence, what changed in code (files), experiments that did not
work and why, and what remains with the next measurable step. Keep numbers in a table; never call something "smooth"
or "fixed" without the recording that shows it.
