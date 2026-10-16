# Measuring with real input

## Contents
- Build
- Recording the user's scroll
- Reading a trace
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
  script for your app); `app` — your binary's hottest symbols.
- `--series` — per half second: display renders, app updates, main-thread ms. Use it when lag comes and goes.

Attribution: `scripts/trace_callers.py callers TRACE 'regex' [depth]` prints the call chains above the deepest match
(who triggers it); `inside TRACE 'regex'` prints what the matched frames spend time on (self and inclusive).

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
