# Measuring with real input

## Contents
- Build
- Recording the user's scroll
- Reading a trace
- Offscreen harness (no screen needed)
- Reference app
- Blind A/B protocol
- Event-rate check
- Synthetic runs (regressions only)
- Etiquette: the user's screen

## Build

Release (`-O`, whole-module, the target arch). If demo data lives behind a Debug flag, keep the flag but optimize:
`xcodebuild ... -configuration Release SWIFT_ACTIVE_COMPILATION_CONDITIONS=DEBUG ENABLE_HARDENED_RUNTIME=NO
CODE_SIGN_INJECT_BASE_ENTITLEMENTS=YES` — the last two let `xctrace` attach (`get-task-allow`). Never ship this build.
Copy each experiment's `.app` aside (`ditto`) so A and B both exist during a blind pair.

## Recording the user's scroll

`scripts/record_manual.sh LABEL /path/App.app/Contents/MacOS/App [app args…]`
- launches the app (env `LEAD`, default 7 s, to open the right state via launch arguments or a deep link),
- brings it to front, shows a countdown panel (`cue`) "scroll in N s", records `DURATION` (default 20) seconds with
  Hitches + Time Profiler attached to the pid, shows "done", quits the app,
- runs `analyze_trace.py` on the result. Traces go to `$TRACES` (default `./perf-traces`).

Attach to a running app instead: `PID=1234 scripts/record_manual.sh LABEL`.

Scenarios worth separate recordings: content scroll with the cursor over content; same with the cursor parked on the
scroll bar (isolates hit-testing/hover); hover sweep without scroll; screen open; window resize; window drag; typing.

## Reading a trace

`scripts/analyze_trace.py TRACE [--process NAME] [--series]`

```
[label] fps=96 p50=8.3ms p95=16.7ms max=166.7ms >8.3ms=16% >16.7ms=2% hitches=21 hitch=9ms/s
  moving: 120Hz 88% 60Hz 10% (Safari ~95% / 4%)
  main thread 9052 ms: hover hit-test 1114, text redraw 2, view bodies 75, SwiftUI render 5074, ...
  app: Top symbols of your binary (inclusive samples) ...
```
- `fps` — app updates per second of activity (gaps > 250 ms ignored).
- `>8.3ms` — share of frame intervals longer than one 120 Hz vsync; `>16.7ms` — longer than two.
- `hitch ms/s` — Apple's hitch time per second; good < 5, visible > 10. It misses steady 60 Hz.
- `moving` — from display renders (`hitches-renders`), gaps > 60 ms dropped: what the eye sees while things move.
- `main thread` — 1 ms Time Profiler samples on the main thread, split by signature (edit `SIGNATURES` in the
  script for your app); `app` — your binary's hottest symbols. Buckets can nest: when a list sits in a `ScrollView`,
  the hover search runs *inside* the SwiftUI render (through the platform `NSScrollView`), so `hover hit-test` is part
  of `SwiftUI render`, not in addition to it. Confirm with `trace_callers.py callers` before adding buckets up.
- `longest frames` — the five longest app-frame intervals with the main-thread ms spent inside each. In a recording
  of clicking between filters the "worst frame 212 ms" held 16 ms of work: the app simply had nothing to draw between
  two clicks, and the 16 ms were one `mouseMoved` hit test. Only a frame that is mostly busy is a hang; `max` alone
  misleads whenever the user pauses.
- `--series` — per half second: display renders, app updates, main-thread ms. Use it when lag comes and goes.

Attribution: `scripts/trace_callers.py callers TRACE 'regex' [depth]` prints the call chains above the deepest match
(who triggers it); `inside TRACE 'regex'` prints what the matched frames spend time on (self and inclusive).

## Offscreen harness (no screen needed)

For "a state change on this screen feels slow" (switching a filter tab, applying a search) the cost can be measured
without the user's screen and without UI tests: a hosted unit test (the app is the test host) builds the screen in an
`NSHostingView` inside an `NSWindow` that is created but never ordered front, drives the state change the same way the
control does (expose the state to tests as a stored `Binding<State?>` property defaulting to `.constant(nil)`, the
screen falls back to its own `@State` on `nil`; the click handler only sets it), and pumps the main run loop. Rules
learned the hard way:
- **Never `Binding?` for that hook.** SwiftUI refreshes a stored `Binding` (like `@Binding`) before `body` and subscribes
  the view to its source; an `Optional<Binding>` is invisible to it. With `var tab: Binding<Tab>?` the screen's `body` was
  never re-evaluated after the test changed the tab (0 body calls), only the child control holding `@Binding` repainted:
  a whole round of numbers measured a tab-highlight animation over rows that never changed, and "the second instance of
  the screen does not draw a row" was just a tree frozen on the tab its binding was created with.
- **Prove the harness changes what you measure** before reading any number: count `body` calls once with a probe, or
  assert that the raster after the change equals the raster of the same screen built directly in the target state
  (keep that assertion as a test — it fails the moment the hook stops working).
- Pump with a *positive* timeout (`RunLoop.main.run(mode: .default, before: Date(timeIntervalSinceNow: 0.002))`): with
  a zero timeout CoreFoundation skips the "before waiting" observers, and that is where SwiftUI and CA commit.
- **Busy is CPU, not `needsLayout`.** SwiftUI often applies an update inside the run-loop observer and leaves no
  `needsLayout` behind, so a rebuild can look like "0 ms, nothing happened". Read the main thread's CPU time around
  each pump (`clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID)`): a turn with > 0.5 ms of CPU is busy; quiet is two
  idle turns. Report "work until quiet" as CPU time — the 2 ms waits of idle turns are not work.
- **Snapshots after a calm period.** Text reveals, pin drops and animated scrolls finish at different moments in a
  fast and a slow build; pump ~2 s before writing the PNG, or the diff shows animation frames instead of differences.
- **Deferred work has no frames offscreen.** A view that finishes work per display-link frame never does it in a
  window that is not on screen; trigger completion explicitly (scroll the clip view 1 pt and back) and time that.
- **A/B as two working copies.** Keep the baseline in its own checkout with its own derived data, apply each kept
  change to it after the comparison, and run A and B back to back: no rebuild between the two runs, and the next
  experiment compares against the new baseline. Other builds on the machine move medians by 10–20 %; read
  differences smaller than that only if they repeat across runs.
- Measure two numbers: the first pass that had `needsLayout` after the change (the synchronous graph update + layout —
  what the eye waits for), and the time to quiet (two passes without layout). The second includes every running
  animation: a 0.2 s implicit animation on a tab's background keeps the hosting view laying out for 0.2 s, so "time to
  quiet" says nothing about the switch itself.
- **A cheaper first pass is not a win until you know what it skipped.** Keep three DEBUG counters on the row (`body`
  evaluations, `onAppear`, `onDisappear`), read them per pass, and print the second pass and the pass in which the first
  row body ran. One variant's first pass fell 27 → 19 ms with `appeared` unchanged and `bodies` 6 → 0: SwiftUI had
  returned the rows removed on the previous switch with their old graphs, because an extra state change landed in the
  same update. That saves the rebuild only when the harness walks between the same two states; a tab the user opens for
  the first time still builds its rows. Attribute a first-pass drop by signatures (next bullet) before believing it.
- **Split a trace by pass.** Wrap every pump in an `os_signpost` interval (`OSSignposter.beginInterval("pass")`,
  `endInterval` with the pass ordinal as the message: 1 = first pass with layout), record with
  `xctrace record --instrument 'Time Profiler' --instrument os_signpost`, and bucket main-thread samples by the interval
  they fall in (`scripts/signpost_split.py`: the `os-signpost` table exports as Begin/End *events* with `event-time`,
  `signpost-name`, `subsystem` and the formatted message in `os-log-metadata`; cache the exports next to the trace — a
  two-minute export per table otherwise). A 25 ms first pass is 25 samples; summed over 120 switches it is a real
  profile, while in the whole trace it drowns under the 0.25 s animation that follows it.
- **Search beside the rows too.** One `hitTest` at a point inside the scroll content but outside every row gives the cost
  of the tree without the rows; the difference to a search on a row is the most any per-row fix (inert content, AppKit
  partition) can save. On a list of ~15 rows it was 0.3 of 0.6 ms — the rest was the hosting view's own setup and the
  descent through the platform `NSScrollView`, which no row change touches (§1 of `root-causes.md`).
- The accessibility tree is not built for a window that is not on screen (`accessibilityChildren()` is empty), so
  in-process `accessibilityPerformPress` cannot drive controls there; drive the binding instead.
- A synthetic `mouseMoved` sent with `window.sendEvent` does not reach SwiftUI's hover search in such a window
  (measured 0.0–0.1 ms). `hostingView.hitTest(point)` does: it enters `PlatformHitTestingManager.hitTest` and walks
  the same responders as the on-screen hover update. Call it once after every pass that had `needsLayout` and sum the
  time — that is the per-frame hover cost SwiftUI pays on screen during an animation that moves responders (§1 of
  `root-causes.md`); call it once at rest for the cost of a single search. Offscreen the walk is cheaper than on
  screen (0.8 ms against 2–3 ms per frame and 10–18 ms per `mouseMoved` event in the same app: smaller window, no
  sidebar, one search instead of up to three), so compare A against B, not against the recording.
- **Pin the scroller style** in every harness launch (`-AppleShowScrollBars WhenScrolling` as a launch argument; for a
  hosted unit test — the scheme's test-action arguments). With the system default "automatic", a connected mouse
  switches to legacy scrollers, which take 17 pt from the content of every `ScrollView` (probe: 299 vs 316 pt): text
  wraps differently and stacks change height, so snapshots of one build differ between runs only because someone
  plugged in a mouse receiver. Don't change the product's look for it — legacy scrollers with a mouse are native.
- Write a PNG of `cacheDisplay`'s bitmap for each state (`bitmapImageRepForCachingDisplay` →
  `representation(using: .png)`) and diff A against B with `react-to-swift/scripts/pixdiff.py`: a "pixels unchanged"
  check without a window on the screen. It compares the two builds' SwiftUI trees under the same software renderer,
  not against the on-screen compositor.
- Several screens in one process are fine once each starts from the same state: six trees built one after another
  (previous windows closed with `contentView = nil; close()` or left open) gave byte-equal rasters and the same pass
  counts. A shared state object carried over from the previous tree is the trap — the next tree starts elsewhere. Still
  prefer A and B as two builds of the same harness, and read the numbers across three runs in different positions
  before believing a 20 % difference.
- `cacheDisplay(in:to:)` draws the page in software and spends most of its time in `CGContextEndTransparencyLayer`
  for every `compositingGroup()`; it is a rough upper bound for text drawing, not what CA does on screen. Use
  `CABackingStoreUpdate_` samples from a Time Profiler attached to the test host for the real redraw cost.
- Build the test host as Release with testability (`-configuration Release ENABLE_TESTABILITY=YES` plus the demo-data
  flag); attach `xctrace` by finding the host pid by executable path and process name — `pgrep -f` on the path alone
  matches short-lived helpers and `xctrace` then fails with "Cannot find process".
- Write the numbers to a file in the host's container (sandboxed `NSTemporaryDirectory()`) and print it from the make
  target: `xcodebuild -quiet` drops the test's stdout.

## Reference app

`scripts/record_reference.sh Safari LABEL` activates the app and records Hitches for all processes; ask the user to
scroll a long page (e.g. developer.apple.com HIG typography) the same way. Analyze with
`analyze_trace.py --pacing-only`. Safari measured ~95 % of frames at 120 Hz while moving; dips in its per-second
series are pauses, not lag.

## Blind A/B protocol

1. Build A and B; copy both `.app` aside.
2. Randomize the order, write the mapping to a file, tell the user only "recording 1" and "recording 2".
3. Record each 20 s with the same scenario and cursor placement.
4. Ask which felt smoother, then reveal and compare numbers. Agreement between the user and `moving`/hitches means
   the metric tracks perception; disagreement means a scenario is missing — record that scenario next.

## Event-rate check

When the main thread is idle during lag, log scroll events for one recording (behind an environment variable):

```swift
if ProcessInfo.processInfo.environment["APP_SCROLL_LOG"] == "1" {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("scroll.log")
    FileManager.default.createFile(atPath: url.path, contents: nil)
    let log = try? FileHandle(forWritingTo: url)
    NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { e in
        log?.write(Data("\(e.timestamp) \(e.phase.rawValue) \(e.momentumPhase.rawValue) \(e.scrollingDeltaY)\n".utf8))
        return e
    }
}
```
Sandboxed apps write to the container's tmp (`~/Library/Containers/<bundle id>/Data/tmp`). Expect ~8.3 ms between
events in both finger and momentum phases on a trackpad. Correlate speed per bin with frames per bin; remove the
logger after.

## Synthetic runs (regressions only)

Posting wheel events with `CGEvent` gives repeatable numbers for regressions, but the cursor does not move and the
hit-testing path under it is skipped: a fix decided on synthetic numbers was wrong once (rejected native paragraphs
at −13 % on resize while the real cost was hit-testing under the cursor). Decide with real input.

## Etiquette: the user's screen

- Recordings and app snapshots use the user's screen: announce ("taking the screen for ~2 min"), wait for "ready".
- Signal start/end with the countdown panel and say the same in chat; macOS notifications from scripts are often
  silenced (terminal notifications off) and sound is unwelcome.
- Do not run UI test suites to find causes; they hijack mouse and keyboard for many minutes.
- Window snapshots (`screencapture -x -o -l <windowid>`) briefly show the app; close it right after.
