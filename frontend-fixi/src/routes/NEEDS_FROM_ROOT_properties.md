# Needs from the root agent -- properties feature

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
