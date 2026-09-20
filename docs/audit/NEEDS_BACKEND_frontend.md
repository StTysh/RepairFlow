# Needs from backend — frontend data-layer bug fixes

Written while fixing the mismatches in `docs/audit/07_frontend_data_layer.md`
from the frontend side only (`frontend-fixi/src/hooks|routes|components`).
Everything in this file requires a backend change; nothing here was papered
over with a defensive frontend fallback.

## Property detail: tenant contact fields (Finding 2, CRITICAL)

`GET /api/v1/properties/{id}` nests each tenant as `properties.py`'s
`TenantSummary{id, display_name, contact_allowed}` — no `phone_e164`/`email`.
The frontend page that rendered this card (`properties.$propertyId.details.tsx`)
was permanently showing "No contact on file" for every tenant, including
ones with real contact details on file, because it read fields
(`phone_e164`/`email`) that this endpoint never sends.

**Frontend fix applied this pass:** `PropertyTenant` (`use-property.ts`) now
matches `TenantSummary` exactly (`id`, `display_name`, `contact_allowed`),
and the property detail page renders a `contact_allowed` Pill plus a link to
the tenant's own profile (which does have real `phone_e164`/`email` via
`GET /api/v1/tenants/{id}`) instead of fabricating contact info this
endpoint doesn't carry. This stops the false "No contact on file" claim but
is a strictly smaller card than the original design intent (phone/email
visible right on the property page without an extra click).

**What backend could do to restore the original design:** extend
`TenantSummary` in `backend/app/api/properties.py` with `phone_e164: str |
None` and `email: str | None` — `TenantModel` already has both fields, and
`_property_detail` already loads the tenant row, so this is a low-risk,
additive change (two nullable fields on an existing internal DTO). If that
lands, the frontend card should go back to showing phone/email directly
instead of routing through the tenant profile link.
