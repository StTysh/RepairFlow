# Frontend Data Layer Audit — does `frontend-fixi`'s idea of the API match the API?

Scope: `frontend-fixi/src/api/` (client, endpoints, types) and every `frontend-fixi/src/hooks/*` fetcher, checked field-by-field against the live response models in `backend/app/api/*.py` and `backend/app/schemas.py`. Read-only; no server started; no source edited except this file.

Context: the two sides were built in parallel against a written contract and have already drifted in shipped-bug ways. Three were known going in (Insights `month`/`resolution_time_distribution`/`comparison`, tenant-profile `updated_at`, stale `PropertyListItem`) — the first and third are now fixed on disk (verified below); the tenant one is not. Five more of the same mechanical kind were found this pass, two of them worse than any of the originals (a landing-page crash, and a permanently-wrong "no contact on file").

## Severity counts
CRITICAL: 3 · HIGH: 4 · MEDIUM: 4 · LOW: 3 · NIT: 2

Field mismatches found (name/shape, not counting the ones already fixed): **9** distinct backend-field ↔ frontend-field disagreements across 6 endpoints.

---

## Field × field diff table

Legend: ✅ match · ⚠️ unused-but-present (harmless) · ❌ mismatch (bug)

### `GET /api/v1/overview` → `use-analytics.ts` `useOverview` (Finding 1, CRITICAL)

| Backend field (`overview.py`) | Frontend field (`use-analytics.ts`) | Verdict |
|---|---|---|
| `property_count: int` | `property_count?: number` | ✅ |
| `tenant_count: int` | `tenant_count?: number` | ✅ |
| `approved_contractor_count: int` | `approved_contractor_count?: number` | ✅ |
| `status_counts: {active, awaiting_confirmation, resolved, escalated, cancelled, total}` | `case_counts_by_status?: Partial<Record<CaseStatus,number>>` (expects `ACTIVE`/`AWAITING_CONFIRMATION`/... keys) | ❌ never present, and even if it were, wrong casing/nesting |
| *(no such field)* | `open_case_count?: number` | ❌ backend never sends this key |
| `open_age_buckets: [{label, count}]` | *(no field at all)* | ❌ dropped entirely, nothing reads it |
| `needs_attention[].case_id/case_number/case_title/reason/detail/occurred_at` | `needs_attention[].id/kind/case_id/case_number/case_title/message/occurred_at` | ❌ `id`, `kind`, `message` don't exist on the backend row (`reason`/`detail` do, unused) |
| `upcoming_appointments[].appointment_id/case_id/case_number/case_title/property_address/contractor_id/contractor_name/start_at/end_at` | `OverviewAppointmentItem` same names minus `contractor_id` | ✅ this section is correct |
| `recent_activity[].event_id/case_id/case_number/case_title/event_type/occurred_at` | `OverviewActivityItem.id/case_id/case_number/case_title/type/display_title/display_description/occurred_at` | ❌ `id` (backend: `event_id`), `display_title`/`display_description` (backend has neither, only `event_type`) |

### `GET /api/v1/insights` → `use-analytics.ts` `useInsights` — **already fixed** on disk

`normalizeInsights` correctly translates `year`+`month` → `"YYYY-MM"`, `category`→`trade` (nullable, no longer cast unsafely), `resolution.buckets[].label`→`bucket`, `case_volume_comparison.change_pct`→`pct_change`. Verified against `backend/app/api/insights.py`'s `InsightsResponse` field-for-field: all match after normalization. `spend_by_year` passes through unnormalized and does match (`year`, `quoted_pence`, `actual_pence` on both sides). No remaining mismatch here.

### `GET /api/v1/insights/cases` → `use-analytics.ts` `useInsightsCases` — matches

`RawInsightsCaseRow` (`case_id`→`id`, `category`→`trade`, `closed_at`→`resolved_at`) matches `CaseDetailRowResponse` in `insights.py` field-for-field. No mismatch.

### `GET /api/v1/tenants/{id}` → `use-directory.ts` `getTenant`/`normalizeTenantProfile` (Finding 2, HIGH — the originally-reported bug, still live)

| Backend `TenantCaseSummary` (`tenants.py:50-56`) | Frontend `TenantCaseItem` (`use-directory.ts:348-354,399`) | Verdict |
|---|---|---|
| `id`, `case_number`, `title`, `status`, **`created_at`**, `is_archived` | `id`, `case_number`, `title`, `status`, **`updated_at`** | ❌ backend never sends `updated_at`; frontend never reads `created_at` |

### `GET /api/v1/properties/{id}` → `use-property.ts` `fetchProperty` (Finding 3, CRITICAL)

| Backend `TenantSummary` (`properties.py:46-49`) | Frontend `PropertyTenant` (`use-property.ts:85-90`) | Verdict |
|---|---|---|
| `id`, `display_name`, `contact_allowed` | `id`, `display_name`, `phone_e164`, `email` | ❌ backend never sends `phone_e164`/`email` on this projection; frontend never reads `contact_allowed` |

Everything else on `PropertyListItem`/`PropertyDetail` matches exactly (this is the "stale `PropertyListItem`" bug, already fixed — `id, address_line, postcode, landlord_reference, property_type, bedrooms, build_year, photo_key, timezone, roof_responsibility, access_notes, is_archived, open_case_count, total_case_count, tenant_count` line up 1:1 with `properties.py`'s `PropertyListItem`).

### `GET /api/v1/contractors/{id}` → `use-directory.ts` `getContractor`/`normalizeWorkHistoryItem` (Finding 4, CRITICAL)

| Backend `ContractorWorkHistoryItem` (`contractors.py:69-79`) | Frontend `ContractorWorkHistoryItem` (`use-directory.ts:110-121,146-160`) | Verdict |
|---|---|---|
| **`id`** (the work order id) | reads `r["work_order_id"]` | ❌ key doesn't exist → always `""` |
| `case_id`, `case_number`, `case_title`, `trade`, `status`, `scope`, `quote_pence`, `created_at` | same names | ✅ |
| **`case_is_archived`** | reads `r["is_archived"]` | ❌ key doesn't exist → always `false` |

### `POST /api/v1/messages/threads/{case_id}` (compose) & thread reads → `use-messaging.ts` (Finding 5, HIGH; Finding 6, MEDIUM)

| Backend `ThreadListItem` (`messaging.py:67-78`) | Frontend `ThreadListItem` (`use-messaging.ts:28-40`) | Verdict |
|---|---|---|
| **`last_message_sender_type`** | `last_sender` | ❌ key doesn't exist → always `undefined` |
| everything else (`case_id`, `case_number`, `case_title`, `property_address`, `tenant_name`, `last_message_preview`, `last_message_at`, `unread_count`, `total_count`, `is_archived`) | same | ✅ |

| Backend attachment dict (`messaging.py:259-261`) | Frontend `MessageAttachment`/`normalizeAttachment` (`use-messaging.ts:51-52,84-88`) | Verdict |
|---|---|---|
| `{"document_id": ..., "display_name": ..., "content_type": ...}` | expects `{id, name?, filename?}` | ❌ every key differs → `normalizeAttachment(a).id` is always `undefined` |

`MessageRecord`'s other fields (`id, sender_type, sender_name, text, channel, delivery_state, delivery_detail, attachments, read_at, communication_id, photo_url`) all match `ThreadMessage` on the frontend.

### `GET /api/v1/cases` (list) → `api/endpoints.ts`/`api/types.ts` `CaseListItem` (Finding 7, LOW)

| Backend `CaseListItem` (`schemas.py:1190-1207`) | Frontend `CaseListItem` (`types.ts:21-31`) | Verdict |
|---|---|---|
| `id, case_number, title, status, version, updated_at, property_address, urgency, assigned_contractor_name` | same | ✅ |
| `category: Trade \| None` | *(field absent from the type)* | ⚠️ not currently rendered anywhere in `maintenance.index.tsx` |
| `is_archived: bool` | *(field absent from the type)* | ⚠️ see Finding 7 below — currently inert only because `fetchCaseList` never passes `include_archived=true` |

### Everything else checked and matching cleanly

`GET /api/v1/cases/{id}` (`CaseSnapshot`), `GET /api/v1/metrics/dashboard` (`DashboardMetricsResponse`), `GET /api/v1/notifications`, `GET /api/v1/appointments/upcoming`, `GET/POST/PATCH /api/v1/costs*`, `GET/POST/PATCH/DELETE /api/v1/documents*`, `GET/POST/PATCH/DELETE /api/v1/notes*`, `GET /api/v1/reports/summary` (the generic `section()` adapter's key guesses — `category_breakdown`, `by_year`, `buckets`, `groups`, `rows` — all happen to be exactly right against `reports.py`), `POST /api/v1/cases` (`IntakeResponse`), `POST /api/v1/cases/{id}/field-updates` (all three `FieldUpdate` variants), `POST /api/v1/actions/{id}/approval`, `POST /api/v1/appointments/{id}/cancel`, `ContractorListItem`/`TenantListItem` top-level list rows.

---

## Findings

### 1. CRITICAL — Overview ("/") is one field-name mismatch away from a hard crash, and most of it silently shows nothing
`frontend-fixi/src/hooks/use-analytics.ts:66-79` (`OverviewResponse`) vs. `backend/app/api/overview.py:68-76` (the real `OverviewResponse`). `frontend-fixi/src/routes/index.tsx:45,171,182,193`.

The file's own header comment says this was "written against the contract... not a verified `openapi.json`" and every field was made optional so a drift "shows up as a dash... instead of a crashed screen." That defense mostly works — except for `needs_attention[].kind`. `index.tsx:45-61` builds three `Record<NeedsAttentionKind, ...>` lookup tables (`NEEDS_ATTENTION_ICON`, `_TONE_CLASS`, `_LABEL`) and indexes them at `index.tsx:171`: `const Icon = NEEDS_ATTENTION_ICON[item.kind]`. The backend (`overview.py:24-30`) never sends `kind` — it sends `reason`/`detail` instead — so `item.kind` is `undefined`, `NEEDS_ATTENTION_ICON[undefined]` is `undefined`, and `<Icon className="h-4 w-4" />` at `index.tsx:185` renders `undefined` as a component. React throws ("Element type is invalid") and the route's `errorComponent` (`__root.tsx:115`) takes over the page. **This fires whenever `needs_attention` is non-empty** — i.e., whenever any case is awaiting approval, escalated, or has an overdue follow-up, which is normal operating state, not an edge case. This is the landing page.

Even when `needs_attention` is empty (so the crash doesn't fire), the rest of the page is substantially wrong:
- "Open cases" tile is permanently `"—"` (`index.tsx:80-86` looks for `open_case_count` or `case_counts_by_status.ACTIVE` — backend sends neither; the real count is at `status_counts.active`, different nesting *and* different casing).
- Recent Activity's second line (`index.tsx:366`, `event.display_title`) is permanently blank — backend sends `event_type`, not `display_title`/`display_description`.
- `open_age_buckets`, a whole payload the backend computes, is dropped on the floor — nothing in `OverviewResponse` even declares it.

Only "Upcoming appointments" and the three top metric tiles (`property_count`/`tenant_count`/`approved_contractor_count`) are actually correct.

**What the user sees:** loads `/`, and the instant there's an approval pending or an escalated case — the two things this card exists to surface — the page crashes to the app's generic error screen instead of showing them.

**Fix:** rewrite `OverviewResponse`/`NeedsAttentionItem`/`OverviewActivityItem` in `use-analytics.ts` against the actual `overview.py` shapes (`status_counts.{active,...}`, `needs_attention[].reason/detail`, `recent_activity[].event_id/event_type`), the same normalization treatment `useInsights` already got. Frontend side should change — `overview.py`'s shape is deliberate and covers strictly more ground (`open_age_buckets`) than the guessed contract.

---

### 2. CRITICAL — Property page permanently tells the operator every tenant has "No contact on file"
`backend/app/api/properties.py:46-49` (`TenantSummary`) vs. `frontend-fixi/src/hooks/use-property.ts:85-90` (`PropertyTenant`), consumed at `frontend-fixi/src/routes/properties.$propertyId.details.tsx:129-139`.

`GET /api/v1/properties/{id}` nests each tenant as `TenantSummary{id, display_name, contact_allowed}` — deliberately narrow, no contact fields. The frontend's `PropertyTenant` type declares `phone_e164`/`email` instead of `contact_allowed`, and the route renders:
```
{t.phone_e164 && <span>...{t.phone_e164}</span>}
{t.email && <span>...{t.email}</span>}
{!t.phone_e164 && !t.email && "No contact on file"}
```
Both fields are always `undefined`, so every tenant row on every property's detail page falls into the `"No contact on file"` branch — even for tenants who plainly have a phone/email on record in the Tenant directory itself (`GET /api/v1/tenants` does return `phone_e164`/`email`). This isn't a rare-field gap; it's the entire purpose of that card, always wrong.

**Fix:** `GET /api/v1/properties/{id}` needs a real answer here: either backend's `TenantSummary` grows `phone_e164`/`email` (cheap — `TenantModel` already has them; `_property_detail` already touched the tenant row), or the frontend switches this card to whatever endpoint the Tenant directory already uses. Preferred: extend `TenantSummary` — the property detail page is the natural place to show reachability, and adding two nullable fields to an existing internal DTO is low-risk. Frontend then just needs `contact_allowed` removed from being silently absent (add it to `PropertyTenant`, it's already computed and thrown away).

---

### 3. HIGH — Tenant profile's case list still reads `updated_at`; API sends `created_at` (originally-reported bug, unfixed)
`frontend-fixi/src/hooks/use-directory.ts:399` (`normalizeTenantProfile`) vs. `backend/app/api/tenants.py:50-56` (`TenantCaseSummary`). Consumed at `frontend-fixi/src/routes/tenants.$tenantId.tsx:218`.

`TenantCaseSummary` has `created_at`, not `updated_at`. `cr["updated_at"]` is always `undefined` → `asString` returns `null` → `formatRelative(null)` renders `"—"` for every case row on every tenant's profile page, permanently.

**Fix:** rename `TenantCaseItem.updated_at` → `created_at` in `use-directory.ts` (`TenantCaseItem` interface, `normalizeTenantProfile`'s per-case mapper) and update `tenants.$tenantId.tsx:218` to `cs.created_at`. Frontend-only fix — `created_at` is the honest field here (the backend model has no per-case `updated_at` at all).

---

### 4. HIGH — Contractor work-history rows: dead React keys, and archival/sample cases render as real, clickable tickets
`backend/app/api/contractors.py:69-79` (`ContractorWorkHistoryItem`) vs. `frontend-fixi/src/hooks/use-directory.ts:110-121,146-160` (`normalizeWorkHistoryItem`), consumed at `frontend-fixi/src/routes/contractors.$contractorId.tsx:189-214`.

Two field names are wrong at once:
- Backend sends the work order's id as `id`; frontend reads `r["work_order_id"]` (doesn't exist) → `work_order_id` normalizes to `""` for every row. `contractors.$contractorId.tsx:191` uses `key={w.work_order_id}` as the React list key, so **every row in a contractor's work history shares the same key** — React will warn and can reuse/misrender DOM across re-fetches (e.g. after approving a new job for that contractor, an old row's DOM can end up showing new data or vice versa).
- Backend sends `case_is_archived`; frontend reads `r["is_archived"]` (doesn't exist) → always `false`. `contractors.$contractorId.tsx:195` branches on `w.is_archived` to decide whether to render the row as inert "Sample history" text or as a live `<Link to="/maintenance/tickets/$ticketId">`. Since it's always `false`, **every archival/sample-import work-history row renders as a normal clickable link to a live ticket** — exactly the failure mode CLAUDE.md calls out by name ("a sample case is never mistaken for something to act on") and that `PropertyHistoryItem`/`CaseListItem`/`TenantCaseSummary` all correctly guard against elsewhere. Clicking it either 404s or (if the archival case_id happens to resolve) shows a synthetic sample case with no archival labelling on the ticket page itself.

**Fix:** two one-line renames in `normalizeWorkHistoryItem` (`use-directory.ts`): `r["work_order_id"]` → `r["id"]`, and `r["is_archived"]` → `r["case_is_archived"]` (interface field can keep its current external name, just fix the source key). Frontend-only fix.

---

### 5. HIGH — Message attachments are unopenable: `document_id`/`display_name` vs. `id`/`name`
`backend/app/api/messaging.py:259-261` (attachment payload written on compose) vs. `frontend-fixi/src/hooks/use-messaging.ts:51-52,84-88` (`MessageAttachment`/`normalizeAttachment`), consumed at `frontend-fixi/src/routes/messages.$caseId.tsx:283,309-320`.

Backend writes each attachment as `{"document_id": str(doc_id), "display_name": doc.display_name, "content_type": doc.content_type}`. Frontend's `normalizeAttachment` looks for `a.id`/`a.name`/`a.filename` — none of which exist on that object — so `{id, label}` comes back `{id: undefined, label: undefined}`. `AttachmentLink.open()` (`messages.$caseId.tsx:317`) then fetches `` `${BASE_URL}/api/v1/documents/undefined/content` ``, which 404s, and the user sees the generic "Could not open attachment" toast for every attachment on every message, unconditionally.

**Fix:** either normalize on the backend key names (`normalizeAttachment` reads `a.document_id`/`a.display_name`) or, cleaner, have `messaging.py`'s compose handler use `id`/`display_name` to match the vocabulary `DocumentRecord` already uses everywhere else in this codebase (`documents.py`'s `DocumentRecord.id`, not `document_id`). Recommend the backend rename — `document_id` is the only place in the whole API that names a document reference that way; everywhere else (`DocumentRecord`, `CostEntryRecord.work_order_id` aside) an id is just `id`.

---

### 6. MEDIUM — Thread list's sender prefix is always blank
`backend/app/api/messaging.py:75` (`ThreadListItem.last_message_sender_type`) vs. `frontend-fixi/src/hooks/use-messaging.ts:36` (`last_sender`), consumed at `frontend-fixi/src/routes/messages.index.tsx:275`.

`item.last_sender ? \`${item.last_sender}: \` : ""` never has a value to show — the backend's field is named `last_message_sender_type`. Non-crashing (the `? :` guards it), but every thread-list preview permanently drops the "Tenant:"/"Contractor:"/"Operator:" prefix that's meant to help an operator scan who spoke last without opening the thread.

**Fix:** rename `ThreadListItem.last_sender` → `last_message_sender_type` in `use-messaging.ts` and the two read sites in `messages.index.tsx`. Frontend-only.

---

### 7. LOW — `CaseListItem`'s `category`/`is_archived` are absent from the frontend type
`backend/app/schemas.py:1190-1207` vs. `frontend-fixi/src/api/types.ts:21-31`.

Currently inert: `fetchCaseList` (`api/endpoints.ts:43-54`) never sends `include_archived=true`, and the backend's `list_cases` defaults `include_archived=False`, so no archival row ever reaches this list today, and `category` simply isn't used for anything in `maintenance.index.tsx`. But the type is silently incomplete, and CLAUDE.md's labelling rule is exactly the kind of thing that quietly breaks the moment someone adds an "include archived" filter to the case list (as already exists for Properties/Tenants/Contractors/Insights) without also adding the `is_archived` field and a badge for it.

**Fix:** add `category: Trade | null` and `is_archived: boolean` to `CaseListItem` in `api/types.ts` now, even unused, so a future archived-toggle can't ship without the compiler forcing the label to be added too.

---

### 8. MEDIUM — No active/idle polling switch; the ticket detail page alone runs three independent pollers
`docs/18_FRONTEND_UX.md` specifies 1s polling during active work, 5s idle. Nothing in `frontend-fixi/src/hooks/*` implements that switch — every `refetchInterval` is a fixed constant:

| Hook | Interval | Where mounted |
|---|---|---|
| `useCaseDetail` | 2000ms (but cheap — `known_version` 304s) | ticket page |
| `useCaseEvents` | 4000ms | ticket page (Timeline) |
| `useCaseMessages` | 4000ms | ticket page (Messages tab) |
| `useMessageThread` | 4000ms | `/messages/$caseId` |
| `useCaseList` | 4000ms | Maintenance list |
| `useDashboardMetrics` | 5000ms | Maintenance list header |
| `useNotifications` | 5000ms | global (UtilityBar, every screen) |
| `useUpcomingAppointments` | 5000ms | Maintenance sidebar |
| `useMessageThreads` | 5000ms | `/messages` |
| `useAgentStatus` | 10000ms | global (sidebar, every screen) |
| `usePropertyHistory`/`usePropertyStats` | 10000ms | property history tab |
| `useOverview` | 15000ms | `/` |
| `useGlobalUnreadCount` | 15000ms | global (every screen) |

Per CLAUDE.md this is a single-worker SQLite backend process that also has to serve Gemini/ElevenLabs-blocking coordinator work on the same process. A ticket page open in one tab runs three concurrent pollers (2s + 4s + 4s) against that one worker indefinitely, and `useNotifications`/`useAgentStatus`/`useGlobalUnreadCount` poll on *every* screen regardless of whether anything is happening. None of this is catastrophic at demo scale (React Query's default `refetchIntervalInBackground: false` at least stops it when the tab isn't focused), but it's a fixed-cost tax with no idle backoff, on exactly the architecture (one worker, blocking provider calls) CLAUDE.md flags as tight.

**Fix:** not urgent for the MVP, but the cheapest win is collapsing `useNotifications`+`useAgentStatus`+`useGlobalUnreadCount` (three separate 5-15s global pollers mounted on every screen) into one shared interval/query, and adding a simple `document.visibilityState`-gated or "any mutation in the last N seconds → 1s, else 5s" toggle to the case-detail/events pollers specifically, since that's the screen the spec's "active work" language is clearly about.

---

### 9. LOW — Triplicated "properties for a picker" fetch, three independent normalizations of the same endpoint
`frontend-fixi/src/hooks/use-new-ticket.ts:13-20` (`usePropertyOptions`), `frontend-fixi/src/hooks/use-analytics.ts:360-371` (`useAnalyticsProperties`), `frontend-fixi/src/hooks/use-directory.ts:555-569` (`useDirectoryProperties`), plus `use-reports.ts:122-143` (`useReportProperties`, with its own `id`/`property_id` and `address_line`/`address` fallback-key guessing). All four hit `GET /api/v1/properties?limit=200` and all four currently produce correct results because the real shape is stable — but each has its own cache key, its own type, and its own (sometimes needlessly defensive) field-reading logic. Not a live bug; flagging because four independent copies of the same 20-line function is exactly how the next field rename produces a fourth undetected mismatch instead of one.

**Fix:** not blocking. Worth consolidating onto `fetchProperties`/`PropertyListResponse` from `api/endpoints.ts`/`api/types.ts` once the ownership-split comments (`use-property.ts:29-34`, `use-messaging.ts:9-21`) are no longer operative.

---

### 10. NIT — Type honesty: two `as unknown as`/`as Trade` casts, otherwise clean
`use-messaging.ts:121` (`useNavigate() as unknown as (...)`, documented and deliberate — TanStack Router's dynamic-search typing limitation). `use-analytics.ts:261` (`(row.category ?? "OTHER") as Trade` in `recurring_issues` — documented as "never null in practice" since `analytics.recurring_issues` excludes `category IS NULL` server-side; a real but narrow assumption about backend query behavior, not enforced by any type). No `any`, no unguarded non-null `!` assertions on network data found across `src/api/` or `src/hooks/`. This codebase's defensive-normalization style (`asString`/`asNumber`/`Record<string, unknown>` + manual field pulls in `use-directory.ts`, `use-property.ts`) is generally *why* Findings 2-6 didn't crash instead of just rendering wrong — worth keeping, but see Finding 1: the one place optionality was pushed all the way to "nothing typed as required" (`OverviewResponse`) is also the one place a crash still got through, because `item.kind` feeds a `Record` index used as a JSX tag rather than displayed as text.

---

## `BASE_URL`/auth bypass check (item 5)

Every `fetch()` call that bypasses `request()`/`requestOrNotModified()` was checked: `RecordingPlayer` (`maintenance.tickets.$ticketId...tsx:403`), `fetchDocumentObjectUrl`/`uploadDocument` (`use-case-content.ts:186,241`), `fetchAuthedBlob`/`uploadDocument` (`use-property.ts:291,321`), `AttachmentLink.open` (`messages.$caseId.tsx:317`), `useExportReportsCsv` (`use-reports.ts:160`), `verifyCredentials` (`api/client.ts:87`). All of them attach `Authorization: authHeader(creds)` and resolve through `BASE_URL` correctly — none bypass auth. The two `<img>` tags that use a bare `src` (`DocumentsPanel.tsx:97` evidence photos, `MessagesPanel.tsx:94` message photos) point at external/spoken-text `locator`/`photo_url` values, never at `/api/v1/documents/...` — both are explicitly *not* calling an authenticated backend endpoint, so no finding there (confirmed by reading `EvidenceRef`/`Message.photo_url`'s actual producers — neither is populated with an internal document URL today).

---

## Invalidation audit (item 3)

- **New case** (`use-new-ticket.ts` `useCreateTicket`): invalidates `["cases"]`, `["dashboard-metrics"]`, `["agent-status"]`, `["overview"]`, `["insights"]`, `["property-history"]`, `["property-stats"]`. Matches the spec ("list, dashboard, overview, insights, property history and property stats") exactly. Gap: does **not** invalidate `["insights-cases"]` (a separate top-level query-key namespace from `["insights"]` — see below) or anything under `["reports"]`, so the Insights drill-down table and the Reports page both keep showing pre-creation data until their own poll/refetch.
- **Cost mutations** (`use-case-content.ts` `useInvalidateCosts`): invalidates `costsQueryKey(caseId)`, `caseDetailQueryKey(caseId)`, `["property-stats"]`, `["insights"]`, `["reports"]`. Matches the spec's list of surfaces by *intent*, but **`["reports"]` is a dead invalidation** — `useReportsSummary`'s real query key is `["reports-summary", filters]` and `useReportProperties`'s is `["reports-properties"]`; neither starts with `"reports"`, so `invalidateQueries({queryKey: ["reports"]})` matches nothing in the cache. A cost recorded while the Reports page is open (or cached) will not refresh it.
- **Message send** (`use-messaging.ts` `useSendMessage`): invalidates thread + thread list, correctly omits the unread badge — verified against backend semantics (`messaging.py:126-146`'s `unread_counts_by_case` only counts `TENANT`/`CONTRACTOR` senders; an operator's own message is never "unread," so not refreshing the badge on send is correct, not a gap).
- **Mark thread read** (`useMarkThreadRead`): invalidates thread, thread list, *and* unread count — correct, this is the one action that actually changes the badge.

**Fix for the real gap:** change `use-case-content.ts:321` from `["reports"]` to `["reports-summary"]` (and add `["reports-properties"]` if property option changes matter, though those rarely do from a cost mutation).

---

## `useQuery` key audit (item 2)

No exact key collisions found (two different response shapes sharing one identical key array). Every list/detail query's key includes its filter/id parameters (`["cases", params]`, `["contractors", params]`, `["tenants", params]`, `["properties", params]`, `["case-detail", caseId]`, `["insights", qs]`, `["reports-summary", filters]`, `["messages-threads", filters, limit]`, etc.) — no query was found that reads a parameter its key omits, so no stale-on-filter-change risk beyond the `["reports"]` invalidation gap above. Three independent hooks share the loose prefix `"properties"` (`["properties", params]` in `use-property.ts`, `["properties", "picker"]` in `use-analytics.ts`, `["properties-directory"]` in `use-directory.ts`) — not a collision (different full keys, different owners), but see Finding 9.
