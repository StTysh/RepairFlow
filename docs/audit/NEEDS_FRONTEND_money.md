# Needs from frontend — quoted-money reconciliation

Written while implementing the fix for `docs/audit/06_analytics_metrics.md`
Finding 1 / `docs/audit/11_data_quality.md` Finding 3 (two unreconciled
sources for "quoted" money) from the backend side only. Per this task's
instructions, `frontend-fixi/` was not touched. Everything in this file is
either informational (no frontend change required, numbers just changed) or
a genuine frontend follow-up.

## What changed, and what the frontend does NOT need to do

`GET /properties/{id}/history` and `/stats` (`PropertyHistoryItem.
quoted_pence`, `PropertyStatsResponse.quoted_by_trade`/`quoted_by_year`) and
`GET /cases/{id}/costs` (`CostTotals.quoted_pence`/`committed_pence`) all
keep their **exact existing response shape** — no field added, removed or
renamed. Only the numeric values changed, in one direction only: a figure
that used to read `0` (or a lower figure) because no `CostEntryModel` had
ever been logged against a work order now reads that work order's real
`quote_pence`-derived figure instead. No existing frontend code should need
to change to pick this up; it should simply start showing correct, non-zero
totals for operational cases that were previously showing `0p` on Property
Stats/History despite having priced work orders, and the Costs tab total
will now agree with those totals instead of reading `0p` while the property
page read something else. If any frontend test/story hardcodes the old
`0p`/mismatched values for a fixture case with work orders but no cost
entries, that fixture's expected number needs updating — not a code change,
a fixture-data change.

## Genuine follow-up: an explicit "estimated" indicator would be more honest

`app.analytics.reconciled_quotes()` (backend) tracks, per contribution,
whether a quoted figure came from a real `CostEntryModel` ledger row
(`from_cost_entry=True`) or is a live fallback to the work order's own
`quote_pence` because nobody has logged a cost entry yet
(`from_cost_entry=False`). None of the response schemas currently expose
this distinction — `PropertyHistoryItem.quoted_pence`,
`TradeQuoteBreakdown.quoted_pence`, `CaseDetailRow.quoted_pence`, and
`CostTotals.quoted_pence`/`committed_pence` are plain integers with no
"how sure are we" flag. This is not a correctness bug (the number itself is
right, and CLAUDE.md's provenance rules are about outbound commitments and
physical activity, not an internal accounting distinction), but a
"Quoted (estimated)" vs "Quoted (logged)" visual distinction on Property
History/Stats and the Costs tab would be a genuine improvement and is a
reasonable next backend+frontend pairing: extend the relevant response
schemas with a boolean/enum sourced from `from_cost_entry`, then have the
frontend render it. Not built this pass — flagging it rather than silently
leaving the distinction invisible.

## Dead code the frontend should not call

`app/domain/services.py`'s `load_property_history`/`load_property_stats`
still exist (that file was out of scope for this fix — owned by another
agent this session) and still compute "quoted" purely from
`WorkOrderModel.quote_pence`, with no reconciliation against
`CostEntryModel`. Nothing calls them any more — `app/api/cases.py`'s
`/properties/{id}/history` and `/stats` now call
`app.analytics.property_history_items`/`property_stats` instead — but they
are not deleted (deleting them means editing `domain/services.py`, which
was out of scope here). If a future frontend or backend change is tempted
to import them directly for any reason, don't: they will silently
reintroduce the exact disagreement this fix removed.
