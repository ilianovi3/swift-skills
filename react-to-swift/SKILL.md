---
name: react-to-swift
description: Port React / Next.js / JSX / TSX / Tailwind / CSS components and screens to native SwiftUI (with AppKit or UIKit where it pays off) so they match the web reference pixel for pixel while being built the native way, fast from day one. Use it whenever the user wants to rewrite, translate, convert, mirror or "make 1:1" a web component, a web prototype or design reference in Swift, asks why a ported screen is off by a pixel (borders, line height, fonts, spacing, colors, shadows), or why a ported screen feels slower than the web page — even if they only paste a .tsx file or a Tailwind class list and say "make this in SwiftUI".
---

# React to Swift

Two contracts, never mixed up:
- **Look = the web reference, 1:1, measured.** Sizes, spacing, type, colors, states and motion come from the
  reference's computed values, and every screen is checked with a pixel diff, not by eye.
- **Mechanics = native.** Port the rendered result, not the DOM. A web page is cheap to build from a div per word
  and a hover on every element; a SwiftUI tree shaped like that pays for it on every frame. Choose the native
  structure first, then reproduce the pixels on top of it.

Companion skills: `optimize-swift` (measuring and fixing performance with real input), `swiftui-pro`,
`swiftui-layout-components`, `swiftui-uikit-interop`, `ios-accessibility`, `ios-localization`.

## Workflow

### 1. Read the source completely
The component file, every class it uses, the design tokens (`globals.css`, Tailwind config), fonts, icons, the data
it renders, and every state: hover, focus, pressed, disabled, empty, loading, error, long text, RTL/locales, dark
theme, reduced motion. Note animations (CSS transitions, GSAP, Framer Motion) with durations, easings, staggers.

### 2. Get computed values, not guesses
Tailwind classes hide `clamp()`, `vw`, `em`, `cqw` and inheritance. Open the reference in a headless browser at the
reference width (Playwright or a headless DevTools MCP — never a visible window on the user's screen) and read
`getComputedStyle` and `getBoundingClientRect` for the elements you port. Write the numbers down; they are the spec.

### 3. Choose the native structure (before any styling)
| Web shape | Native structure |
| --- | --- |
| Long list of uniform rows | `LazyVStack`/`List` with cheap rows; `NSTableView`/`UICollectionView` for thousands |
| Long document of heterogeneous, expensive blocks (macOS) | Build all blocks; host each row in its own `NSHostingView` inside an AppKit stack (see `optimize-swift`, pattern HostedStack) |
| Paragraph with inline chips/mentions/tags | One `Text`; chips drawn from `Text.LayoutKey` rects (`optimize-swift`, InlineDecorations) — never a view per word |
| Word-by-word reveal | `TextRenderer` with per-run opacity, not word views |
| Hover highlight shared across items | Per-item observable flags; hover only where it adds meaning |
| `contentEditable`, `<textarea>` | `TextField(axis: .vertical)` or `NSTextView`/`UITextView` |
| `<select>`, dropdown menus | `Menu`/`Picker`/`NSPopUpButton` styled to match |
| Popover, dialog, toast | `popover`/`NSPopover`, `sheet`/alert, overlay with transition |
| `title=` tooltip | `.help()` — but each one is a hit-test target; skip on dense repeated items |
| Images | ImageIO thumbnails at display size + cache, not `AsyncImage` in lists |
| `position: sticky` | `safeAreaInset` / pinned section headers |
| Custom title bar region (macOS) | `window.isMovable = false` + `WindowDragGesture` on your bars |

Native chrome may differ (window, system dialogs, scroll bars, popover arrows); list each difference explicitly.

### 4. Build the kit first
Port tokens (colors, type scale, radii, shadows, spacing) and primitives (border, rule, bar, row, button, chip,
avatar, field) before screens. Nearly every "the screen looks off" bug in practice was a kit bug repeated on every
screen — fixing it once in the kit fixes all screens.

### 5. Translate styles
Use `references/css-to-swiftui.md` (box model, flex/grid, borders, shadows, colors, units, motion) and
`references/typography.md` (fonts, variable axes, CSS line height, tracking, smoothing, wrapping). The most common
pixel errors, in order of frequency:
1. CSS borders sit inside the border box: use `strokeBorder`, not `stroke`, and add the border to padding math.
2. `border-t/b` occupies its own pixel row: the rule adds height, it is not drawn over padding.
3. `line-height` is CSS half-leading: glyphs centered in `size × leading`; SwiftUI puts extra space below.
4. `Font.custom(_:size:)` follows a text style and adds its tracking: use `fixedSize`.
5. Group opacity (`opacity-40` on a button) needs `compositingGroup()`, otherwise layers fade separately.
6. Box shadows with negative spread are not `shadow(radius:)`: blur a shrunk shape instead.
7. `last:border-b-0`, `gap`, `minmax(0,1fr)_auto` columns: container logic, not per-child guesses.

### 6. Verify pixels
`references/parity-check.md`: screenshot the reference headlessly and the app window without stealing focus
(`scripts/window_shot.sh`), diff with `scripts/pixdiff.py`, measure offsets by ink rows/columns, fix, repeat.
Cover both themes and the largest text scale on representative states — a handful of screens per component, not
every combination.

### 7. Hand over
Report a table "element — reference value — before → after", the native differences you kept on purpose, and the
structure choices with their reason. If the screen is long or interactive, run the measurements of
`optimize-swift` before calling it done.

## Rules that save days
- Strings verbatim from the reference (localization keys = source strings); no copy edits while porting.
- No new UI invented in Swift: if a state or element is missing in the reference, design it there first.
- Never keep mock data in the product path; put demo content behind a Debug-only switch.
- Give screens deep links or launch arguments that open any state directly — snapshots and recordings depend on it.
- A prototype mutates state client-side (re-typing a record by overlaying it, "server" edits applied locally); the product often has a server operation for that. Port the *resulting screen state* (e.g. "processing again"), call the server, and drop the prototype-only branch ("chosen manually…") — mark it `native:`. A client-side overlay that mimics the server never clears itself and ends up fighting real server data.
- A sentence in the reference about an element the native build hides (a button gated by an entitlement) goes with that element: split the localization key at the sentence boundary (source text unchanged) and append `Text(verbatim: " ") + Text(second)` only when the element shows — markdown links in each part keep working; mark it `native:`.
- A local cache with an outbox belongs to one account: store the auth user id with it and check it synchronously at the moment the session becomes "signed in", before any request runs; another id — wipe like sign-out, same id — keep and send. Otherwise a lost session (401) followed by another sign-in ships the old account's queue under the new token. Sign-in during a live recording of the old account is refused, not wiped.
- Optimistic edits: keep the overlay = "not yet confirmed". Queue only the fields that changed, and on the server reply clear exactly those fields whose value is still the one you sent — an edit typed while the request was in flight survives, and other people's changes show up. A full-snapshot overlay that is never cleared silently overwrites everyone else.
- Failure states need two different UIs the prototype usually lacks: "no network / server down" (wait and retry with backoff, no action needed) and "the server refused" (4xx: show the reason in plain words, roll the edit back, offer Retry). Design both in the reference first; the second one is the one people never draw.
- The reference's demo query (`?app=offline`, `?state=failed`) maps to real signals natively (reachability, outbox rows, HTTP status) — never to a parameter.
- A TS edit field with three states (`place?: string | null` — untouched / cleared / set) is `String??` in Swift, and synthesized `Codable` collapses it: `decodeIfPresent` reads `null` as "absent", so a cleared field comes back from the queue as "untouched". Keep it with a small `@propertyWrapper` holding `T??` plus `KeyedDecodingContainer`/`KeyedEncodingContainer` overloads (`contains` + `decodeNil` on read, `encodeNil` on write). On the wire a generated OpenAPI client (`encodeIfPresent`) never sends `null` either — inject the null keys in a client middleware from a task-local set until the generator supports explicit null.
- Undo in a prototype just restores the previous overlay; the server must hear the reset too. Diff the overlay against the server base: a key dropped from the overlay sends the base value (or `null` for a cleared optional), a dropped dictionary entry sends its reset form (`done: {id: false}`, `speakers: {key: {reset: true}}`). Also check which dictionaries the server replaces whole (`fields`): send the base merged with the overlay, confirm with the overlay part only.
