# Implement the complete UI2 application — unattended assignment

You are the lead implementation agent. Execute this assignment in the target repository. This is an implementation task, not a request for a plan.

## 1. Work silently and autonomously

I will leave you unattended for approximately two hours. Do not send acknowledgements, progress updates, explanations, questions, approval requests, or a final prose report in chat. Put plans, decisions, progress, unresolved blockers, verification evidence, and the final handoff in repository files. Use tools directly and keep tool output focused. Do not spend context narrating your actions.

Make reasonable decisions independently using the repository, existing contracts, the reference UI, and authoritative documentation. For a difficult or uncertain question, use a bounded **Sonnet** subagent for research, investigation, implementation, or independent verification. Explicitly select an available Sonnet model; do not assume subagents inherit a lightweight model. Keep architecture, prioritization, and final decisions with the root Opus agent. Give subagents concise context, defined ownership, evidence requirements, and an instruction not to spawn further agents. Parallelize independent work conservatively and avoid overlapping file edits. If Sonnet is unavailable, work through the question yourself rather than asking me or silently substituting another expensive model.

Also delegate suitable routine work to Sonnet; delegation is not reserved for hard questions. In particular, use Sonnet for synthetic historical data design/generation, deterministic import scripts, repetitive record descriptions, asset-to-record mapping, bounded repository searches, mechanical documentation, and independent data validation. Opus should define the schema, constraints, expected outputs, and acceptance checks, then review the resulting artifacts. Do not spend Opus context inventing dozens of example records by hand.

Batch related routine work into a small number of coherent assignments. Do not create a subagent per record or send every subagent the entire repository and conversation. Prefer files and concise evidence summaries over returning large datasets in chat. Run independent tasks in parallel only when that helps, and reserve expensive root reasoning for integration, domain semantics, and final acceptance.

Silence does not authorize destructive actions, external outreach, or bypassing tool permissions. If an action requires unavailable authorization, record the blocker, choose a safe alternative, and continue independent work. Never wait for my answer.

Use the time for implementation and verification. Do not stop after a plan, a successful build, or copying the static screens. Do not idle to fill the time. Track elapsed time and leave a reviewable, runnable result with an honest handoff before ending. If complete earlier, finish. If the full scope cannot be completed in the available window, preserve coherent working changes and document the exact remaining work; do not claim completion or conceal missing features.

Maintain a concise progress/checkpoint file so another session can resume without reconstructing the investigation. Put the final report in `docs/UI2_IMPLEMENTATION_HANDOFF.md`, or the repository's equivalent established handoff location. No chat report is needed.

## 2. Outcome and priorities

Replace the older UI in my actual application with the design in `liza.UI2/`, intended for integration into main. Make the entire application functional, backed by persistent records and real workflows.

The highest priorities are:

1. **Every visible button and interactive control must work.**
2. Reproduce existing reference screens one-to-one visually.
3. Preserve all reference UI content and existing working application capabilities.
4. Use genuine operational behavior and consistent database-backed data.
5. Keep the existing ElevenLabs/Twilio integration intact while ensuring this unattended session cannot call or otherwise contact anybody.

If something needed by the application is missing from the reference UI, **extend the UI** using its existing design language. Do not remove reference buttons, cards, tabs, charts, navigation destinations, sections, or information to make implementation easier. Do not simplify away difficult features.

The explicit exception is legacy hackathon/demo functionality: remove those controls and their production behavior as directed below. Preserve genuine domain restrictions and access controls; making a button work does not mean bypassing them.

For screens that exist in the reference, match layout, typography, spacing, colors, borders, shadows, icons, image crops, table density, badges, and content hierarchy. For screens or interaction states that do not exist, create complete, consistent extensions. Do not interpret an absent reference screen as permission to leave a destination unimplemented.

## 3. The hackathon has ended

Repository notes may still describe a hackathon, scripted scenarios, demo mode, fixture-driven runtime behavior, or one-day scope limits. Those product requirements are outdated.

I want an application I can actually use. New cases must originate from real input or genuine integrations. Property, tenant, contractor, observation, appointment, message, document, cost, and outcome records must represent user-entered or integrated information.

Remove user-facing features such as Play demo, Run demo, Start scenario, Next step, Reset demo, Inject observation, simulated contractor responses, and scenario selectors. Remove or disconnect their exposed production APIs, startup hooks, jobs, and dependencies. Hiding the buttons is insufficient if normal application behavior still relies on scripted progression.

Replace mocked runtime decisions, automatic success responses, fake bookings, canned model output, artificial incoming communications, and scripted case completion with genuine implementations or explicit human-recorded workflows.

Keep useful architecture, authentication, domain rules, data protections, and existing integrations. Do not perform an unrelated technology rewrite merely because the hackathon ended. Technologies are retained for their usefulness, not sponsor requirements.

Older MVP exclusions do not justify omitting the requested navigation sections, documents, notes, analytics, reports, or their necessary backend support. Update relevant documentation to reflect the expanded application.

Do not seed fictional active workload. An empty operational workspace is legitimate: implement useful onboarding and empty states rather than manufacturing activity.

## 4. Inspect the target and reference before editing

Identify the current branch, uncommitted work, application entry points, frontend/backend stack, database models, API clients, authentication, integrations, tests, and existing seed/import mechanisms. Read applicable AGENTS.md, CLAUDE.md, README, and relevant domain, API, database, safety, and architecture documents. Verify important claims against the current branch.

The reference is the `liza.UI2/` directory on the `liza.UI2` branch. The destination is the actual application using the older UI, intended for main. Locate both reliably. If the current checkout is the reference branch, preserve it and use a separate worktree/implementation branch based on the target. Do not implement the result solely inside the standalone reference workspace.

Preserve uncommitted work. The reference checkout may include a locally added `src/components/ui/button.tsx` required for startup, plus generated route changes. Do not assume the committed branch captures all reference files. Do not merge the reference branch wholesale over the application. Do not push, merge into main, or deploy during this assignment.

Inspect these reference sources:

- `liza.UI2/src/styles.css`
- `liza.UI2/src/components/fixi/AppShell.tsx`
- `liza.UI2/src/components/fixi/UtilityBar.tsx`
- `liza.UI2/src/components/fixi/Badge.tsx`
- `liza.UI2/src/components/ui/button.tsx`, if present
- `liza.UI2/src/routes/maintenance.index.tsx`
- `liza.UI2/src/routes/maintenance.tickets.$ticketId.{-$section}.tsx`
- `liza.UI2/src/routes/properties.14-king-street.history.tsx`
- `liza.UI2/src/lib/fixi-data.ts`
- `liza.UI2/src/assets/`

Use browser tools to inspect the running reference, including clicks and screenshots. It may already be at `http://127.0.0.1:5175/maintenance`. If unavailable, run the reference locally without disturbing other work.

Reference routes:

- `/maintenance`
- `/maintenance/tickets/1042`
- `/maintenance/tickets/1042/summary`
- `/maintenance/tickets/1042/timeline`
- `/maintenance/tickets/1042/messages`
- `/properties/14-king-street/history`

Record visual baselines at known viewport sizes. Inspect source and browser behavior together. The reference is mostly static: sidebar links frequently point back to Maintenance, many controls do nothing, and the three ticket section URLs currently show the same page. Those are gaps to implement, not behaviors to preserve.

## 5. Preserve and extend the design

Reuse or faithfully port the reference's components, tokens, assets, and styling into the existing application stack. Do not introduce TanStack Start or replace the target router solely because the reference uses them.

Match:

- Fixi branding and the pale background, white cards, dark green primary styling.
- Left navigation, active states, bottom agent-status panel and account area.
- Top search, notifications, and New Ticket button.
- Content widths, spacing, type sizes, card proportions, corner radii, and shadows.
- Compact tables, status/priority badges, avatars, and property thumbnails.
- Ticket progress indicator, vertical timeline, and detail columns.
- Property tabs, issue donut, annual-spend bars, recurring-issue panel, and history table.

Retain existing real features such as approvals, observations, work dependencies, agent activity, voice recordings, and transcripts. Integrate them through additional compatible panels, tabs, or routes if the reference does not provide a place for them.

Visual fidelity does not require copying contradictory static figures. For example, the reference shows 8 total tickets above 11 historical rows, and its displayed spend does not match the row total. Preserve the design and calculate correct values.

## 6. Inventory and implement every control

Maintain an interaction checklist covering every visible link, button, icon action, dropdown, tab, checkbox, sort header, filter, search field, image, chart drill-down, row chevron, notification control, and account control.

For each, record its intended behavior, destination or mutation, data source, persistence requirement, and verification result.

No enabled control may silently do nothing. A console log, toast, modal with no working submission, decorative dropdown, or navigation to an unrelated screen does not count as implementation. Do not remove controls to reduce the checklist. Do not leave requested sections as “coming soon.”

Legitimate disabled states are allowed for loading, invalid input, insufficient permissions, missing configuration, or prohibited transitions. Explain the reason and provide the relevant setup or corrective path. These states cannot conceal unfinished implementation.

Use working forms with validation, loading/error feedback, cancellation, keyboard access, focus handling, and persisted success. Give icon actions meaningful accessible names. Handle empty results and unavailable/deleted records cleanly.

## 7. Implement all eight sidebar destinations

Each destination needs distinct content, correct active navigation, usable deep links, browser back/forward support, and database-backed behavior.

### Overview

Provide portfolio metrics, recent activity, upcoming appointments, and items needing attention. Cards and lists should link to corresponding records or filtered views. Metrics must reflect actual state.

### Maintenance

Reproduce the reference dashboard. Implement:

- All/Open/In progress/Waiting/Resolved filters.
- Priority, property, and contractor filters.
- Search, sorting, selection/select-all, appropriate bulk actions, and row menus.
- Validated, persisted New Ticket creation.
- Detail navigation for every ticket, not only #1042.
- Upcoming visits, individual appointment links, and View all.
- Calculated KPI values and comparison percentages.
- Property-insights navigation.

Make global search useful across tickets, properties, tenants, and contractors. Maintain filter/sort state appropriately across navigation.

### Properties

Add a searchable property index, creation/editing, and individual property pages. Reproduce the reference property-history design for any selected property.

Implement all four tabs:

- Maintenance history: real case links, outcomes, contractors, costs, sorting, selection, and analytics.
- Property details: persisted relevant property information and relationships, with editing.
- Documents: actual upload, metadata, preview/download, and appropriate removal.
- Notes: persisted content, authorship, timestamps, editing, and appropriate removal.

Implement issue-breakdown, annual-spend, and recurring-issue drill-downs. Historical row chevrons must open their corresponding records.

### Contractors

Provide a searchable directory, creation/editing, profiles, trade/contact information, linked assignments and work history, and appropriate assignment workflows. Distinguish approved contractors from unverified research candidates. Do not fabricate availability or external acceptance.

### Tenants

Provide a searchable directory, creation/editing, profiles, property relationships, contact details, linked maintenance cases, and conversations. Preserve relationship integrity.

### Insights

Provide calculated trends for case volume, categories, spend, resolution time, and recurring issues. Implement date/property/category filters and drill-downs. Use the same metric definitions as other screens.

### Messages

Provide persisted case-related conversations, full threads, search/filtering, attachments, timestamps, read/unread state, and a working composer connected to supported real delivery channels.

Distinguish drafts, internal notes, queued delivery, delivered messages, and failures. Do not display “sent” based only on saving a draft or accepting a provider request. Global unread counts and ticket previews must derive from the same records. Preserve existing genuine voice/conversation functionality.

### Reports

Implement report filters and database-derived maintenance, spend, resolution, and recurring-issue summaries. Include working CSV export and a printable report view. Exports must agree with UI values under the same filters and identify synthetic historical content when included.

## 8. Make the ticket detail page fully functional

Reproduce the reference:

- Ticket title/number, priority, address and copy action.
- Share, Edit, more-actions menu, and status control.
- Reported → Diagnosing → Contractor on site → Follow up → Resolved progression.
- Case overview, evidence photographs, and image previews.
- Tenant contact actions.
- Assigned contractor and View profile.
- Next appointment and Reschedule.
- Activity timeline and View all.
- Latest incoming messages, attachments, and View all.
- Related property history and View all history.

Bind everything to the selected case. Editing must persist and refresh affected views. Share should copy a valid deep link without granting public access. Contact actions must open the correct profile, conversation, or configured workflow. Rescheduling must update persisted appointment information and all related views.

Full timeline and message destinations must expose their corresponding case-specific content rather than rendering the same undifferentiated page. Historical cases must have their own detail views.

The progression is a presentation of real domain state and events. Do not falsely show every case following an identical scripted linear path; extend the design when blocked work, additional visits, dependencies, or other supported states require it.

## 9. Preserve authoritative domain behavior

Extend the target application's existing backend, database, API clients, authentication, and refresh conventions. Add migrations and endpoints where needed rather than using browser-only storage for business data.

Keep case state, work-order state, appointment state, dependency state, and external-action state distinct. Implement explicit mappings into display labels such as “In progress,” “Contractor booked,” and “Awaiting tenant.”

The status control must execute legal domain actions and enforce their preconditions. It must not become an unrestricted “set status” endpoint. Preserve approval, resolution, observation, idempotency, version/concurrency, and audit rules.

A finished visit does not necessarily mean a resolved repair. Provider acceptance does not mean delivery or confirmed booking. A manually recorded appointment does not mean a contractor accepted it externally.

Use genuine integrations where configured and explicit human-recorded workflows where appropriate. Record who supplied a manual confirmation and when. Do not silently infer external events.

The agent-status panel must reflect actual state. Do not hardcode “AI agent active” or “Handling 24 tasks.”

## 10. Only completed historical data may be synthetic

Add an optional, deterministic, database-persisted historical dataset sufficient to populate charts and past property history. Aim for approximately 60 varied completed archival cases across the reference properties, spanning multiple years such as 2021–2026. Adjust quantity to produce useful, internally consistent history.

**Delegate the historical dataset and generator/import implementation to a Sonnet subagent.** First give it the relevant existing schema, permitted archive representation, provenance rules, date bounds, category definitions, asset paths, and metric contracts. Assign ownership of specific dataset/generator files, excluding unrelated application code. Have it produce a reproducible generator or compact structured dataset, not a long narrative or hundreds of records pasted into the root context. Prefer a fixed random seed and programmatic generation for repeated structure. Opus remains responsible for approving the representation and integrating the result.

The historical dataset must support more than spend totals. Include internally consistent historical report/open timestamps, relevant past status intervals, waiting-for-response intervals, responses where represented as archival facts, work/appointment milestones where appropriate, and resolution timestamps. All such intervals must end in the past and each case must finish in a completed archival state. Use varied but plausible durations and category/cost distributions so historical resolution averages, response-time distributions, trends, and prior-period comparisons are meaningful. Do not manufacture provider receipts, actual-delivery claims, or production event streams to express these facts; use clearly synthetic archival fields or records.

Separate historical analytics from current operational counts. Past open/in-progress/waiting intervals may power explicitly historical or as-of charts. They must not populate today's Open tickets, In progress, Awaiting response, current workload, or notifications. Those current cards must come from genuine operational records and may correctly show zero. Historical resolved counts and averages may include the synthetic archive only within a clearly identified scope and date window. Do not move completed sample cases into active states simply to make dashboard cards nonzero.

Require the Sonnet worker to provide programmatic validation for referential integrity, ordered timestamps, nonnegative durations/costs, closed historical intervals, absence of pending operational work, recurrence grouping, reconciled category/year totals, and idempotent imports. It should return the artifact paths, a compact dataset summary, validation results, and any assumptions. When useful, use a separate bounded Sonnet verifier to check the data and metric calculations; do not duplicate the entire generation assignment. Opus should review these checks and resolve semantic issues rather than regenerate the records itself.

Include plausible categories, dates, completed outcomes, historical contractor descriptions, costs, notes, documents, and appropriately identified illustrative images. Roof leaks, damp, plumbing, heating, electrical, gutter, and general maintenance examples should support meaningful recurrence and spending analysis.

Use the reference's 14 King Street roof-leak scenario as historical illustration if useful. Do not create a fictional current case or contactable operational James Doe/ABC Roofing record merely to match the reference screenshot. Use stable display numbers where compatible without breaking existing internal identifiers.

Historical records must:

- Have explicit synthetic archival provenance.
- Be inspectable as archival records, with clear identification in relevant detail/reporting views.
- Contain no active work, pending approvals, future appointments, unread operational messages, or scheduled jobs.
- Never trigger model execution, calls, messages, booking, or other workflow actions.
- Be excluded from current workload, active queues, notifications, and live agent-status indicators.
- Use a consistent archive/import representation without fabricated consent, provider receipts, tenant confirmations, or evidence of actual external activity.

Keep archival identities separate from contactable operational identities. Do not silently attach invented history to real properties; use explicit mapping or separate sample archival properties. Historical property views and portfolio filters must make the distinction usable.

Provide an idempotent additive import command and a narrowly scoped way to remove only that import batch. Do not wipe or replace existing data. Preserve genuine records and ambiguous records lacking reliable provenance. The application must work normally without the historical dataset.

Use a consistent date/clock strategy for relative timestamps, property age, comparison periods, and year labels. Do not hardcode “Tomorrow” against an old date.

## 11. Reuse assets honestly and calculate all metrics

Reuse `liza.UI2/src/assets/`, including `house-exterior.jpg`, the individual property photos, `ceiling-stain.jpg`, `ceiling-damp.jpg`, and `roof-flashing.jpg`. Preserve their visual treatment. Sample photographs may illustrate synthetic historical records; they must not masquerade as evidence for a genuine current property or case.

Uploaded documents and evidence require actual stored files plus metadata. Notes must persist. Do not fabricate live recordings or transcripts.

Remove hardcoded KPI values, changes, donut segments, bar heights, spending totals, and recurrence counts. Document consistent definitions for active/open/waiting/resolved, resolution time, date windows, categories, recurrence grouping, and actual versus estimated spend. Handle zero baselines and empty datasets explicitly.

Use exact monetary representation such as integer minor units. Prevent double-counting costs, work orders, invoices, or adjustments. The chart, total, detail table, and export must reconcile for the same scope.

The donut must derive from category counts. Annual bars must derive from cost records grouped by year. Recurring issues must derive from property plus a normalized issue classification and link to the records supporting the count. Historical inclusions must be clear, while genuine records naturally contribute as the application is used.

Relevant mutations must refresh all affected screens:

- New case → list, detail, property history, counts and category metrics.
- Legal workflow action → status filters, activity, progression and KPIs.
- Cost entry/adjustment → spend chart, totals and reports.
- Another matching issue → recurrence grouping and drill-down.
- Message/read-state change → thread, previews, unread badges.
- Reschedule → case appointment and upcoming visits.

Business records must survive browser refresh and application restart. UI state alone or localStorage is not sufficient.

## 12. Critical: preserve ElevenLabs/Twilio, but do not call me

The current application already has an ElevenLabs agent connected to Twilio and can call me. Preserve this real integration and its configuration. Do not replace it permanently with a mock, disconnect Twilio, modify the live agent's behavior to return fake results, rotate credentials, or change real phone routing.

**During this entire unattended session, do not initiate an actual call to me or anybody else. Do not send SMS, emails, external messages, real booking requests, or other consequential outreach as a test.** Do not invoke a call-creation endpoint even “just to check” whether it works. Do not rely on an immediate hang-up or subsequent cancellation.

Inspect startup behavior, workers, persisted queues, retry logic, scheduled jobs, and provider adapters before running the application. Use an isolated development/test database and prevent pending genuine jobs from being consumed by the verification environment.

I want downstream call processing verified without receiving a call. Implement a **test-only, side-effect-free provider substitute** at the external transport/adapter boundary. This is allowed for verification and does not relax the prohibition on mocked product workflows.

Preferred approach:

1. Trace the current call request, provider response, callbacks/webhooks or polling, correlation identifiers, conversation retrieval, transcript handling, state transitions, and UI updates.
2. Reuse existing test infrastructure if appropriate. Inject a deterministic provider substitute into an isolated test harness/process, never as the production default.
3. Return representative test responses at the adapter boundary and exercise the normal application logic downstream. Model request acceptance, later completion/failure, and duplicate delivery as separate events where the real contract does so.
4. Feed schema-valid synthetic callback/conversation results into the local test instance using its normal parsing, validation and persistence paths. Use test-only secrets/configuration when signature validation is involved; do not disable production verification.
5. Correlate responses with the correct test case and call identifiers. Mark all resulting records explicitly as test data. Do not insert them into real operational or archival datasets.
6. Verify success and failure paths, duplicate/out-of-order handling where supported, and that normal UI state updates correctly without claiming that a real call occurred.

You may inspect relevant ElevenLabs MCP capabilities and official documentation read-only. If there is a documented simulation facility that is guaranteed not to dial or message anyone, you may use it within the isolated test context. Do not assume such a capability exists, invent a tool, alter the live agent, or call an outbound-call API to obtain a simulated result. If a safe native facility is unavailable or uncertain, use the local adapter substitute.

Use synthetic transcript text only as labelled test input. Do not represent it as an actual conversation with me, invent consent, or fabricate a live recording. If audio playback is tested, use an explicitly identified test audio asset confined to the test environment.

Enforce and verify the no-contact boundary: real calling/messaging transports must not be invoked by tests or local verification. Prefer an injected rejecting transport or equivalent process-local guard in addition to the substitute. Prevent silent fallthrough to real clients when a fixture is missing.

Keep the real integration available for my later intentional use. Any manual real-call verification must remain unperformed and be documented in the handoff. Clearly distinguish “downstream integration verified with test responses” from “live call verified.”

If an interactive local test harness is needed, keep it outside normal product navigation and production routes, disabled by default and explicitly scoped to test configuration. Do not reintroduce a Play demo experience.

## 13. Verification and completion

Implement incrementally and run appropriate checks in isolation. Preserve existing operational tests and add meaningful coverage for new behavior. Test doubles are legitimate in tests; they must not leak into normal production operation.

Required verification includes:

- All eight navigation destinations and their real detail routes.
- Every reference control and newly added control, checked against the interaction inventory.
- Create/edit forms, errors, persistence, deep links, refresh, and browser navigation.
- Filters, sorting, selection/select-all and actual bulk actions.
- Notes, files, image previews, downloads and report exports.
- Database migrations and repeatable historical imports without duplicates.
- No operational jobs or outreach created by historical imports.
- Working empty states with the historical import absent.
- Correct metrics, recurrence grouping and reconciled costs.
- Valid workflow transitions and rejection of invalid actions.
- Existing approvals, observations, dependencies and integration logic.
- ElevenLabs/Twilio downstream processing using the isolated no-contact harness, with zero live call attempts.
- No exposed demo controls, scripted runtime scenarios, or silent mock fallbacks.

Demonstrate in an isolated test database:

1. Create a case through the actual UI/API; verify its detail, property relationship and affected metrics.
2. Edit it and perform a legal workflow action; verify persisted state, event history and refreshed displays.
3. Record a cost through the supported path; verify annual spend, its detail view and report.
4. Add another case in the same recurrence group; verify the count and linked supporting records.
5. Create a note and upload a document; reload and verify retrieval.
6. Verify messaging/call result handling through the isolated provider substitute, without external delivery.
7. Reschedule a test appointment; verify the case and upcoming-visits views agree without contacting anybody.

These are automated or local verification scenarios, not product demo features or seed data for my normal workspace.

Compare screenshots of the reference and implementation at identical desktop viewport dimensions. Fix visual discrepancies. Verify narrower layouts remain usable without removing information or features. A successful build is not evidence that the UI matches or that interactions work.

The handoff file must state:

- What was implemented and where.
- Routes and interaction checklist completion.
- Schema/migration, history-import, run and test commands.
- Functional/regression and visual verification evidence.
- How production integrations were preserved and no-contact testing was enforced.
- What was verified with test doubles versus real services.
- Required external configuration and any remaining manual verification.
- Exact incomplete work or blockers, if any, without claiming the scope is complete.

Finish with the working changes and artifacts in the repository. Do not send a chat summary. Do not push, merge, deploy, contact anybody, or execute a live call.
