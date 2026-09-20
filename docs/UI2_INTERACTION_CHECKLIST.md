# Interaction inventory

Every visible, enabled control in the Fixi operator UI, what it does, what
backs it, and how it was verified.

Rules this list is checked against:

- **No enabled control may silently do nothing.** A `console.log`, a toast
  with no write behind it, a modal that cannot submit, a decorative
  dropdown, or navigation to an unrelated screen does not count.
- A **disabled** control is legitimate only for loading, invalid input,
  insufficient permission, missing configuration, or a prohibited domain
  transition — and it must say which, next to itself.
- Controls are never deleted to shorten this list.

Verification legend — `unit` a backend test, `type` passes `tsc --noEmit`
(every file does; noted only where it is the strongest evidence a control
has), `build` survives the production build (every route does), `manual`
exercised in a browser against a served build on an isolated no-contact
instance, `—` not exercised by hand.

**Read the legend honestly.** `type` means the code compiles and the call
site is wired to a real endpoint; it does **not** mean somebody clicked
it. Three bugs this session — a hardcoded API origin, a crashed Insights
page, and URL filter flags that were inert because the router
JSON-quoted them — all passed `type`, `build` and the full backend suite,
and were only found by opening the app. Rows marked `type` alone should
be read as "wired and compiles", not "confirmed working".

Browser pass covered: Overview, Properties (incl. archival), property
history for 14 King Street, Contractors (incl. archival), Insights (incl.
archival, with charts populated), Messages list and thread, Reports, and
one ticket detail page. Tenants, the three non-history property tabs, and
the individual create/edit dialogs were **not** clicked through.

---

## Global shell (`AppShell.tsx`, `UtilityBar.tsx`)

| Control | Behaviour | Backed by | Verified |
| --- | --- | --- | --- |
| Sidebar × 8 (Overview, Maintenance, Properties, Contractors, Tenants, Insights, Messages, Reports) | Navigates; active state follows the URL, exact-match for `/` | TanStack router | type, build, manual |
| Messages unread badge | Real global unread count; hidden at zero | `GET /messages/unread-count` | unit, type |
| Agent status panel | Live dot + label + active-case count; says "idle" when idle, "unavailable" on error | `GET /metrics/dashboard` (`agent_active`) | unit, type, manual |
| Operator chip | Shows the authenticated operator, not a hardcoded persona | session credentials | type |
| Global search box | Debounced; filters the Maintenance list, and `GET /search` spans cases/properties/tenants/contractors | `GET /search` | unit, type |
| Notifications bell + popover | Real unread count; each row links to its case | `GET /notifications` | unit, type |
| **+ New Ticket** | Dialog → creates a real case, navigates to it | `POST /cases` | unit, type |

## Maintenance (`/maintenance`)

| Control | Behaviour | Backed by | Verified |
| --- | --- | --- | --- |
| Status filter (All / each `CaseStatus`) | Refetches the list | `GET /cases?status=` | unit, type |
| Urgency filter | Filters by `risk.urgency` | case list | type |
| Property filter | Options from the real directory | `GET /properties` | type |
| Contractor filter | Filters by assigned contractor | `GET /cases?contractor_id=` | unit |
| KPI cards + comparison % | Calculated; no arrow when there is no honest baseline | `GET /metrics/dashboard` | unit |
| Ticket row → detail | Every ticket, not only one | route param | type |
| Row "…" → Open ticket | Navigates | router | type |
| Row "…" → Open conversation | Navigates to the thread | router | type |
| Row "…" → Cancel case | Dialog, reason required, version-checked | `POST /cases/{id}/cancel` | unit, type |
| Row "…" on a terminal case | **Disabled with the reason shown** ("this case is cancelled — it cannot be cancelled") | transition graph | type |
| Upcoming visits list + View all | Real appointments | `GET /appointments/upcoming` | unit |

## Ticket detail (`/maintenance/tickets/$id/{-$section}`)

| Control | Behaviour | Backed by | Verified |
| --- | --- | --- | --- |
| 9 section tabs (Overview, Summary, Timeline, Calls, Work, Property, Files, Costs, Messages) | Deep-linkable; back/forward works | route param | type, build, manual |
| Copy address | Clipboard | — | type |
| Share | Copies a deep link; grants no public access | — | type |
| Edit | Dialog → persists; 409 on a stale version is surfaced | `PATCH /cases/{id}` | type |
| More-actions kebab | Copy reference / conversation / property history / export summary | mixed | type |
| Status control | Only legal transitions from the current status; each takes a required reason | `/cancel`, `/resume`, `/reopen` | unit, type |
| Progress track | Derived from real case, work-order and appointment state; escalation and blocked work shown explicitly | case snapshot | type, manual |
| Record an update | Contractor report / tenant update / visit window passed, with named reporter | `POST /cases/{id}/field-updates` | type |
| Approve / Reject (DecisionCard) | Version- and hash-checked approval | `POST /actions/{id}/approval` | unit |
| Reschedule | Dialog → cancels the old visit, records a **pending** replacement | `POST /appointments/{id}/reschedule` | unit, type |
| Recording player | Streams the stored audio | `GET /communications/{id}/recording` | unit |
| Files tab | Upload, preview, download, delete | `/documents` | unit, type |
| Costs tab | Cost entries + totals; add / edit / delete | `/cases/{id}/costs` | unit, type |
| Tenant contact | Opens profile or conversation; **disabled with a reason** when `contact_allowed` is false | tenant record | type |
| Contractor View profile | Navigates | router | type |
| View all (timeline / messages / property history) | Navigates to the full view | router | type |

## Properties (`/properties`, `/properties/$id/…`)

| Control | Behaviour | Backed by | Verified |
| --- | --- | --- | --- |
| Search, include-archival toggle | Refetches | `GET /properties` | unit, type, manual |
| New property | Validated form → persists | `POST /properties` | unit, type |
| 4 tabs (Maintenance history, Details, Documents, Notes) | Each a real route and deep link | router | type |
| History table sort / select / select-all / bulk export | Sorts server- or client-side; export produces a real file | history | type |
| Donut / spend bars / recurring rows | Drill down to the supporting records | `GET /properties/{id}/stats` | unit, type, manual |
| Row chevron | Opens that case | router | type |
| Details edit | Persists; archival properties refuse with a stated reason | `PATCH /properties/{id}` | unit, type |
| Documents upload / preview / download / delete | Real files on disk | `/documents` | unit, type |
| Notes add / edit / delete | Persisted with author and timestamps | `/notes` | unit, type |

## Contractors, Tenants

| Control | Behaviour | Backed by | Verified |
| --- | --- | --- | --- |
| Search, trade / approval / property filters | URL-backed, refetch | `GET /contractors`, `GET /tenants` | unit, type |
| Create / edit dialogs | Validated, persisted | `POST`/`PATCH` | unit, type |
| Approve contractor | **Disabled until a verification note exists**; 409 surfaced | `PATCH /contractors/{id}` | unit, type |
| Profile work history / cases | Link to the real records | joins | unit, type |
| Archival rows | Labelled "(archived, FIXTURE)" / "Sample history"; non-approved and marked "Not assignable"; edits refused with a reason | `archive_batch_id` | unit, manual |

## Insights, Reports, Messages, Overview

| Control | Behaviour | Backed by | Verified |
| --- | --- | --- | --- |
| Overview metric cards | Link to filtered destinations; real counts; zero shown honestly | `GET /overview` | unit, type, manual |
| Needs-attention rows | Link to the case | `GET /overview` | unit, type |
| Insights filters (date range, property, category, include-archival) | URL-backed, refetch | `GET /insights` | unit, type, manual |
| Chart drill-downs | Every bar / segment / recurrence row opens its supporting records; each is a labelled `<button>` | `GET /insights/cases` | type, manual |
| Reports filters | Same definitions as Insights. **Not URL-backed** — a filtered report is not linkable | `GET /reports/summary` | unit, manual |
| Export CSV | Authenticated fetch → real download; totals equal the on-screen figures | `GET /reports/export.csv` | unit, type |
| Print view | `print:` layout, chrome hidden, `window.print()` | — | type |
| Thread list: search / unread-only / include-archival | Refetch | `GET /messages/threads` | unit, type, manual |
| Open thread | Marks read; sidebar badge drops | `POST /messages/threads/{id}/read` | unit, type |
| Composer — Internal note | Posts; a complete outcome | `POST /messages/threads/{id}` | unit, type, manual |
| Composer — Email / SMS | Saves a **draft**; button reads "Save draft"; the API's own reason is printed under the message | same | unit, type, manual |
| Per-message mark unread | Toggles | `POST /messages/{id}/unread` | unit, type |

---

## Deliberately disabled, with reasons shown

| Control | Why |
| --- | --- |
| Email / SMS "send" | No delivery transport is configured. The message is saved as a draft and labelled as one; it is never shown as sent. |
| Approve contractor without a verification note | Approval is a deliberate act that must record what was verified. |
| Edit / delete on an archival record | Archival rows are read-only sample history. |
| Case actions on a terminal case | The transition graph permits none. |
| Tenant contact when `contact_allowed` is false | A recorded do-not-contact instruction. |

## Removed, not hidden

`Play demo`, `Replay case`, `Reset demo`, hard `Delete ticket`, and
`Simulate an observation` are gone from the UI **and** their endpoints are
gone from the API (`app/api/demo.py` deleted). Nothing in normal operation
depends on scripted progression any more.

---

## Gaps found in the browser pass, and their status

| Finding | Status |
| --- | --- |
| Served build called `localhost:8000` regardless of its own origin, so it showed a login form while its own backend had auth off | **fixed** — `BASE_URL` resolves same-origin for a served build |
| Insights crashed on load: five field names drifted between the analytics API and the screen | **fixed** — normalised in `use-analytics.ts` |
| Every URL filter flag was inert (TanStack JSON-quotes search values, so `=== "true"` never matched) | **fixed** — `lib/search-params.ts` tolerant readers, used by every screen |
| Ticket browser tab read `#<uuid> — Fixi` | **fixed** — title set from the loaded case |
| Contractors had no archival toggle | **fixed** |
| Insights drill-down claimed hour bounds were unavailable | **fixed** — the API serves them now |
| Reports filters are not in the URL, so a filtered report is not linkable | **open** — the controls work; only the deep link is missing |
| Insights property filter lists operational properties only | **open** — an archival sample property cannot be singled out |
| Insights drill-downs open an inline panel rather than pushing filters onto Maintenance | **open by choice** — the brief allowed either |
| Property-history trade drill-down's total is computed from the filtered rows, not asserted equal to the donut segment | **open by design** — the donut sums work orders by trade, a history row carries the case's single primary trade; the two genuinely differ, and the screen says so |

## Not clicked through

Tenants directory and profile, Property details / Documents / Notes tabs,
and every create/edit dialog were built to the same patterns as the
screens that were exercised, and compile and build clean — but nobody
opened them. Treat them as unverified until someone does.
