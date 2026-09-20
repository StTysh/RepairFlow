# Needs from root -- directory API (properties/contractors/tenants)

## Wiring

`main.py` already imports and registers `properties`, `contractors` and
`tenants` routers (lines 24, 14, 27 and 101-103 at time of writing) --
nothing further needed there. Confirmed by running the app import; no
action required on your side unless those lines get removed.

## Schema gap: ContractorModel has no `archive_batch_id`

`PropertyModel` and `RepairCaseModel` both carry a nullable indexed FK
`archive_batch_id -> archive_batches.id` (see models.py) so archival rows
can be identified and excluded per CLAUDE.md's "CRITICAL DOMAIN RULE".
`TenantModel` does not have this column either, but a tenant's
archival-ness can be honestly derived one FK hop away, through
`TenantModel.property_id -> PropertyModel.archive_batch_id` -- that's
what `app/api/tenants.py` does.

`ContractorModel` has no equivalent derivation available: a contractor
isn't scoped to one property, and its work orders can span both
archival and real cases, so there is no honest signal today for whether
a given contractor row is archive-import sample data versus a real
directory entry. Per the task brief's instruction to record gaps here
rather than invent a heuristic:

- `app/api/contractors.py`'s `is_archived` field is currently
  hard-coded `False` on every contractor row.
- The `PATCH /contractors/{id}` "refuse edits to archival contractors"
  requirement is consequently unimplementable and not attempted.

**Proposed fix** (mirrors the existing `PropertyModel` pattern exactly):

```python
archive_batch_id: Mapped[str | None] = mapped_column(
    sa.ForeignKey("archive_batches.id"), nullable=True, index=True
)
```

added to `ContractorModel` in `models.py`, set by whatever process
creates archive-import contractor rows. Once that column exists,
`contractors.py`'s `is_archived` can read it directly and the PATCH
refusal can be added the same way `properties.py` and `tenants.py`
already do it.

## Endpoints implemented (for reference)

- `GET/POST /api/v1/properties`, `GET/PATCH /api/v1/properties/{id}`
- `GET/POST /api/v1/contractors`, `GET/PATCH /api/v1/contractors/{id}`
- `GET/POST /api/v1/tenants`, `GET/PATCH /api/v1/tenants/{id}`

`GET /api/v1/properties/{id}/history` and `.../stats` were left alone --
those stay owned by `app/api/cases.py` per the task brief.
