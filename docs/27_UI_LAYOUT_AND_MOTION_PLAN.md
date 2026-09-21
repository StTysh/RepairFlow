# 27 — UI layout and motion plan

**Status:** proposal. Nothing in here is implemented. Written 2026-09-21 after
photographing every screen in the running application and measuring the DOM.

**Method.** 24 screenshots of every distinct screen, tab, dialog and overlay,
captured at the owner's real viewport, plus live `getBoundingClientRect`
measurement. Every number marked *(measured)* is a DOM reading, not an estimate.
Two independent analyses were run over the screenshots and the source; their
claims were then re-verified here. Where they were wrong, this document says so.

**The viewport that matters.** 2552 × 1226 CSS px (a 2560-wide display at 150%
scale, `devicePixelRatio` 1.5). This is not a hypothetical wide screen; it is
the one the application is used on. Chrome's window could not be narrowed
during the audit, so behaviour below 1280px is assessed from source, not
observation — see §8.

---

## 1. The complaint, and the two mechanisms behind it

> *"overcrowded or there is not too much space for very little thing"*

Both halves are true at once, and they have two distinct causes.

### 1.1 The layout stops responding at 1280px

| Breakpoint | Usages in `frontend-fixi/src` |
|---|---|
| `xl:` (1280px) | 9 |
| `2xl:` (1536px) | **2**, both in `maintenance.index.tsx` |

Between 1280px and 2552px — the whole of the owner's screen — **no grid ever
adds a column**. Cards and table cells only stretch. A four-up grid designed at
1280px is still four-up at 2552px, with each card 1.6× fatter than intended.

### 1.2 Two different width rules, neither right

*(measured)*

| Surface | Container | Rendered width |
|---|---|---|
| Every page using `PageContainer` | `mx-auto max-w-[1510px] px-6` | **1454px** |
| **The ticket page** | `px-8 py-6` — no `mx-auto`, no `max-w` | **2334px** |

`AppShell.tsx:257-260` carries a comment claiming the utility bar "matches the
max-w-[1510px]/px-6 container the page content uses so the bar's right edge
lines up". On the ticket page it does not: *(measured)* the bar sits at left 630
width 1510, the ticket header at left 250 width 2270. **The comment is stale.**

So the application simultaneously throws away 824px of gutter on most pages and
lets its single most-used page sprawl to 2334px. That is the complaint, exactly.

### 1.3 The clearest single illustration

On the ticket page, in **one row** *(measured)*:

- the row itself is **2270px** wide
- the `<h1>` inside it is capped `max-w-2xl` and renders **557px**
- on the Timeline tab, the gap between "Case opened" and its "16d ago"
  timestamp is **2073px**

A title too narrow to breathe and a timestamp two thousand pixels from its
label, in the same container. Cramped and sprawling at once.

---

## 2. Measured inventory of the problem

*(all measured)*

| Screen | Finding |
|---|---|
| **Ticket (all 10 tabs)** | **526px of chrome before content — 43% of the viewport.** Content card itself 444px. Progress rail **2205px** for 5 steps: 441px per label, first-to-last centres **1764px** apart |
| **Agent tab** | Graph fills **43%** of its canvas. Nodes 1116×537 in a 2212×634 canvas → **548px dead on each side**. `fitView` runs correctly but is capped by `fitViewOptions={{ maxZoom: 1 }}` (`CaseFlow.tsx:304`) when it could scale ~1.97× |
| **Overview** | "Needs attention" detail lines are **1300px boxes at 11px ≈ 250 characters per line**, then clipped by `line-clamp: 1` at 194–215 chars. Roughly 3.3× the 75ch readability limit — too long *and* truncated |
| **Maintenance** | 6 KPI cards at 232×92px. The Issue column — the only thing you actually read — is the **only** hard-capped column (320px) while Address and Assigned-to wrap to two lines. Row heights vary 44–54px because wrapping is accidental |
| **Properties** | 4 cards in a 3-up grid → one orphan on row 2 beside 954px of empty grid. Photo strip is 3.7:1 |
| **Contractors** | Contractor column **661px**; ~374px of empty space between the name and "Service area" on all 18 rows. "Assigned" gets 133px for one digit |
| **Tenants** | 4 rows; content ends at 462px leaving **764px (62%) blank**. 1201px of eye travel from name to last figure |
| **Property detail** | "Quoted by year" renders **one** bar whose height is always 100% of itself — it encodes nothing. The same £1,565.00 appears three times in one row |
| **Reports** | Numeric columns left-aligned; stat tiles leave a ragged trailing empty cell |
| **Messages** | Thread pane 1017×923 showing a 432×220 placeholder, inside a bordered box inside a bordered box. 768px of empty list |
| **Sidebar** | 218×1227 with nav ending at y=432 → **~700px unused** |

---

## 3. Defects found that are not layout

These were found while photographing and are worth fixing regardless.

1. **Message thread heading shows a raw UUID.** "Case f0372992-efae-54ff-…"
   instead of "#14 — Slipped ridge tiles". Root cause is server-side:
   `GET /api/v1/messages/threads/{case_id}` returns only `{case_id, items}` —
   no `case_title`, no `case_number` — so the UI's
   `case_title ?? \`Case ${caseId}\`` always falls through. Fix in
   `app/api/messaging.py` (the list endpoint already returns both).
2. **US date format in a UK product.** The Record-an-update dialog renders
   `mm/dd/yyyy`.
3. **Status badge casing is inconsistent.** `AWAITING_CONFIRMATION` on property
   and ticket-detail surfaces vs "Awaiting confirmation" from `StatusBadge`
   elsewhere. Three call sites render `{x.status}` raw instead of using
   `StatusBadge`.
4. **Dark mode is dead code.** `styles.css:5` declares `@custom-variant dark`
   and `:148` defines a complete `.dark` token block, but **nothing ever adds
   the class, there are zero `dark:` utilities in any component**, no
   `prefers-color-scheme` hook, and `index.html` does not set it. Either wire it
   up — cheap, the tokens exist — or delete it.
5. **`recharts@^2.15.4` is a dependency with zero imports.** Every chart is
   hand-rolled CSS. Adopt it or drop it.
6. **Two failing contrast pairs** (WCAG AA, 4.5:1 for body text): the red
   escalation text at **3.58:1**, and "Awaiting confirmation" / "Urgent" pills
   at **4.40 / 4.49:1** — marginal but under. Everything else measured passes.
7. **"Back to X" placement is inconsistent** — above the title on tickets,
   below it on contractor and tenant detail.
8. **The Files tab stacks two empty states** (a dropzone *and* a "No files yet"
   panel), ~230px for nothing.
9. **17 distinct font sizes**, with **51 usages at or below 10.5px** including
   8px, 9px, 9.5px and 10.5px.

---

## 4. The layout system to move to

### 4.1 One page width, one place

Today `max-w-[1510px] px-6 xl:px-7` is written out in **six files**
(`AppShell.tsx` ×3, `PropertyTabs.tsx`, `maintenance.index.tsx`,
`messages.$caseId.tsx`, `properties.index.tsx`) and the ticket page ignores it
entirely. Any width change needs six edits today.

```css
/* styles.css, inside @theme */
--container-page:  110rem;  /* 1760px -> max-w-page */
--container-prose:  70ch;   /* max-w-prose-fixi, for descriptions */
```

**Why 1760px and not "full width".** Derived, not chosen by taste. The widest
page is Maintenance. Its table needs 848px of fixed columns plus ≥500px for the
Issue title before it stops truncating = ~1350px; plus a 320px right rail (the
width at which "Harbourside Plumbing & Heating" stops clipping), a 24px gap and
2×28px gutters = **1750px**. Round to 1760. Past that, extra width only
re-creates the fling-apart problem, because nothing on these pages wants a cell
wider than ~560px. Side margin at 2552px becomes 287px instead of 412px.

Then delete the five hand-rolled copies in favour of `PageContainer`, and give
the **ticket page** the container it never had — this one line is the highest
effect-to-effort change in the whole audit:

```tsx
// maintenance.tickets.$ticketId.{-$section}.tsx:154
- <div className="px-8 py-6">
+ <div className="mx-auto w-full max-w-page px-6 py-5 xl:px-7">
```

That alone fixes the 2073px timeline gap, the 1098px key-value cells, the
2205px progress rail and roughly half the dead graph canvas, because all four
are width-derived.

### 4.2 Grids add columns; cards do not inflate

The rule: **a card has a target width, not a fraction of the row.**

| Grid | Classes | Result at 1704px |
|---|---|---|
| Property cards | `grid-cols-[repeat(auto-fill,minmax(288px,1fr))] gap-4` | 5 × 332px — no orphan |
| Chart cards | `grid-cols-[repeat(auto-fill,minmax(420px,1fr))] gap-4` | 4 × 411px — all on one row |
| Fixed-count KPI rows | keep the count, cap the **section**: `max-w-[1040px]` (4 tiles) / `max-w-[1480px]` (6) | no empty trailing track |

Never let a card exceed ~1.6× its design width; add a column or cap the section.

### 4.3 Tables: an explicit column budget

Replace auto layout with `table-fixed` + `<colgroup>` so the important column
absorbs slack and the trivial ones stop hoarding it. Maintenance:

```tsx
<table className="w-full table-fixed text-[12px]">
  <colgroup>
    <col className="w-[56px]"  />   {/* # */}
    <col />                          {/* Issue — absorbs all slack */}
    <col className="w-[190px]" />   {/* Address */}
    <col className="w-[96px]"  />   {/* Urgency */}
    <col className="w-[130px]" />   {/* Status */}
    <col className="w-[240px]" />   {/* Assigned to */}
    <col className="w-[92px]"  />   {/* Updated */}
    <col className="w-[44px]"  />   {/* actions */}
  </colgroup>
```

Same treatment for Contractors (cap the card `max-w-[1180px]`) and Tenants
(`max-w-[1100px]`), with `text-right tabular-nums` on count columns. Tenants'
eye travel drops from 1201px to ~640px. Cell padding `px-2` → `px-3`; 8px is
tight for 12px type and it appears 64 times.

**The icon column — and a correction.** Both analyses recommended deleting the
leading icon column in Maintenance and Contractors, since it renders a
byte-identical glyph on every row and costs 56px. For Contractors that is
right. For **Maintenance it is now wrong**: the code comment at
`maintenance.index.tsx:341-347` explains the placeholder exists because there
was "no property-photo field on the backend". **That comment went stale in this
same session** — properties now carry `photo_key`, the images are in
`src/assets`, and `PropertyPhoto` + `resolvePropertyPhoto` already handle null.
So the better fix is to make the column carry real information: add
`property_photo_key` to the case-list payload (`app/api/cases.py` + schema) and
render a real 32px thumbnail. Visual property identification is genuinely
useful when scanning 39 tickets. Keep the tenant avatar for the same reason —
initials differ per row.

### 4.4 Line length

The single worst readability number in the audit is a 1300px, ~250-character
line. One change in `AppShell.tsx:289` fixes every page description at once:

```tsx
<p className="mt-1 max-w-prose-fixi text-sm text-muted-foreground">
```

and in the Overview needs-attention row, `line-clamp-1` → `line-clamp-2` with
`max-w-[78ch]`. Two readable lines beat one 250-character line clipped at 194.

### 4.5 Ticket header: 526px → ~344px, 44px scrolled

Order of operations, each independently shippable:

1. the container from §4.1 (5 minutes)
2. fold the back-link into an icon button on the title line (−36px)
3. urgency badge onto the title line (−24px)
4. merge address + "updated · version" into one meta line (−20px)
5. collapse the right-hand cluster from two rows to one (−44px)
6. escalation banner out of `CaseProgress`, one line + a "Details" disclosure (−28px)
7. cap the progress rail `max-w-[860px]` — it is currently 2205px for five labels (−90px)
8. delete the "Record an update" row; the trigger joins the action cluster (−68px)
9. sticky tab strip, underline idiom (matches `PropertyTabs`, removes a third tab style)
10. on scroll, show `#91 – title` + status inside the sticky strip, via
    `IntersectionObserver` on a sentinel — no scroll listener, no layout shift

Result: **~344px escalated, ~304px otherwise, 44px once scrolled**, on all ten tabs.

### 4.6 The agent graph

`CaseFlow.tsx:304` currently reads `fitViewOptions={{ padding: 0.18, minZoom: 0.55, maxZoom: 1 }}`.
`fitView` works correctly — *(measured)* `translate(548px,48px) scale(0.99)` — it
is the **`maxZoom: 1` cap** that leaves 43% fill when the content could scale
~1.97×. That cap was added earlier in this session to stop long cases being
shrunk; the right fix is to raise the ceiling, not remove the floor:

- `fitViewOptions={{ padding: 0.08, minZoom: 0.5, maxZoom: 1.6 }}`
- make `COLUMN_WIDTH` responsive to the measured canvas via `ResizeObserver`,
  clamped `Math.min(420, Math.max(300, floor((canvasW - 32) / columns)))`
- height `clamp(420px, calc(100vh - 360px), 900px)` instead of the fixed 720 cap
- add `<Controls showInteractive={false} />`; a real affordance beats the text
  hint, which is currently gated on `columns > 4` and so is **hidden on a
  4-round case that still pans and zooms**
- move `RunDetail` into a `2xl` side column so clicking a decision does not
  push the graph off-screen
- **drop `key={steps.length}`** — see §5, this is a correctness fix, not polish

### 4.7 Type scale: 17 sizes → 7

Nothing below 11px. Add to `@theme`: `--text-micro` 11/16 (hard floor),
`--text-body` 12/18, `--text-strong` 13/20, `--text-section` 15/22,
`--text-title` 20/28, `--text-metric` 26/30 `tabular-nums`, `--text-hero` 32.

Also fix the inverted hierarchy: the page title is `text-2xl` (24px) while KPI
values are `text-xl` (20px) — **the word "Overview" is currently louder than
the number 19**. Title down to 20, metrics up to 26.

Row heights: 36 (dense) / 44 (default) / 56 (genuine two-line). Maintenance
rows currently measure 44–54px in one table because wrapping is accidental.

---

## 5. Motion

### 5.1 The constraint that shapes everything

*(measured)* FCP **560ms**, average API response **10ms**, slowest 41ms, DOM
interactive 28ms. **This application is already fast.** Long animations would
not make it feel more alive; they would make it feel slower. Durations below
are deliberately short.

Second constraint, and the more dangerous one: **everything polls.** Case
detail every 2s, case list / events / runs every 4s, metrics / notifications /
appointments every 5s, agent status every 10s — twelve hooks, roughly 30
requests a minute at rest. *Any animation keyed on "data arrived" fires every
few seconds forever.* Skeletons must stay gated on `isLoading`, never
`isFetching` (they currently are — keep it that way).

The opportunity is the inverse of the brief's framing: the data is **already**
live and the UI never says so. Surfacing that beats decorating.

### 5.2 Do not add a motion library

Measured with real Vite 8 + React 19.3 production builds, not quoted — the
published "~6 kB LazyMotion" figure predates v13:

| Option | Cost (gz) |
|---|---|
| `motion@13.4.0`, full + AnimatePresence | +40.9 kB |
| `motion`, LazyMotion + domAnimation, sync | +27.9 kB |
| `motion`, LazyMotion, async feature chunk | +14.5 kB initial |
| **This plan, CSS-first** | **+4.5 kB** (JS +2.5, CSS +2.0) |
| `@formkit/auto-animate` (optional, list reorder only) | +3.3 kB |

Against a 321.7 kB gz JS baseline. Nothing in the brief needs `motion`:

- exit animations for every dialog and popover — Radix already waits on
  `animationend` via `@radix-ui/react-presence`, so
  `data-[state=closed]:animate-out` just works, 0 kB
- route transitions — the View Transitions API, now **Baseline** (Chrome 111,
  Safari 18, Firefox 144; 91.75% global), driven by TanStack Router's
  `defaultViewTransition`, present in the installed 1.170.18, 0 kB
- count-up and change-flash — about 40 lines of `requestAnimationFrame`
- list reorder FLIP — `auto-animate` at 3.3 kB, which honours reduced motion itself
- toasts — `sonner@2.0.8` already ships its own reduced-motion block

`tw-animate-css@1.4.0` is **already installed** and supplies the `animate-in` /
`slide-in-from-*` / `fade-*` vocabulary. It is currently used in exactly two
places in the entire app.

### 5.3 The foundation, which must land first

There is presently **zero** `prefers-reduced-motion` handling anywhere — not in
`src` (0 matches), and not in `tw-animate-css` itself (0 matches in its dist).
TanStack Router does not check it either. So the foundation is:

1. motion tokens in `@theme` — four durations only (90 / 140 / 200 / 320ms) and
   three easings, using Tailwind v4's real namespaces (`--transition-duration-*`,
   `--ease-*`) so the same tokens drive both transitions and keyframes
2. a global `@media (prefers-reduced-motion: reduce)` guard that also kills
   `::view-transition-*` and React Flow's marching-ants edges — using
   `animation-duration: 1ms`, not `0s`, so Radix's `animationend` unmount still fires
3. a subscribed `usePrefersReducedMotion()` hook for the JS-side gates
   (count-up, stagger, router transition types)

Every feature then opts out at its own level too, so nothing depends on a
single `!important` cascade.

### 5.4 What to animate

| Item | Trigger | Duration | Notes |
|---|---|---|---|
| Route change | navigation | 200ms | `defaultViewTransition`; return `types: false` under reduced motion — the cleanest escape hatch in the stack |
| Table rows | first load only | 200ms, 20ms stagger, **capped at ~12 rows** | never on refetch |
| Stat counters | value actually changes | 640ms count-up + tint flash | `tabular-nums` so digits do not jitter |
| Dialogs and popovers | open and close | 140–200ms | Radix + CSS, no JS |
| Buttons, tabs, rows | hover / press | 90–140ms | the existing `transition-colors` vocabulary, tokenised |
| Skeletons | `isLoading` only | 1400ms shimmer | content-shaped, replacing the 12 bare "Loading…" strings |
| Graph nodes and edges | a genuinely new node | 200 / 320ms | requires the `key={steps.length}` fix first |
| Charts | mount | 320ms | `@starting-style`, bars grow from the baseline |

### 5.5 The honest agent indicator

The existing code comment already gets the ethic right — *"an indicator that is
always green tells the operator nothing"* — and the motion must not undo it:

1. **Idle animates nothing.** No breathing dot. Idle motion reads as activity.
2. **`isFetching` never animates.** The poll firing is this component working,
   not the agent. This is the specific temptation to refuse.
3. **Unknown animates nothing** — static amber, "Agent status unavailable".
4. **Motion is never the only signal.** The label says working or idle; under
   reduced motion the ring becomes a static halo, still distinguishable.
5. **Disclose staleness** — `agent_active` is up to 10s old.

### 5.6 Explicitly do not animate

Each of these is a plausible idea that would make the tool worse: global search
results (they change per keystroke); the notification list on its 5s poll (a
list that reshuffles while you read is hostile); relative timestamps; the agent
pill on `isFetching`; skeletons on background refetch (with nine polling hooks
this strobes the whole app); any React-Query-tied global loading bar (something
is always in flight); auto-panning the graph or the message thread when content
arrives — offer a chip instead; and `animate-pulse` as a liveness signal, which
conflates "loading" with "working".

### 5.7 One correctness fix hiding in here

`CaseFlow.tsx:281` renders `<ReactFlow key={steps.length}>`. The entire canvas
is torn down and rebuilt whenever a step is added — which, on a 4s poll against
an active case, happens live: the viewport resets, `fitView` re-runs, and no
entry animation is possible. **This is a pre-existing defect, not a polish
item.** Fix it whether or not any animation ships.

---

## 6. Priority

### P0 — this *is* the complaint
| # | Item | Effort |
|---|---|---|
| 1 | Ticket page container (`mx-auto max-w-page`) — one line, fixes four symptoms | **5 min** |
| 2 | Table column budgets: `table-fixed` + `colgroup`, right-aligned numerics, `px-3` cells | 4–5 h |
| 3 | Line length: `max-w-prose-fixi` on descriptions, `line-clamp-2 max-w-[78ch]` on Overview | 30 min |
| 4 | Ticket header restructure + sticky underline tabs (526px to ~344px, 44px scrolled) | 3–4 h |
| 5 | Type below 11px raised to an 11px floor (51 usages) | 1 h |
| 6 | Status-badge casing (3 call sites) + Reports category casing | 30 min |
| 7 | Motion foundation: tokens + the reduced-motion guard | 1 h |

### P1
| # | Item | Effort |
|---|---|---|
| 8 | Page width 1510 to 1760 as one token; delete 5 duplicated containers; rail 270 to 320 | 2 h |
| 9 | Grids add columns (`auto-fill`); property photo 3.7:1 to 2.2:1 | 2 h |
| 10 | Agent graph: `maxZoom` 1.6, responsive columns, viewport-clamped height, `Controls`, `RunDetail` beside the canvas | 3 h |
| 11 | `CaseFlow` `key={steps.length}` removal (correctness) | 1 h |
| 12 | Route transitions + micro-interactions + skeletons + counters + agent ring | 1 day |
| 13 | Message-thread UUID heading (backend: add `case_number` / `case_title`) | 45 min |
| 14 | KPI and metric tile geometry; H1 24 to 20, metrics 20 to 26 | 1.5 h |
| 15 | Charts: n=1 handling, horizontal bars at n<=3, plot heights, 8px to 10px labels | 2 h |
| 16 | Messages: fill the window, drop the box-in-box, cap message text at 72ch | 1.5 h |

### P2
| # | Item | Effort |
|---|---|---|
| 17 | Type-scale token sweep (17 to 7 sizes, ~550 mechanical call sites) | 3–4 h |
| 18 | One `StatTile`, one card padding, one `h2` size, a `CardEmpty` variant | 3 h |
| 19 | Decide dark mode: wire it up or delete the dead `.dark` block | 1–3 h |
| 20 | Remove `recharts`, or adopt it | 15 min |
| 21 | Fix `mm/dd/yyyy` to UK format | 20 min |
| 22 | Sidebar: use the ~700px of dead vertical space for per-status counts | 1.5 h |
| 23 | `@formkit/auto-animate` on card lists (+3.3 kB) | 1 h |

**Order:** 1, 3, 6, 7, then 2, 4, 8, 9. Items 1, 2 and 8 compound: the column
budget only stops truncating the Issue title once the page is 1760px wide.

---

## 7. How to verify this work

`vitest.config.ts` is `environment: "node"` with `include: ["src/**/*.test.ts"]`
— **no jsdom, so no `.tsx` component test will run.** Keep the testable surface
pure (`src/lib/motion.test.ts` for the stagger cap and the flash predicate) and
verify the rest **by running it**, which is this repo's stated method:

- DevTools, Rendering, *Emulate `prefers-reduced-motion: reduce`*, then check
  that navigation does not cross-fade, the agent ring is a static halo,
  skeletons are flat, dialogs still **close** (the Radix `animationend` path),
  and chart bars render at full height on first paint.
- Re-measure the numbers in section 2 after each P0 item; they are the
  acceptance criteria. Specifically: ticket chrome <=344px, worst
  `justify-between` gap <=200px, graph canvas fill >=70%, zero type below 11px.

## 8. What this audit could not check

- **Narrow viewports.** Chrome's window would not resize below the 2560px
  display width during the audit, and neither CSS `zoom` nor `pushState` moves
  media queries. Everything below 1280px is assessed from source only. The
  `sm:` / `md:` / `lg:` behaviour should be checked in a real narrow window
  before shipping section 4.2.
- **Six ticket sub-tabs** (Summary, Calls, Property, Messages, and the two
  property sub-tabs) were photographed but not analysed in depth. The header
  findings apply to all ten tabs; the content findings cover the four examined.
- **Print styles.** `print:hidden` exists in `AppShell` and the Reports page has
  a "Print / Save as PDF" button that was not exercised.

---

## 9. What was implemented, 21 September 2026

The plan above was written as an audit. This section records what
actually landed against it, what the numbers came out at, and what was
left. Where the two disagree, this section is the newer fact.

### 9.1 Acceptance criteria, re-measured

| Criterion (§7) | Target | Before | After |
|---|---|---|---|
| Ticket chrome above the first card | <=344px | 526px | **321px** |
| Type smaller than 11px | 0 | 51 usages | **0** |
| Agent graph canvas fill | >=70% | 43% | **71-89%**, no overflow |
| Worst `justify-between` gap | <=200px | 657px | see §9.5 |

Type is now seven sizes and only seven: 11 / 12 / 13 / 15 / 20 / 26, plus
14px on two `size="lg"` buttons on Reports. Verified by walking every
element with a text node on all eight destinations plus the ticket page
and reading its computed `font-size`, not by grepping source — the
distinction turned out to matter (§9.4).

### 9.2 Layout

- One page width. `--container-page: 110rem` replaces six hand-written
  `max-w-[1510px]`, and the ticket page — which had no container at all —
  now uses it.
- Ticket header: five rows plus a two-row action cluster plus a button
  row, collapsed to two rows with a sticky tab strip.
- Maintenance table: `table-fixed` with an explicit `<colgroup>`
  (56/52/auto/190/96/164/210/92/44). Rows are a uniform 45px. The dead
  `Building2` icon repeated on all 39 rows became the property
  photograph — `property_photo_key` was added to `RepairCaseSummary` for
  it.
- Charts (delegated): case volume 5.4:1 -> 2.52:1, spend 7.1:1 -> 2.98:1,
  resolution 8.6:1 -> 2.98:1, donut 96px -> 160px, and the
  single-year "quoted by year" chart — one bar, always 46px, comparing
  nothing — replaced by a sentence.

### 9.3 Motion

Built on the foundation §5.3 required, in that order: tokens in `@theme`,
a global `prefers-reduced-motion` guard, then a subscribed
`usePrefersReducedMotion()` for the JS-side gates.

- **Route transitions.** `defaultViewTransition` with a `types` function
  deriving forward / back / lateral from path depth rather than history
  direction. `AppShell` names three snapshot regions, so only
  `page-content` travels; the sidebar and utility bar morph in place.
  The same function returns `false` -- TanStack's documented "skip this
  one" -- under reduced motion, and when the document is not visible.
  The second case is not an optimisation: Chrome aborts a transition
  started in a hidden document and rejects the transition's `ready`
  promise, TanStack never attaches to it, and the unhandled rejection
  lands in the console as `InvalidStateError: Transition was aborted
  ... Document hidden`. Deciding per navigation rather than at router
  construction also means the motion preference is re-read every time
  instead of being frozen at boot.
- **Skeletons.** Twelve bare "Loading…" strings replaced by placeholders
  shaped like their content — the KPI strip at its real 72px card height,
  table rows as real `<tr>`/`<td>` so the `<colgroup>` keeps them on the
  exact columns the data will occupy.
- **`<Metric>`.** KPI figures count up on arrival and flash on change.
  The arithmetic lives in `lib/metric-format.ts` and is unit-tested,
  because both defects it produced were arithmetic (§9.6).
- **Agent ring.** Gated on the same boolean as the dot's colour, so it
  pulses only while a run or a due job is genuinely in flight.

The reduced-motion guard uses `animation-duration: 1ms`, not `0s`: Radix
waits for `animationend` before unmounting, and a zero-duration animation
is not guaranteed to fire it. A dialog that will not close is worse than
one that animates.

### 9.4 The defect that made most of this a no-op

`cn()` was deleting the type scale.

tailwind-merge classifies `text-<word>` by looking the word up in
Tailwind's built-in font sizes and assuming anything else is a colour.
Every size on the new scale is a custom name, so all six were filed under
`text-color`, judged to conflict with the text colour beside them in the
same `cn()` call, and dropped:

```
twMerge("text-strong text-sidebar-foreground") -> "text-sidebar-foreground"
```

No error, no warning, no build failure. The class simply was not in the
DOM and the element fell back to the 16px browser default — which is how
eight sidebar links ended up as the largest text on a dashboard whose
table rows are 12px, while the source said 13px and the compiled
stylesheet contained a correct `.text-strong` rule.

`lib/utils.ts` now extends tailwind-merge with all five custom token
groups. `lib/utils.test.ts` pins it; reverting the extension fails 16 of
its 17 tests. **Any token added to `@theme` must be added there too.**

This is the strongest possible argument for this repo's "verify by
running" rule: the source, the stylesheet and the build were all correct
and the rendered page was still wrong.

### 9.5 The agent graph fit

`<ReactFlow fitView>` fits the bounding box React Flow derives from its
own node measurements, and measurement is a ResizeObserver, so the box is
whatever happens to have been measured when the call lands. Observed: the
first fit ran against a near-empty box, asked for ~3.6x, took the
`maxZoom` clamp, and left the graph at **137% of its pane** — overflowing
both edges, with the built-in "fit view" button recomputing the same
wrong answer. Declaring `initialWidth`/`initialHeight` helped but was not
deterministic (consecutive loads fitted at 0.837 and 1.6).

The fix removes the dependency: the layout is ours — fixed column width,
fixed row height, known node width — so the extent is arithmetic, and
`fitBounds` takes it directly. Fill is now 71–89% with no overflow in any
observed run.

The residual 71–89% spread is the canvas's *own* size arriving late; the
component subscribes to it so the fit is redone when the panel settles.
It could not be driven to a single value here because the verification
tab was backgrounded, and a non-rendering document runs no rendering
steps, so ResizeObserver deliveries are unreliable by construction.

### 9.6 Two defects in the new code, both caught by running it

- `<Metric>` rendered **"-0"** and **"-0.6h"** on first paint.
  `requestAnimationFrame` passes the timestamp of the frame the callback
  belongs to, which can *precede* the `performance.now()` captured when
  the frame was requested, so elapsed time is negative on the first frame
  and the cubic ease returns a negative multiplier. Progress is now
  clamped at both ends, and anything rounding to zero prints without a
  sign.
- The skeleton shimmer was **invisible**: `color-mix` of `--muted` with
  `--background` produced a 0.008 lightness sweep, because those two
  tokens differ by 0.017. The highlight is `--card` now — a 0.035 sweep,
  the conventional depth for a light theme.

### 9.7 Not done

- **`.dark` was deleted, not fixed.** It defined 32 of the 55 tokens
  `:root` does, missing every status and timeline colour, and nothing in
  the app ever set the class. Shipping a real dark theme means authoring
  the 23 missing values and checking legibility on every screen in both
  themes; that is a design task, not a flag flip. `styles.css` carries the
  recovery command.
- **Narrow viewports remain unverified** (§8). Chrome would not resize
  below the display width during either pass.
- **`prefers-reduced-motion` was not exercised end to end.** The CSS rule
  and the JS hook are both in place and the rule is present in the built
  stylesheet, but emulating the preference needs a DevTools control this
  environment does not expose. The dialog-close path (§7) in particular
  is unproven.
- **The route transitions were never watched running.** They resolve the
  correct `types` on the correct navigations (verified: ticket ->
  Maintenance gives `back`, Maintenance -> ticket gives `forward`), the
  pseudo-element rules and all six keyframes parse in the built
  stylesheet, and `:active-view-transition-type()` is supported here.
  But the verification browser was minimised for the whole pass —
  `document.visibilityState === "hidden"`, and screenshots eventually
  failed with "Cannot take screenshot with 0 width" — so every
  transition was correctly skipped rather than played, and no frame of
  one was seen. **Watch a navigation in a visible window before
  trusting the timing or the 10px travel distance.**

  The same hidden document is why two other things could not be pinned
  down here: `requestAnimationFrame` is suspended in a non-rendering
  document (hence the `settle` timeout in `Metric.tsx`) and
  ResizeObserver deliveries are unreliable (hence the 71-89% spread in
  §9.5).
