# Implementation notes from the migration work

Assumptions, contract gaps and resolutions recorded while the eight
destinations were built in parallel. Kept because they explain why a
few things are shaped the way they are; every blocking item in here has
since been resolved.


---

## From `frontend-fixi/src/routes/NEEDS_FROM_ROOT_analytics.md`


Written by the agent building `/`, `/insights`, `src/hooks/use-analytics.ts`
and `src/components/fixi/Charts.tsx`. Nothing outside that ownership list
was edited; everything below is either a request for someone who owns the
affected file, or a note of the assumption made in its absence.

## 1. Backend contract wasn't implemented yet at build time

`GET /api/v1/overview`, `/api/v1/insights`, `/api/v1/insights/cases` and
`/api/v1/properties` did not exist on the backend when this was built (only
`backend/app/api/{cases,approvals,metrics,notifications,observations,voice}.py`
were present — no `overview.py`/`insights.py`/`properties.py`). Every field
read off these responses in `use-analytics.ts` is therefore optional and
every consumer falls back to "—" / 0 / an empty list rather than assuming a
field exists. Once the real endpoints land, please diff their actual
response shape against `use-analytics.ts`'s types and fix any mismatch —
particularly:

- **Overview**: assumed `property_count`, `tenant_count`,
  `approved_contractor_count` as top-level scalars; assumed either a direct
  `open_case_count` OR a `case_counts_by_status` map (the "Open cases" KPI
  tries `open_case_count` first, then sums
  `ACTIVE + AWAITING_CONFIRMATION + ESCALATED` from the status map, then
  falls back to "—"). `needs_attention[]` items are assumed to carry `id`,
  `kind` (`AWAITING_APPROVAL` | `ESCALATED` | `OVERDUE_FOLLOW_UP`),
  `case_id`, `case_number`, `case_title`, `message`, `occurred_at` — same
  shape as the existing `NotificationItem` type in `api/types.ts`, extended
  with a `kind` covering overdue follow-up (which `NotificationItem`
  doesn't have). `upcoming_appointments[]`/`recent_activity[]` are assumed
  close to the existing `UpcomingAppointmentItem`/`CaseEvent` shapes with
  `case_number`/`case_title` folded in.
- **Insights**: `category_breakdown[]` percentages are assumed to already
  sum to 100 the way `PropertyStatsResponse.quoted_by_trade` does (the
  donut still applies the same largest-remainder rounding defensively
  either way). `comparison` is assumed to be a map of metric name →
  `{ current, previous, pct_change: number | null, is_new: boolean }` — not
  currently rendered as a UI element yet beyond being available on
  `InsightsResponse`, since the exact metric keys weren't confirmed; **if
  there's a specific "vs previous period" callout expected on the page,
  the shape needs confirming and a render pass added.**
- **`resolution_time_distribution[]` buckets have no confirmed hour
  boundaries.** The contract only promises a `bucket` label + `count`. The
  resolution-time chart's drill-down needs boundaries to filter the
  matching case rows precisely — `ResolutionBucket` optionally reads
  `min_hours`/`max_hours` if present; when absent (the current, unconfirmed
  case), clicking a bucket instead shows every case in the page's current
  filters, with a visible note explaining why. **Please add `min_hours`/
  `max_hours` (or equivalent) to each bucket object** so this drill-down
  can be exact instead of approximate.
- `InsightsCaseRow` (from `/insights/cases`) is assumed to carry `id`,
  `case_number`, `title`, `status`, `property_address`, `trade`,
  `quoted_pence`, `created_at`, `resolved_at` — the minimum needed for the
  inline drill-down table and the resolution-time client-side bucket
  filter above.

## 2. `/tenants` and `/contractors` aren't registered routes yet

`routeTree.gen.ts` only has `/`, `/maintenance/`, `/properties/`,
`/properties/$propertyId/history`, `/maintenance/tickets/$ticketId/{-$section}`
as of this build. The Overview page's portfolio-metrics row needs to link
to Tenants and Contractors, so those two tiles use a plain `<a href="/tenants">`
/ `<a href="/contractors">` (same pattern `__root.tsx`'s `ErrorComponent`
already uses for "Go home") instead of a typed `<Link>`, specifically to
avoid the `Link to` type error a widened string doesn't trigger but a route
literal not present in `FileRoutesByPath` does. **Once those routes are
registered, please convert both to `<Link to="/tenants">` /
`<Link to="/contractors">`** — `routes/index.tsx`, the `MetricLink` calls
near the top of `OverviewPage`.

## 3. `/maintenance` doesn't read a `status` query param

The task brief for this page says the "Open cases" KPI card should link to
`/maintenance?status=…`. `maintenance.index.tsx` (owned elsewhere) holds
`statusFilter` in local `useState` defaulting to `"ALL"` and never reads
`window.location.search` — passing a `status` param today would be a
decorative link with no effect, which conflicts with "every enabled
control does something real". The Overview page's "Open cases" card
therefore links plainly to `/maintenance` (real, working destination) with
no query param. **If `maintenance.index.tsx` is updated to seed its filters
from the URL search string** (mirroring the pattern in
`routes/insights.index.tsx` — no `validateSearch`, read via
`useRouterState({ select: s => s.location.searchStr })` — see §4), the
Overview card can start passing `?status=ACTIVE` for real.

## 4. Why insights.index.tsx doesn't use `validateSearch`

Per the task brief and `properties.$propertyId.history.tsx`'s own comment:
`validateSearch` reproducibly froze the renderer on a hard navigation to a
non-prerendered route (only `/` is prerendered; everything else hits the
SPA fallback shell during hydration). `properties.$propertyId.history.tsx`
gets away with an unvalidated one-off `window.location.search` read because
that route never navigates. `/insights` does navigate (every filter change
pushes a new query string), so it reads search reactively off router state
(`useRouterState({ select: s => s.location.searchStr })`, parsed with
`URLSearchParams`) and writes it with a plain updater function passed to
`useNavigate()`'s `search` option — verified against `npx tsc --noEmit`,
no `as any`/`@ts-expect-error` needed. This is a new pattern in the app (no
existing route both reads and writes its own search params); if a
"canonical" typed-search helper gets added later, this route is a
candidate to migrate onto it.

## 5. `createFileRoute("/insights/")` TS error

As expected per the task brief: `src/routes/insights.index.tsx(37,38)` is
the one remaining `npx tsc --noEmit` error in this agent's files —
`"/insights/"` isn't yet a member of `FileRoutesByPath` until the root
agent regenerates `routeTree.gen.ts`. `AppShell.tsx`'s nav array already
has an `Insights` entry pointing at `/insights`, so no change is needed
there once the tree is regenerated.

## Summary of what was built

- `src/routes/index.tsx` — Overview: portfolio metrics (Properties/Tenants/
  Approved contractors/Open cases, each a real link), Needs attention
  (awaiting approval/escalated/overdue, each linking to its ticket),
  Upcoming appointments (+ "View all"), Recent activity. Real
  `EmptyState`/`ErrorState`/`LoadingRows` throughout; no fabricated numbers.
- `src/routes/insights.index.tsx` — filters (date presets + custom range,
  property, category, include-archived toggle) live entirely in the URL
  query string; charts; an inline `/insights/cases` drill-down panel that
  every chart element opens into (month bar, donut legend row, year bar,
  resolution bucket, recurring-issue row); an "Includes N archival sample
  cases" banner when `includes_archived_history` is true.
- `src/components/fixi/Charts.tsx` — `CaseVolumeChart`, `CategoryBreakdownDonut`
  (largest-remainder rounding so percentages sum to exactly 100),
  `SpendByYearChart` (quoted vs. actual as two distinct series, never
  merged), `ResolutionTimeChart` (+ average/median callouts),
  `RecurringIssuesTable`. Every mark is a real `<button>` with an
  `aria-label`; every chart also carries a `sr-only` list of its own data
  points as a text alternative.
- `src/hooks/use-analytics.ts` — `useOverview`, `useInsights`,
  `useInsightsCases`, `useAnalyticsProperties`, all built directly on
  `request()` from `api/client.ts` (not added to `api/endpoints.ts`/
  `api/types.ts`, which are owned/being edited elsewhere this session).

---

## From `frontend-fixi/src/routes/NEEDS_FROM_ROOT_directories.md`


Written by the agent building `contractors.index.tsx`, `contractors.$contractorId.tsx`,
`tenants.index.tsx`, `tenants.$tenantId.tsx`, `hooks/use-directory.ts` and
`components/fixi/DirectoryForms.tsx`. Nothing outside that list was touched.

## Route tree

These four routes aren't in `routeTree.gen.ts` yet, so `createFileRoute("/contractors/")`
etc. (and any `<Link to="/contractors">` / `to="/tenants/$tenantId"` elsewhere, e.g. the nav
array already added to `AppShell.tsx`) show a TS "not a valid route" error until it's
regenerated. Please regenerate once the contractors/tenants API routes land.

## Resolved: `/messages` link from the tenant profile

`/messages` now exists. Its only filter parameter is `q` (see
`useThreadListFilters` in `hooks/use-messaging.ts`), and the backend's
thread search spans tenant name, so the tenant profile links to
`/messages?q=<display name>` through a typed `<Link>` rather than a plain
`<a href>` with a guessed `tenantId` param. There is no tenant-id filter
on that endpoint; a link using one would look precise and match nothing.

## Contract fields not pinned down precisely

- `GET /tenants/{id}`: the contract says "profile + property summary + cases[]" without exact
  key names. `use-directory.ts`'s `normalizeTenantProfile` checks `property.address_line` /
  `property.postcode` for the nested property summary, and per case-row checks `id ?? case_id`,
  `title ?? case_title`, plus `case_number`, `status`, `updated_at`. If the real shape differs,
  only the normalizer in `use-directory.ts` needs updating — every screen consumes the
  normalized `TenantProfile`/`TenantCaseItem` types, not the raw response.
- `Tenant.preferred_channel` is a plain `str` on the backend (`backend/app/schemas.py`), not a
  validated enum. The tenant form offers a curated `PHONE` / `SMS` / `EMAIL` picker rather than
  guessing a backend enum that doesn't exist; an existing tenant with some other value is kept
  selectable (see `channelOptions()` in `DirectoryForms.tsx`).
- `PATCH /contractors/{id}` approve flow: implemented as `PATCH { approval_status: "APPROVED" }`
  relying on a `verification_note` already persisted on the record (the Approve button is
  disabled client-side until `contractor.verification_note` is non-empty). If the backend
  instead expects the note re-sent in the same PATCH as the approval, let me know and I'll add
  it to `useApproveContractor`.

## Property picker

Tenant create/edit uses `GET /api/v1/properties?limit=200` per the contract (not the
demo-only `GET /api/v1/demo/seed-refs`, which is explicitly documented in this codebase as
demo glue for the "+ New Ticket" flow, not a general properties list). If that endpoint isn't
live yet, the property `<select>` shows "Loading properties…" / an inline "Could not load
properties" message rather than crashing.

## Everything else

List/detail field names otherwise matched the contract as given (`assigned_work_order_count`,
`completed_work_order_count`, `is_archived`, `open_case_count`, `total_case_count`, etc.).
Every optional/nested field is read defensively (`asString`/`asNumber`/array-filter helpers in
`use-directory.ts`) so a missing or renamed field renders as `—` / `0` instead of throwing.

---

## From `frontend-fixi/src/routes/NEEDS_FROM_ROOT_messaging.md`


Files owned by this slice: `routes/messages.index.tsx`, `routes/messages.$caseId.tsx`,
`routes/reports.index.tsx`, `hooks/use-messaging.ts`, `hooks/use-reports.ts`.

## 1. Route tree registration — RESOLVED mid-session

`routeTree.gen.ts` didn't know about `/messages/`, `/messages/$caseId` or
`/reports/` for most of this session (expected — that's the root agent's job).
It was regenerated while this slice was still being built; `npx tsc --noEmit`
is now clean across all five owned files (`hooks/use-messaging.ts`,
`hooks/use-reports.ts`, `routes/messages.index.tsx`, `routes/messages.$caseId.tsx`,
`routes/reports.index.tsx`) with zero errors, verified as the last step of this
slice's work. One thing worth noting for whoever reads this next:
`use-messaging.ts`'s `useThreadListFilters()` still carries one deliberate
`useNavigate() as unknown as (...)` cast (with an explanatory comment at the
call site) -- that one is *not* a route-tree artifact. It's because the hook is
shared by both `/messages` and `/messages/$caseId` with no single static `from`
to bind to, so TanStack Router can't resolve a concrete search schema for a
target it can't pin down statically; confirmed by temporarily removing the cast
and re-running tsc, which reproduced the error even with the route tree fully
registered.

## 2. AppShell can't get `print:hidden` from this slice

`reports.index.tsx` needs the sidebar and utility bar hidden when printing.
`AppShell.tsx` isn't owned by this slice, so instead of editing it, `reports.index.tsx`
injects a scoped `<style>` tag while mounted:

```css
@media print { aside, main > div:first-child { display: none !important; } }
```

This matches `AppShell.tsx`'s actual DOM (the `<aside>` sidebar, and the
utility-bar wrapper as `main`'s first child) as read this session. **Proper fix**:
add `print:hidden` directly on the sidebar `<aside>` and the utility-bar wrapper
`<div>` in `AppShell.tsx`, and drop the `<style>` shim here once that lands.

## 3. Types/fetchers deviation from the house pattern

The house pattern keeps wire types in `src/api/types.ts` and fetch functions in
`src/api/endpoints.ts`. Neither file had the messaging-threads or reports contract
on disk while this slice was built (no `backend/app/api/messages.py`,
`reports.py`, or plain `GET /properties` existed yet — the messaging/reports
backend is being built concurrently by another agent in this same tree). Both
files are also actively being edited by others right now, so rather than collide,
this slice defined its own types and called `request()`/`fetch()` directly inside
`use-messaging.ts` and `use-reports.ts` (the existing `use-unread-count.ts` already
does the same thing for `/api/v1/messages/unread-count`, so this isn't a new
pattern in this app). **Once the backend contract is confirmed**, these types/fetch
calls should be hoisted into `api/types.ts` / `api/endpoints.ts` and this slice's
local copies deleted.

Note in particular: `use-messaging.ts` does **not** import `Message` /
`CaseMessagesResponse` from `api/types.ts` — that's the *old* read-only per-case
thread shape (no `channel`, no `delivery_state`) still used by `MessagesPanel.tsx`
on the ticket detail page's Messages tab. Importing it here would have typechecked
while being silently wrong.

## 4. Contract fields inferred rather than fixed by the brief

These weren't nailed down in the contract handed to this slice, so the client
degrades defensively — please confirm/correct so the generic handling can be
replaced with precise typing:

- **`GET /messages/threads` list envelope**: assumed `{ items: [...] }`, falls back
  to `{ threads: [...] }`.
- **`GET /messages/threads/{case_id}` envelope**: assumed `{ items: [...] }`
  (oldest-first), falls back to `{ messages: [...] }`.
- **Attachment shape**: `attachments[]` item shape wasn't specified. Handled as
  either a bare document-id string or `{ id, name?, filename? }`
  (`normalizeAttachment()` in `use-messaging.ts`). No attachment-*upload* UI was
  built in the composer — no upload endpoint was given, so the composer only
  posts `text`+`channel` (never `attachments`) for now. Existing attachments on
  received messages render as read-only "open in new tab" links via
  `GET /api/v1/documents/{id}/content` (fetched with `authHeader()`, since a plain
  `<a href>` can't carry HTTP Basic — same reasoning the task brief gave for the
  CSV export).
- **`sender_type`**: contract doesn't fix an enum (unlike the old `Message` type's
  `TENANT|CONTRACTOR|OPERATOR`). Rendered generically via `titleCase()`, with a
  color mapping that only recognizes those three values and falls back to blue for
  anything else.
- **`POST .../read` / `.../unread` response bodies**: not relied on — the UI just
  invalidates the thread, thread-list and `["messages-unread-count"]` query keys
  and lets the next fetch be the source of truth.
- **`GET /api/v1/properties?limit=200` item shape**: assumed
  `{ items: [{ id | property_id, address_line | address, ... }] }`.
- **Reports section row/column names**: the brief fixes the four section names
  (maintenance/spend/resolution/recurring-issues) and says each carries
  totals + row-level detail, but not field names inside either. `use-reports.ts`'s
  `coerceSection()` accepts `{ totals, rows }` or a flat object of numeric
  totals + `rows`/`items`, and `reports.index.tsx` renders whatever columns are
  present on the first row (humanized via `titleCase`), with pence/date/boolean
  heuristics on cell values. This is intentionally generic rather than guessing a
  schema that might silently diverge from the real one — once the real response
  shape is confirmed, `SectionPanel` in `reports.index.tsx` should get real typed
  columns instead.
- **`category` filter**: contract names the param but not its values. Assumed to
  be the existing `Trade` enum (`ROOFING/SCAFFOLDING/PLUMBING/ELECTRICAL/OTHER`
  from `api/types.ts`), since that's the only trade/category-shaped taxonomy
  already in this app. Please confirm.
- **CSV filename**: prefers a `Content-Disposition` filename from the response if
  present, else builds `repairflow-report_<date_from|all-time>_to_<date_to|now>.csv`
  client-side.

## 5. Duplication note (not a request, just visible in the diff)

`messages.$caseId.tsx` imports `ThreadFilterBar`/`ThreadListBody` from
`messages.index.tsx` rather than duplicating the list-pane markup, since both
files are owned by this slice. If a shared `components/fixi/` file becomes
available to this slice later, those two could move there instead.

---

## From `frontend-fixi/src/routes/NEEDS_FROM_ROOT_properties.md`


Written by the agent that owns `properties.index.tsx`,
`properties.$propertyId.{index,history,details,documents,notes}.tsx`,
`components/fixi/PropertyTabs.tsx` and `hooks/use-property.ts`.

## Route tree regeneration

New route files added this session (need `routeTree.gen.ts` regenerated):

- `properties.$propertyId.index.tsx` -- redirects to the history tab
- `properties.$propertyId.details.tsx`
- `properties.$propertyId.documents.tsx`
- `properties.$propertyId.notes.tsx`

Until that regeneration happens, `npx tsc --noEmit` reports "not assignable"
errors on every `<Link to="/properties/$propertyId/...">`/`createFileRoute`
call touching these four paths, in both the new route files and in
`PropertyTabs.tsx`. Expected and self-resolving once regenerated -- see the
task brief's note on this.

## `/tenants/$tenantId` doesn't exist yet

`properties.$propertyId.details.tsx` links each tenant to
`/tenants/$tenantId` (`Link to="/tenants/$tenantId" params={{tenantId}}`) per
the task brief ("Show the related tenants with links to
`/tenants/$tenantId`"). No `tenants.$tenantId.tsx` route file exists in this
tree as of this session. If no other agent adds one, this Link won't
typecheck even after `routeTree.gen.ts` is regenerated, and will 404 at
runtime. `AppShell.tsx`'s sidebar nav already references a bare `/tenants`
with the same gap, so this isn't a new problem -- just flagging the second
half of it.

## api/types.ts + api/endpoints.ts don't model properties/notes/documents

The properties/notes/documents backend routes
(`backend/app/api/*.py` -- properties list/detail/create/update, notes
CRUD, documents upload/list/content/delete) don't exist in this repo as of
this session; another agent is adding them in parallel. Rather than editing
`src/api/types.ts` / `src/api/endpoints.ts` (already modified by that other
agent per git status, so editing them risked a conflict), all of this
feature's types and fetch functions were kept local to
`src/hooks/use-property.ts`, built directly on `request`/`authHeader`/
`BASE_URL`/`ApiError` from `src/api/client.ts`. Types defined there:
`PropertyListItem`, `PropertyDetail`, `PropertyTenant`,
`CreatePropertyRequest`, `UpdatePropertyRequest`, `NoteItem`, `NotesResponse`,
`DocumentItem`, `DocumentsResponse`, `RoofResponsibility`.

Worth folding into `api/types.ts`/`api/endpoints.ts` once both sides have
landed, for consistency with the rest of the app -- not done here to avoid
touching files outside this agent's ownership.

## Contract assumptions made without a live backend to check against

The properties/notes/documents backend routes didn't exist to test against,
so these were implemented to the letter of the task brief's contract. Please
verify once the backend lands:

- `POST /api/v1/properties` body: `{address_line, postcode, landlord_reference,
  property_type, bedrooms, build_year, access_notes, photo_key}`. No
  `roof_responsibility`/`timezone` sent on create (left to the backend's
  documented defaults -- `RoofResponsibility.UNKNOWN`, `"Europe/London"`,
  per `backend/app/models.py PropertyModel`).
- `PATCH /api/v1/properties/{id}` body: same shape plus optional
  `roof_responsibility`/`timezone`, all fields optional (partial update).
- `POST /api/v1/notes` body: `{subject_type, subject_id, body}` -- no
  `author` field sent; assumed the backend derives it from the
  authenticated operator (`backend/app/models.py NoteModel.author`), since
  the task brief's contract for the POST body doesn't list it and there's
  no operator-identity field elsewhere in this frontend beyond the Basic
  Auth username.
- `POST /api/v1/documents` multipart fields: `subject_type`, `subject_id`,
  `description` (omitted when empty), `file`.
- A 409 from `PATCH /api/v1/properties/{id}` is read as "archival record,
  edit refused" and shown as a toast + the Details tab's disabled-Edit
  state; if the real 409 body carries a different reason, the toast text
  in `hooks/use-property.ts`'s `useUpdateProperty` should be updated to
  surface it instead of the current fixed message.
- `is_archived` is assumed to mean "created from the synthetic archive
  import" (`PropertyModel.archive_batch_id is not None`, per
  `backend/app/models.py`'s comment on that column) -- this drives the
  "Sample history" pill and the disabled-edit state throughout.

## Drill-down totals note (not a mismatch, just a heads-up)

`GET /properties/{id}/stats`'s `quoted_by_trade` sums every work order's
`quote_pence` by trade (a case with two trades' worth of work orders
contributes to two segments), while `GET /properties/{id}/history`'s
per-row `trade` is a case's single *primary* trade
(`backend/app/domain/services.py _pick_primary_trade`). So a donut-trade
drill-down's row selection will not always sum back to that segment's own
£ figure -- by design, not a bug. The history tab's totals line above the
table is therefore computed only from the filtered rows themselves ("Showing
N of M cases · £X quoted on these"), never asserted equal to the chart's own
total. `quoted_by_year` happens to use the same case-level bucketing as the
table's per-row `created_at` year, so that drill-down does reconcile exactly
in practice.

---

## From `frontend-fixi/src/routes/NEEDS_FROM_ROOT_ticket.md`


Filed by the agent that built `CaseProgress`, `CaseToolbar`, `DocumentsPanel`,
`CostsPanel`, `RescheduleDialog` and wired them into
`maintenance.tickets.$ticketId.{-$section}.tsx`.

## 1. Three routes don't exist yet in this checkout

`/tenants/$tenantId`, `/contractors/$contractorId` and `/messages/$caseId`
are not in `src/routes/` (confirmed via `Glob src/routes/*.tsx` before
starting) and so aren't in `routeTree.gen.ts`. TanStack's `<Link to=>` is
type-checked against that tree, so a typed `Link` to any of these three
fails `tsc` until the routes land and the tree is regenerated.

**What I did instead:** every place that needs to reach one of these three
uses a plain `<a href="...">` (full navigation, not client-side), not a
typed `<Link>`. Exact locations:

- `frontend-fixi/src/routes/maintenance.tickets.$ticketId.{-$section}.tsx`
  — `ProfileLinkButton` component, used for the tenant's "View profile"
  (`/tenants/${tenant.id}`) and the assigned contractor's "View profile"
  (`/contractors/${assigned_contractor.id}`) in `SummaryColumn`.
- `frontend-fixi/src/components/fixi/CaseToolbar.tsx` — the kebab menu's
  "Open conversation" item (`/messages/${snapshot.case.id}`).

**Please convert these three to typed `<Link to="..." params={{...}}>`**
once the corresponding route files exist and the tree is regenerated —
search this checkout for `ProfileLinkButton` and
`href={`/messages/${` to find every call site. No other logic needs to
change; it's a mechanical swap from `<a href>` to `<Link to>`.

## 2. `RepairCase` (api/types.ts) has no `category` field, but it's editable

`backend/app/schemas.py`'s `RepairCase` (the object embedded in
`CaseSnapshot.case`) does not serialize `category` at all — only
`CaseListItem` (a different response, from `GET /cases`) carries it, and
`PATCH /cases/{id}` (`CaseEditRequest.category`) can still write it.

Practical effect: `CaseToolbar.tsx`'s Edit dialog cannot show what the
case's current category actually is, because the snapshot never told it.
Rather than fabricate a default or blindly overwrite an unseen value on
every save, the category field in that dialog defaults to an explicit
"Leave unchanged (current value isn't shown here)" option and is only
included in the `PATCH` body if the operator actively picks something
else.

**Recommended real fix** (not done here — `backend/app/schemas.py` and
`frontend-fixi/src/api/types.ts` are both outside this agent's ownership
for this phase): add `category: Trade | None` to the backend `RepairCase`
Pydantic model (it already exists as a column on `RepairCaseModel`, and
`CaseListItem` already proves the serialization is cheap), then add
`category: Trade | null` to `RepairCase` in `api/types.ts`. Once that
lands, `CaseToolbar.tsx`'s `EditCaseDialog` can pre-fill the real value
instead of the "leave unchanged" placeholder — see the comment directly
above `EditCaseDialog` in that file.

## 3. Evidence-photo rendering has nothing to render on current data

`DocumentsPanel.tsx`'s "Reported evidence" section (from
`snapshot.issue.evidence_refs`) is built and wired correctly, but on every
case in this codebase today `evidence_refs` is populated only with
`SourceType.VOICE_TOOL` entries whose `locator` is spoken text (see
`backend/app/domain/services.py`'s `evidence_ref_dict` call sites), never
an image URL/path. So the image grid renders zero items right now — that's
the honest, correct output of the filter (`isImageLocator` in
`DocumentsPanel.tsx`), not a bug. If/when a future producer attaches a
real photo locator to an evidence ref, no code change is needed here for
it to appear, correctly labelled "Illustrative sample" whenever
`provenance !== "LIVE"`.

---

## From `backend/app/archive/NEEDS_FROM_ROOT.md`


## Resolved: `TenantModel` / `ContractorModel` now carry `archive_batch_id`

Originally flagged that `ActionRecordModel`, `TenantModel`, `RepairIssueModel`
and `WorkOrderModel` had neither `provenance` nor `archive_batch_id`, which
conflicts with CLAUDE.md's hard rule 2 read literally ("a row with neither
must not be written") given the dataset shape requires all four.

The root agent added `archive_batch_id` to `TenantModel` and `ContractorModel`
(same nullable-FK-to-`archive_batches` shape as `PropertyModel`'s). `importer.py`
now sets it on every tenant/contractor it writes, and `remove_archive()`
deletes both by a plain `archive_batch_id ==` filter -- no more traversal or
deterministic-id-regeneration for these two.

**Still open by design, not by oversight**: `RepairIssueModel`, `WorkOrderModel`
and `AppointmentModel`/`ActionRecordModel` still have neither column. Root's
call: the FK chain back to `RepairCaseModel.archive_batch_id` (via `case_id`)
makes the traversal exact for these, so no schema change is planned there.
`importer.py` and `remove_archive()` still scope those four tables that way --
`WHERE case_id IN (SELECT id FROM repair_cases WHERE archive_batch_id = :batch)`
-- never a bare delete. `validate()`'s `referential_integrity` check
(`PRAGMA foreign_key_check`) and the removal test both confirm this leaves
zero orphans.

No HTTP/API surface for the archive is planned this session; CLI-only
(`python -m app.archive`) is correct and final for this task.
