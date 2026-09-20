# Follow-up work queue

Actionable items, highest priority first. The full honest inventory of
what is not done lives in `docs/UI2_IMPLEMENTATION_HANDOFF.md` §7 — this
file is the subset somebody has decided to actually do, with enough
detail to start without re-investigating.

Status: `TODO` · `IN PROGRESS` · `DONE`

---

## 1. Category donut renders a meaningless 100% wedge — `TODO`

**Symptom.** On `backend/data/repairflow.db` (14 real cases, none
categorised) the Insights category donut shows a single unlabelled
segment: `{category: null, count: 10, percentage: 100}`. The legend row
reads blank, and its colour dot has no class at all.

**Where it goes wrong — the frontend, not the API.** The backend is
behaving as designed and documents why: `analytics.category_breakdown`
deliberately keeps `category=None` as its own group so the percentages
describe the whole matched case set rather than a silently-filtered
subset. That is the right call. The bug is that the UI casts the null
straight to a `Trade`:

- `frontend-fixi/src/hooks/use-analytics.ts` — `trade: row.category as Trade`
  (two places: `category_breakdown` and `recurring_issues`). A lying cast;
  the value really is nullable.
- `frontend-fixi/src/components/fixi/Charts.tsx` — `titleCase(d.trade)`
  on null yields an empty label, and `TRADE_DOT_CLASS[TRADE_TONE[d.trade]]`
  is `undefined`, so the legend dot renders unstyled.

**Fix.**
1. Type it honestly: `trade: Trade | null` in `CategoryBreakdownItem`.
2. In `Charts.tsx`, render a null category as **"Uncategorised"** in the
   gray tone — it is a real and useful fact that N cases have not been
   triaged, so it should be legible, not hidden.
3. When the **only** group is the null one, show the existing empty state
   ("No categorised cases in the selected range") instead of a 100% wedge.
   A donut of one slice conveys nothing.

**Note on `recurring_issues`:** `analytics.recurring_issues` already
excludes `category IS NULL` explicitly — "recurring category is
meaningless without one" — so that one is correct and needs no change.
The same lying cast is present in the hook and should still be removed.

**Verify.** With no categories set, Insights must show the empty state.
With a mix, "Uncategorised" appears as a normal labelled segment and the
percentages still sum to exactly 100.

---

## 2. Backfill `repair_cases.category` from work-order trade — `TODO`

**Why.** `category` is a new column and is NULL on all 14 existing cases,
which is what empties the donut and the recurrence grouping. Every one of
those cases already has work orders carrying a real `Trade`.

**Decision taken (2026-09-20):** derive the backfill from work-order
trade. Confirmed by the repository owner.

**Rule to implement.** For each case where `category IS NULL`:
- exactly one distinct work-order trade → set `category` to it;
- several distinct trades → use the trade of the work order with
  `required_for_resolution = true`, falling back to the **earliest**
  work order by `created_at`. A case's category is meant to be what the
  issue *is*, and the first-raised required work order is the closest
  honest proxy for that;
- no work orders at all → **leave NULL.** There is nothing to derive it
  from, and guessing would put a fabricated classification into every
  count, donut segment and recurrence group that reads this column.

**Shape.** A one-shot, idempotent, additive command —
`python -m app.backfill_category --dry-run | --apply` — alongside
`app.legacy_demo_purge`, not a migration step. It must never overwrite a
`category` that is already set, and must print what it changed.

**Watch out for:** `RepairCaseModel.category` is a `Trade` enum column
and the derivation reads `WorkOrderModel.trade`, also a `Trade` — no
mapping table needed. Do not touch archival cases: the archive sets its
own categories deliberately, and rewriting them would desynchronise the
dataset from its own validation checks.

**Verify.** On a *copy* of `backend/data/repairflow.db` (never the
original — see the handoff): `--dry-run` reports the intended change per
case; after `--apply`, the Insights donut shows real trade segments, the
recurrence grouping produces at least one group, and re-running reports
zero changes.

---

## Not queued — needs a decision first

**Insights and Reports spend read `cost_entries`; property stats read
`work_orders.quote_pence`.** Two different money sources that disagree on
the same property (£200.00 on one screen, £0.00 on the other), which also
contradicts the handoff's claim that `analytics.py` is the single source
of every metric. Making Insights fall back to work-order quotes would
surface existing data but double-count as soon as real cost entries are
recorded — unless the fallback is per-case rather than global. Left open
deliberately: this is a definition question, not a bug to patch.
