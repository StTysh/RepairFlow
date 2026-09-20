# UI components & accessibility audit

Scope: `frontend-fixi/src/components/` (20 files) and `frontend-fixi/src/routes/`
(17 route files, matched against `routeTree.gen.ts`). Read-only review; no
server started, no source edited. Checked against `docs/UI2_INTERACTION_CHECKLIST.md`
and the standard in the audit brief (no enabled control may silently do
nothing; disabled controls must state why, adjacent to themselves; no
fabricated state; colour never the only signal; empty/loading/error states
must differ; responsive at 768px).

**Headline: this is an unusually honest codebase.** Every interactive
element I traced reaches a real handler — a TanStack Query mutation against
a documented endpoint, a real client-side derivation, or a real `<Link>`/
`<a>` navigation. I did not find a single `console.log`-only button, a toast
with no write behind it, or a fabricated "Sent"/"Confirmed"/"Booked" string.
The problems below are real but narrower: a missing mobile nav, a few stale
"route doesn't exist yet" comments now producing full-page-reload links
instead of SPA `Link`s, and inconsistent disclosure of *why* a control is
disabled.

---

## Control inventory

Legend for **Verdict**: WIRED (reaches a real mutation/query/navigation),
WIRED-BUT-STALE (works, but not via the mechanism its own comment/the
checklist claims), DISABLED-OK (disabled with a stated, correct reason),
DISABLED-WEAK (disabled but the reason is not reliably visible), NIT
(cosmetic only, no functional claim).

### Global shell — `AppShell.tsx`, `UtilityBar.tsx`

| Control | Wired to | Verdict |
| --- | --- | --- |
| Sidebar × 8 links | `<Link>` per route, `aria-current` on active | WIRED |
| Messages unread badge | `GET /messages/unread-count`, hidden at 0 | WIRED |
| Agent status panel | `GET /metrics/dashboard`, 3 real states (working/idle/unavailable) | WIRED |
| Operator chip / Sign out (`LoginGate.tsx`) | session creds; `logout()` | WIRED |
| Global search input | `CaseSearchContext`, consumed by Maintenance list | WIRED |
| Notifications bell + popover rows | `GET /notifications`; each row `<Link>` to its case | WIRED |
| **+ New Ticket** (`NewTicketDialog.tsx`) | `POST /cases`, navigates to new case | WIRED |
| **Sidebar itself at <1024px** | — | **MISSING — see HIGH-1** |

### `NewTicketDialog.tsx`, `RecordFieldUpdateDialog.tsx`, `RescheduleDialog.tsx`, `CaseLifecycleActions.tsx`, `DirectoryForms.tsx` (all dialogs)

Every field: `<label htmlFor>` paired to a real `id`, inline error under the
field gated on a `touched` flag, submit button shows a pending label
(`"Saving…"`/`"Creating…"`/etc.) and is `disabled` while pending or invalid,
Cancel is `disabled` while pending, Radix `Dialog`/`AlertDialog` supplies
focus-trap-in, focus-return-on-close and Escape-to-close for free (verified
no `onEscapeKeyDown`/`onOpenAutoFocus` overrides suppress this, except
`properties.index.tsx`'s `NewPropertyDialog` which explicitly re-wires
Escape to the same close handler — redundant but harmless). Inputs are
cleared only on success (`reset()` called after `mutateAsync` resolves, kept
on catch). **Verdict: WIRED**, no missing pieces in any of these five forms.

### Maintenance list (`maintenance.index.tsx`)

| Control | Wired to | Verdict |
| --- | --- | --- |
| Status / Urgency / Property / Contractor filter | refetch / client filter | WIRED |
| KPI cards | `GET /metrics/dashboard`, delta suppressed (`null`) when dishonest | WIRED |
| Row → ticket, row "…" → Open ticket / Open conversation / Cancel | `<Link>`s + `POST /cases/{id}/cancel` | WIRED |
| Row "…" on terminal case | replaced by static reason text, not a disabled item | DISABLED-OK |
| "Updated ↓" column header | — | **NIT — see LOW-1**, no onClick, static text |
| Marketing tile → "View properties" | real `<Link to="/properties">` | WIRED |

### Ticket detail (`maintenance.tickets.$ticketId.{-$section}.tsx`, 901 lines)

| Control | Wired to | Verdict |
| --- | --- | --- |
| 9 section tabs | route param via `<Link>`, deep-linkable | WIRED |
| Copy address | `navigator.clipboard.writeText` | WIRED |
| `CaseToolbar`: Share / Edit / kebab (Copy ref / Open conversation / Property history / Export) | clipboard, `PATCH /cases/{id}`, `<a>`/`<Link>`/blob download | WIRED, one item **WIRED-BUT-STALE — see MED-1** |
| `CaseLifecycleActions` status menu | `/cancel` `/resume` `/reopen`, each version-checked | WIRED |
| `RecordFieldUpdateDialog` | `POST /cases/{id}/field-updates` | WIRED |
| `DecisionCard` Approve/Reject | `POST /actions/{id}/approval`, hash+version checked | WIRED |
| Calls: expand row, ▶ Play recording | `GET /communications/{id}/recording` → blob → `<audio>` | WIRED |
| `RescheduleDialog` | `POST /appointments/{id}/reschedule`, shows PENDING not CONFIRMED | WIRED |
| Tenant Mail/Phone icon buttons | real `mailto:`/`tel:`, disabled when `!contact_allowed` | DISABLED-OK (see MED-2 on disclosure) |
| `ProfileLinkButton` (tenant/contractor profile) | plain `<a href>` | **WIRED-BUT-STALE — see MED-1** |
| Work tab (`WorkGraph`) | renders real work orders + dependency edges, non-interactive nodes (correctly not buttons) | WIRED |
| Files / Costs / Messages tabs | `DocumentsPanel`, `CostsPanel`, `MessagesPanel` | WIRED |

### `DocumentsPanel.tsx`, `CostsPanel.tsx`, property Documents/Notes tabs

Upload (input + drag/drop), preview (image/PDF, revokes blob URL on
close/unmount), download, delete (confirmation dialog that stays open until
the mutation settles, not an auto-closing `AlertDialog.Action`), add/edit
cost entry with pence-safe parsing. All real, all `WIRED`. Evidence photos
correctly label anything not `provenance: LIVE` as "Illustrative sample —
not a photo of this property" rather than presenting it as a real photo.

### Properties (`properties.index.tsx`, `.history.tsx`, `.details.tsx`, `.documents.tsx`, `.notes.tsx`)

| Control | Wired to | Verdict |
| --- | --- | --- |
| Search, include-archived checkbox, pagination | `GET /properties` | WIRED |
| New property dialog | `POST /properties`, UK-postcode regex check | WIRED |
| 4 tabs | real routes | WIRED |
| History table: sort headers (Date/Trade/Status/Quoted), select row, select-all, Export selected CSV | client-side sort/select, real CSV blob download | WIRED |
| Donut / bar chart / recurring rows → trade/year chip filters | filters the table below | WIRED |
| Details tab Edit → form | `PATCH /properties/{id}`, archived → disabled with visible reason | DISABLED-OK |
| Documents/Notes CRUD | real endpoints, per-row confirm-delete state (not `window.confirm`) | WIRED |
| `PropertyTabs` header "Edit" `<Link>` when archived | `pointer-events-none` + `aria-disabled`, but still a real `href` | **DISABLED-WEAK — see MED-3** |

### Contractors, Tenants (`contractors.index/$id`, `tenants.index/$id`)

| Control | Wired to | Verdict |
| --- | --- | --- |
| Search, trade/approval/archived filters | URL-backed, refetch | WIRED |
| Create/Edit dialogs (`DirectoryForms.tsx`) | `POST`/`PATCH`, no approval-status field on the create form (matches "a candidate from the web is not an approved contractor") | WIRED |
| Approve contractor | disabled until `verification_note` exists, **reason shown as visible text**, not just title | DISABLED-OK |
| Row chevron → profile | `<Link>` | WIRED |
| Tenant "Messages" action | only rendered when `hasCases`, links to `/messages?q=name` (documented as the closest honest proxy, no tenant-id filter exists) | WIRED |
| "Not assignable" label on non-approved contractor | static text next to the Pill, not colour alone | WIRED |

### Insights, Reports, Messages, Overview

| Control | Wired to | Verdict |
| --- | --- | --- |
| Overview metric cards, needs-attention rows, upcoming/activity rows | `GET /overview`, all real `<Link>`s | WIRED |
| Insights date presets / from / to / property / category / include-archived | URL search params, refetch | WIRED |
| Every chart bar/segment/row (`Charts.tsx`) | real `<button>`, `aria-pressed`, `aria-label` with full sentence, sr-only data list per chart | WIRED |
| Drill-down panel | `GET /insights/cases`, honest fallback text when a bucket's hour bounds are unknown | WIRED |
| Reports filters, Export CSV, Print | `GET /reports/summary`, `GET /reports/export.csv`, `window.print()` | WIRED (not URL-backed — matches the checklist's own "open" gap) |
| Thread list: search / unread-only / include-archived | refetch | WIRED |
| Composer: Internal note vs Email/SMS | `POST /messages/threads/{id}`; Email/SMS button reads **"Save draft"**, not "Send", with the reason printed under it | WIRED |
| Per-message "mark unread" | `POST /messages/{id}/unread` | WIRED |

---

## Findings

### HIGH-1 — No navigation below 1024px; nothing replaces it
**Severity: HIGH**
`frontend-fixi/src/components/fixi/AppShell.tsx:114`

```
<aside className="sticky top-0 hidden h-screen w-[218px] shrink-0 flex-col ... lg:flex">
```

The entire sidebar — all 8 primary destinations, the agent status panel and
the sign-out control — is `hidden` below Tailwind's `lg` breakpoint (1024px)
with **no hamburger menu, no bottom nav, no drawer** anywhere in the
codebase (checked `AppShell.tsx`, `UtilityBar.tsx`, and grepped the whole
tree for `Menu|Sheet|Drawer|md:hidden`). `UtilityBar` (search, notifications,
+New Ticket) stays visible, so the top of the screen looks intentional, not
broken.

At the 768px width this audit is asked to check, a user who lands on any
page other than Overview (e.g. a ticket detail page, opened from a bookmark
or shared link) has **no way to reach Contractors, Tenants, Insights,
Reports or Messages** short of hand-editing the URL. The one exception is
Overview's own metric cards, which still link out — but Overview itself is
unreachable from anywhere else without the sidebar.

**Fix:** a `lg:hidden` menu button in `UtilityBar` opening the same `nav`
list in a Radix `Dialog`/`Popover` (the codebase already uses Radix
Dialog/Popover elsewhere, so this is idiomatic, not a new dependency).

### MEDIUM-1 — Three navigations use full-page `<a href>` because their own comments are now wrong
**Severity: MEDIUM**
- `frontend-fixi/src/components/fixi/CaseToolbar.tsx:416-423` ("Open
  conversation")
- `frontend-fixi/src/routes/maintenance.tickets.$ticketId.{-$section}.tsx:576-593`
  (`ProfileLinkButton`, used at lines 646 and 667 for tenant/contractor
  profile)

Each carries a comment along the lines of *"neither route exists in this
checkout yet ... a full navigation still reaches the right page once it
does"* and uses a plain `<a href="/messages/${id}">` /
`<a href="/tenants/${id}">` instead of a typed `<Link>`. But
`routeTree.gen.ts` shows `/messages/$caseId`, `/tenants/$tenantId` and
`/contractors/$contractorId` are all registered routes today, and
`maintenance.index.tsx:524-532` already uses a correct `<Link to="/messages/$caseId">`
for the identical "Open conversation" action — proving the fix is a one-line
change, just not applied consistently. The user-visible effect: clicking
these three links does a full page reload (loses toasts, resets the React
Query cache, visible flash) instead of an instant client-side transition,
and the app's own claim about why is stale/false.

**Fix:** swap the three `<a href>` call sites for `<Link to=... params=...>`.

### MEDIUM-2 — Disabled-reason disclosure is inconsistent: several controls rely on `title` only
**Severity: MEDIUM**

The brief requires a disabled control's reason to be shown *adjacent to the
control*. Most of the app does this correctly with visible text (contractor
approve button, cancel-blocked menu row, archived-property banner). But
several controls state the reason only in the `title` attribute, which is
invisible until hover (fails on touch, and isn't guaranteed to be announced
consistently by screen readers when a more specific accessible name is also
present):

- `frontend-fixi/src/components/fixi/Charts.tsx:249-276` — the disabled
  "Uncategorised" row in `CategoryBreakdownDonut` has a `title` explaining
  why it can't be clicked, but the row's own `aria-label` (line 265-269)
  omits that reason entirely — a screen-reader user hears the count and
  percentage with no indication the row is inert or why.
- `frontend-fixi/src/routes/maintenance.tickets.$ticketId.{-$section}.tsx:516-539`
  (`IconButton`) and `:608-619` — tenant Mail/Phone buttons disabled for
  `!contact_allowed` state the reason only via `title`.
- `frontend-fixi/src/components/fixi/DocumentsPanel.tsx:218-224` — the
  preview toggle when a file type isn't previewable (lower stakes: cosmetic,
  not a data-changing action).

**Fix:** where a `title` already carries the reason, either also put it in
`aria-label`/`aria-describedby`, or add the same sentence as small adjacent
text as the rest of the app already does for the contractor-approval and
lifecycle-action cases.

### MEDIUM-3 — "Disabled" archived-property Edit link is still keyboard-activatable
**Severity: MEDIUM**
`frontend-fixi/src/components/fixi/PropertyTabs.tsx:140-155`

```
<Link to="/properties/$propertyId/details" ... aria-disabled={p.is_archived}
  className={cn(..., p.is_archived ? "pointer-events-none opacity-50" : "hover:bg-accent")}>
```

`pointer-events-none` blocks mouse clicks and `aria-disabled` is a hint to
assistive tech, but neither actually prevents a real `<a>`/`<Link>` from
being focused and activated with Enter — there's no `onClick` guard or
`tabIndex={-1}`. A keyboard user can still "activate" a control that looks
disabled to everyone else. Impact is contained: the destination
(`properties.$propertyId.details.tsx:81-95`) independently disables its own
Edit button with a stated reason ("Sample-history properties can't be
edited"), so no write is actually possible — but the control itself isn't
correctly disabled, and the pattern (a fake-disabled `Link`) is worth fixing
before it's copied somewhere with no second gate.

**Fix:** either drop the `Link` to a plain non-interactive `<span>` when
archived, or add `tabIndex={-1}` and an `onClick` guard that no-ops.

### LOW-1 — "Updated ↓" list header looks like a sort control but isn't one
**Severity: LOW / NIT**
`frontend-fixi/src/routes/maintenance.index.tsx:290`

Plain `<th>` text with a decorative down-arrow, no `onClick`, no `<button>`
— unlike the real sortable headers this same app builds correctly in
`properties.$propertyId.history.tsx`'s `SortableTh` (button + `ArrowUp`/
`ArrowDown`/`ArrowUpDown` that actually re-sorts). Not claimed as
interactive anywhere in the checklist, so this isn't a false claim, but
visually it invites the same expectation the real sort headers set
elsewhere in the app.

### Verified-false: the reported "checkbox accessible name is 'on'" issue
I checked every `type="checkbox"` in `frontend-fixi/src` (6 instances:
Insights include-archived, Contractors include-archived, Properties
include-archived, Reports include-archived, and the property-history
select-all/select-row checkboxes). Every one either sits inside a `<label>`
with real trailing text as a sibling text node (implicit label association)
or carries an explicit `aria-label` (`properties.$propertyId.history.tsx:365,493`;
`contractors.index.tsx:143`). None of them would compute an accessible name
of `"on"` from this source. This looks like a stale or transient
`read_page` observation, not a reproducible bug — flagging as resolved/not
found rather than carrying it forward.

### Colour-only signalling
Not found. Every status/urgency/approval/delivery Pill I traced always pairs
colour with a text label (`StatusBadge`, `UrgencyBadge`,
`DELIVERY_TONE`/`DELIVERY_LABEL` in `messages.$caseId.tsx`, "Not assignable"
caption under the contractor approval Pill). `CaseProgress` step dots use
distinct icons (check/dot/triangle/dashed-ban) in addition to colour.

### Empty / loading / error states
Every list/panel I read (Overview's three sections, Maintenance table,
Properties/Contractors/Tenants tables, Insights charts, Reports sections,
Messages thread list, Documents, Notes, Costs) has distinct loading
(skeleton or "Loading…"), error (`ErrorState` with retry), and empty
(`EmptyState` with a specific reason and, where relevant, a CTA) branches
that render different markup — "nothing yet" and "failed to load" never
collapse into the same look.

### Responsive (Tailwind classes, 768px)
Aside from HIGH-1, no other overflow risks found: every data table sits in
a `Card` with `overflow-x-auto` plus a `min-w-[...]` on the `<table>`
(maintenance, contractors, tenants, property history, reports, insights
drill-down, contractor work-history). Search inputs cap width with
`max-w-[Nvw]`/`max-w-full` rather than a bare fixed width. Dialogs use
`w-[min(Nrem,92vw)]` or `max-w-md`/`max-w-sm` with viewport clamps. Messages'
master-detail correctly collapses to a single pane below `lg` with a
`lg:hidden` back link (`messages.$caseId.tsx:118-124`) — this is the one
place a mobile fallback *was* built, which makes the sidebar's omission
(HIGH-1) look like an oversight rather than a deliberate scope cut.

---

## Verdict on `docs/UI2_INTERACTION_CHECKLIST.md`

**It does not materially overstate.** Every row I could verify against
source matched what the checklist claims, including its own hedges (e.g. it
already flags Reports filters as not URL-backed, and already marks Tenants/
property-tabs/dialogs as "not clicked through" — my source read of those
found them consistent with the rest of the codebase, no issues).

Two rows are worth a precision correction rather than a retraction:

> `Contractor View profile | Navigates | router | type`
> `Tenant contact | Opens profile or conversation; disabled with a reason when contact_allowed is false | tenant record | type`

"Backed by: router" reads as TanStack Router's typed `<Link>` mechanism: it
is actually a plain `<a href>` for the profile-link case (MEDIUM-1) — still
a real navigation, just not through the router, and the checklist's own
`type` column is accurate (it compiles and reaches the right URL) even
though "router" slightly overstates the mechanism.

The checklist does not mention responsive/mobile behaviour at all (its
"Verified" legend only covers Overview/Properties/Contractors/Insights/
Messages/Reports/one ticket in a desktop browser pass), so HIGH-1 is an
omission in scope, not a false claim.
