# Parity check: measure, don't eyeball

## Contents
- What to compare
- Reference screenshot (headless)
- App screenshot without stealing focus
- Diff and measure
- Report

## What to compare
Representative states per component — default, hover, empty, long content, error — in light and dark and at the
largest text scale. A handful of screenshots per screen, not every combination: a full matrix (screens × themes ×
sizes) takes hours and finds nothing a kit-level check doesn't. Automate the rest as a smoke pass (screen opens,
no empty blocks where data exists).

## Reference screenshot (headless)
Never open a visible browser window on the user's screen.
```sh
npx playwright screenshot --viewport-size "1280, 800" --full-page http://localhost:3000/screen ref.png
```
For numbers, evaluate in a headless page (Playwright or a headless DevTools MCP):
```js
const el = document.querySelector('[data-x]'); const r = el.getBoundingClientRect();
({ x: r.x, y: r.y, w: r.width, h: r.height, ...Object.fromEntries(
   ['font-size','line-height','letter-spacing','padding','border','color'].map(p => [p, getComputedStyle(el)[p]])) })
```
Use device scale factor 2 to compare with a Retina window at the same pixel scale.

A fresh headless profile has empty `localStorage`: an onboarding gate will redirect every screen to `/welcome` and the
screenshot shows the wrong page without an error. Seed the persisted state before navigation
(`page.add_init_script("localStorage.setItem('<key>', JSON.stringify({onboarded: true}))")`) and assert a text the
target state must contain, not just that a PNG was written.

Turbopack (Next 16) refuses a symlinked `node_modules` ("points out of the filesystem root"): in a git worktree run
`npm ci` there instead of linking the main checkout.

## App screenshot without stealing focus
`scripts/window_shot.sh OUT.png APP_BINARY [args…]` launches the app with arguments that open the state (deep link,
launch argument, fixture), waits `LEAD` seconds, captures only its largest window (`screencapture -x -o -l <id>`,
window id from `CGWindowListCopyWindowInfo`), quits the app. The window appears for a few seconds; tell the user.
Give the app launch arguments for every state you need (open screen X scrolled to y, theme, text size, demo data).
Pin overlay scrollers too (`-AppleShowScrollBars WhenScrolling`): headless Chrome hides scroll bars, while a Mac with a
mouse connected gives every `ScrollView` legacy scrollers that take 17 pt of its width — lines wrap differently from
the reference and between your own runs.

When no window may appear at all (the screen is in use), render the screen in a unit test: an `NSHostingView` as the
content of an `NSWindow` that is never ordered in, the run loop spun for about a second, then `cacheDisplay(in:to:)`
into a PNG; text scale = the root view's scale environment with the host frame multiplied by it (like the reference's
root `zoom`). Gate such a suite on an environment flag so ordinary test runs skip it. `cacheDisplay` draws views, not
the composited layer tree: layer filters (`.blur`, blurred shadows, backdrop effects) are missing. For those, render
the window's layer tree with `CARenderer(mtlTexture:options:)` into a `.managed` `bgra8Unorm` texture after
`window.display()` — scale with the root layer's transform (anchor point zero), flip rows when saving (layer origin is
bottom-left). A renderer keeps the tree it was attached to: after a state change attach a new one. Do not plan geometric assertions
through the accessibility tree there: the hosting view of a window that was never shown returns no accessibility
children, so "is the button in the first screen" stays a check of the reference script plus the image pair.
A view rendered at its own height (a dialog, a card) needs a measured frame: with `sizingOptions = []` the host's
`fittingSize` is zero and `bitmapImageRepForCachingDisplay` returns `nil` (no file, no error), so size it with
`NSHostingController(rootView:).sizeThatFits(in: NSSize(width: w, height: big))`. A sheet's chrome with a
`ScrollView` body measures to the header only unless the root has `.fixedSize(horizontal: false, vertical: true)` —
in the real sheet the system does that sizing. A sheet itself never opens in a window that was not shown: render its
chrome as a plain view (the modifier's content extracted into a public view) for the pair.
A SwiftUI `.alert` on macOS is an `NSAlert` sheet, so it cannot be presented there either (and presenting a sheet on a
hidden window may bring the window on screen): build an `NSAlert` with the same strings and buttons in the same order,
`layout()` it, set `window.appearance` and cache `window.contentView` inside `appearance.performAsCurrentDrawingAppearance`.
Its background is an `NSVisualEffectView` that the cache leaves transparent (dark-theme text then shows white on
white): composite the cache over `NSColor.windowBackgroundColor` resolved in the same appearance, and draw it with
`draw(in:from:operation: .sourceOver, …)` — plain `NSImageRep.draw(in:)` copies the transparent pixels over the fill.
The default button stays grey (the window is never key), and the alert ignores the app's text scale — no XL pair.

## Diff and measure
`scripts/pixdiff.py A.png B.png [--crop x0,y0,x1,y1] [--out side.png] [--ink x0,y0,x1,y1:threshold]`
- prints the bounding box and count of differing pixels (threshold 24 per channel);
- `--out` writes A over B (or side by side) plus an amplified difference strip for viewing;
- `--ink` prints the first/last rows and columns with ink darker than the threshold inside a box — the fastest way
  to read "the capsule is 2 px lower" or "text starts 3 px later" from two screenshots.
Typical loop: crop the element in both images, compare ink rows/columns, change one value, rebuild, re-measure.
Differences spread across a whole line that grow toward its end are word positioning (see typography), not layout.

## Report
| Element | Reference | App before → after | Where |
Keep one table per screen in the project docs; list native differences kept on purpose separately.
