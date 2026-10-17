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
- The same rule for a list the prototype keeps whole (`edits.docs = [...]`): natively the overlay holds only entries that differ from the server list — new, edited, a local unsent draft (flag it), deleted ones as tombstones — computed as a diff against the server list on every save; the screen list is server list + overlay merged by server id *or* key (the server may assign its own key to a new item, so match by id too). The server's reply to each operation goes into the server list, and the overlay entry is dropped when its operation's fields are still what was sent and no other operation for it is queued. A full local copy saved on the first edit hides every item and change other people make afterwards.
- A whole-document edit (a hand-edited snapshot) carries the version the edit *started* from, and your own confirmed operations on the same item rebase the queued ones. On 409 fetch the server copy: the same text — already there; no hand-edited text there (only metadata moved) — resend on the new version; otherwise show the server text and offer "keep mine" (put yours back on top of the winning version), never a silent overwrite.
- A field-level edit batch (several fields of one record) needs field-level conflicts, not a version gate: the server stamps who changed which field path and when, applies a batch on an older base unless one of *its* fields was changed by someone else since (then 409 with the paths), and the client drops exactly those fields from its queue rows and overlay, shows the server copy and offers "keep mine". A whole-record "stale → resend everything on the new version" makes the edit always win and the conflict toast never fires. On a version mismatch keep the queued rows in place with the new base instead of collapsing them into one snapshot row — the rows carry the resets (undo) that a snapshot cannot express. Resets that the overlay's value types cannot hold (`[String: String]` → `null`, `[String]` of flags → `false`) travel in a separate delta-only set (`unset`) mapped to `null`/`false` when the request body is built.
- Failure states need two different UIs the prototype usually lacks: "no network / server down" (wait and retry with backoff, no action needed) and "the server refused" (4xx: show the reason in plain words, roll the edit back, offer Retry). Design both in the reference first; the second one is the one people never draw.
- The reference's demo query (`?app=offline`, `?state=failed`) maps to real signals natively (reachability, outbox rows, HTTP status) — never to a parameter.
- A version string used for optimistic concurrency (`updated_at` echoed back as `base_updated_at`) must survive parse → `Date` → print unchanged. `Date.ISO8601FormatStyle(includingFractionalSeconds:)` truncates, and a `Date` holds `…56.360` as `…56.3599999`, so about half of millisecond versions come back one millisecond lower and the server answers "stale" on every retry. Either keep the string verbatim on the wire, or print with a nudge bigger than the `Double` error and smaller than the server's sub-millisecond step (`addingTimeInterval(2.5e-7)` for 2020s dates), and test all 1000 millisecond values.
- A TS edit field with three states (`place?: string | null` — untouched / cleared / set) is `String??` in Swift, and synthesized `Codable` collapses it: `decodeIfPresent` reads `null` as "absent", so a cleared field comes back from the queue as "untouched". Keep it with a small `@propertyWrapper` holding `T??` plus `KeyedDecodingContainer`/`KeyedEncodingContainer` overloads (`contains` + `decodeNil` on read, `encodeNil` on write). On the wire a generated OpenAPI client (`encodeIfPresent`) never sends `null` either — inject the null keys in a client middleware from a task-local set until the generator supports explicit null.
- Undo in a prototype just restores the previous overlay; the server must hear the reset too. Diff the overlay against the server base: a key dropped from the overlay sends the base value (or `null` for a cleared optional), a dropped dictionary entry sends its reset form (`done: {id: false}`, `speakers: {key: {reset: true}}`). Also check which dictionaries the server replaces whole (`fields`): send the base merged with the overlay, confirm with the overlay part only.
- A prototype "upload" that only keeps a blob URL (or a timer bar) ports to the real transfer: create the record → presigned PUT straight to the bucket → confirm. Progress comes from a task-level `URLSessionTaskDelegate` (`session.upload(for:from:delegate:)`, `didSendBodyData`), hopped to the main actor per tick. In the sandbox, copy the picked file into the container *before* any `await` (security-scoped access ends with the picker) and treat that copy as the retry queue: a top-level copy = not uploaded yet, so it survives relaunch and resumes on reconnect; move it into a per-id cache after confirmation and reuse it for Quick Look and Save. If the server dedups by content hash and counts unconfirmed records, an interrupted attempt blocks its own retry and eats a slot of the limit: fix it on the server (an unconfirmed twin of the same owner and hash is taken over with a fresh upload link, the limit counts confirmed files and is re-checked at confirm) rather than having every client delete its stale record first; return the refusal reason (duplicate with the existing id, limit) in the 409 body and map it to the row text, never guess it from local counts. A chat attachment is the same flow with the thread as owner: a duplicate in the thread is the existing file — attach that id; a draft thread becomes a server thread once, with concurrent uploads awaiting the same creation task; the message carries file ids and the reply lists files with links, opened natively with `quickLookPreview` from the local cache. Text the server needs from the file (pages for a model) is extracted on device off the main actor (`@concurrent`): PDFKit per page, `NSAttributedString` for DOCX/RTF, plain text as is.
- A prototype that fakes a server reply (an answer revealed word by word after a timer) ports to the real mechanism, not the timer: stream the reply (SSE through the generated OpenAPI client — `text/event-stream` comes as `HTTPBody`, `asDecodedServerSentEvents()`), show the "searching" state until the first piece, let the text grow and keep the list's end in view; the final event carries the saved record that replaces the streamed draft. If the server uses structured output, stream the raw JSON and extract the text field from the partial JSON on the server (`pydantic_core.from_json(allow_partial="trailing-strings")` is monotonic), holding back an unclosed markup token (`@{…`, `[[…`) so it never flashes. Mark the difference `native:`.
- A prototype's in-memory chat (all messages at once) becomes pages natively: the list of threads without messages, the open thread's newest page, older pages when the top marker scrolls into view (`onScrollVisibilityChange`, then `scrollTo(previousFirst, anchor: .top)` keeps the position), new messages of others by polling `after=<cursor>`. Order and dedupe by server id (time-ordered ids such as uuidv7), unsaved local rows stay last. The polling cursor is the newest id that came *from a page or poll*, never your own just-saved row: another writer's row saved during your long request got a smaller id and would be skipped forever.
