# Requests for the root agent

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
