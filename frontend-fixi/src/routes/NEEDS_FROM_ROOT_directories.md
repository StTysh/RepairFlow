# Needs from root — Contractors / Tenants directories

Written by the agent building `contractors.index.tsx`, `contractors.$contractorId.tsx`,
`tenants.index.tsx`, `tenants.$tenantId.tsx`, `hooks/use-directory.ts` and
`components/fixi/DirectoryForms.tsx`. Nothing outside that list was touched.

## Route tree

These four routes aren't in `routeTree.gen.ts` yet, so `createFileRoute("/contractors/")`
etc. (and any `<Link to="/contractors">` / `to="/tenants/$tenantId"` elsewhere, e.g. the nav
array already added to `AppShell.tsx`) show a TS "not a valid route" error until it's
regenerated. Please regenerate once the contractors/tenants API routes land.

## `/messages` link from the tenant profile

`tenants.$tenantId.tsx` renders a "Messages" link to `/messages` (only shown when the tenant
has at least one case — there's no way from `GET /tenants/{id}` to know whether any of those
cases actually has a message thread, so "has cases" is the closest honest proxy). It passes
`search={{ tenantId: t.id }}` as a guess at the filter param name. `/messages` doesn't exist
as a route file yet in this app and there's no documented query-param contract for filtering
it by tenant — whoever builds that route should confirm/rename the param (or tell me and I'll
fix the call site). Until then this is cast `as never` to keep it compiling.

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
