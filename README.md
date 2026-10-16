# Swift skills

Agent skills (Claude Code and compatible agents) for native Swift work: porting a web UI to SwiftUI pixel for pixel,
and optimizing the client until it scrolls like a first-party app. They grew out of porting a Next.js prototype to a
macOS app; every rule is backed by a measurement or a pixel comparison.

| Skill | What it does |
| --- | --- |
| [`react-to-swift`](react-to-swift/SKILL.md) | Rewrite a React / Next.js / Tailwind component or screen in SwiftUI so it matches the web 1:1 while being built the native way: structure chosen for performance, CSS translated value for value, browser-accurate typography, verification by pixel diff. |
| [`optimize-swift`](optimize-swift/SKILL.md) | Optimize a client, a screen or a component as far as it goes: measure with the user's real input, use "share of frames at 120 Hz while moving" as the metric, a catalogue of root causes with their trace signatures, and native fixes that keep the look unchanged. |

They complement, and do not repeat, general skills such as `swiftui-performance`, `swift-performance-optimization`,
`swiftui-pro` and `swiftui-uikit-interop`.

## Install

```sh
git clone https://github.com/ilianovi3/swift-skills ~/dev/swift-skills
ln -s ~/dev/swift-skills/react-to-swift ~/.claude/skills/react-to-swift
ln -s ~/dev/swift-skills/optimize-swift ~/.claude/skills/optimize-swift
```

Then run `/reload-skills` in Claude Code.

## Layout

```
react-to-swift/
  SKILL.md                     workflow and the rules that matter most
  references/css-to-swiftui.md CSS and Tailwind → SwiftUI, value for value
  references/typography.md     fonts, variable axes, CSS line height, tracking, smoothing, wrapping
  references/parity-check.md   screenshots without windows on screen, diffing and measuring offsets
  scripts/window_shot.sh       capture the app's window (+ window_id.swift)
  scripts/pixdiff.py           difference of two screenshots, ink bounds for measuring shifts
  evals/evals.json             test prompts with assertions
optimize-swift/
  SKILL.md                     principles, workflow, root-cause table
  references/root-causes.md    causes, how to confirm them, fixes, traps
  references/patterns.md       ready code patterns (HostedStack, per-item hover flags, one-Text paragraphs, …)
  references/measure.md        recording real scroll, reading traces, Safari baseline, blind A/B
  scripts/analyze_trace.py     xctrace summary: frames, 120 Hz while moving, main thread by signature
  scripts/trace_callers.py     who triggers a signature and what it spends time on
  scripts/record_manual.sh     20 s recording of the user scrolling, with an on-screen countdown
  scripts/record_reference.sh  reference recording of Safari or another system app
  scripts/cue.swift            countdown panel in the corner of the screen
  evals/evals.json             test prompts with assertions
```

## Requirements

macOS with Xcode (`xcrun xctrace`, `swiftc`), Python 3, Pillow for `pixdiff.py` (`pip install pillow`), Playwright for
reference screenshots (`npx playwright`). Recordings and window snapshots briefly take over the screen; the agent
should warn the user first.

## Evaluation

Each skill ships three test prompts. In the first run (Claude Opus, with and without the skill, assertions checked
against the answers) the skills raised the assertion pass rate from 79 % to 100 % (`optimize-swift`) and from 72 %
to 100 % (`react-to-swift`), at +12–18 % tokens. Two prompts did not discriminate (the baseline already passed) and
should be made harder.

## Contributing

A new finding about performance or web-to-native porting goes into the matching `references/*.md` with before/after
numbers and how to confirm it; rejected experiments are recorded too. Keep `SKILL.md` short (under 500 lines) and put
details in `references/`.
