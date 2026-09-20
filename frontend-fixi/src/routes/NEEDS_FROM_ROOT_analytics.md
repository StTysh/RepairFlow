# Needs from root / other agents — Overview + Insights

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
