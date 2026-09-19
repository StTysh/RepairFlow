# 02 — Business problem research

## Evidence verdict

The problem is real. Evidence is strongest for English social housing and vendor-described letting-agency workflows. It establishes delays, dependencies and communication failures; it does not establish a causal ROI for RepairFlow.

| Evidence | What it establishes | Limit |
|---|---|---|
| Regulator's 2024/25 TSM headline report: 79% of 11 million completed non-emergency responsive repairs met landlords' target timescales | Material scale and timeliness gap | Completed repairs only; landlord targets vary; not a private-lettings sample |
| Same report: median landlord satisfaction with repair time 69.5%; overall repairs service 73.6% | Residents distinguish quality from elapsed time | Medians, not proportions of all English renters |
| Ombudsman 2019 case F: roof work completed after 16 months; internal remedial work another six months later | Inspection accuracy, scaffolding and administration can block a repair chain | Historical selected complaint, not typical duration |
| Ombudsman August 2025 learning | Explicit need to communicate dependencies and oversee contractors | Selected serious failures, not population prevalence |

Sources: [RSH headline report, 4 November 2025](https://www.gov.uk/government/statistics/tenant-satisfaction-measures-202425/tenant-satisfaction-measures-202425-headline-report), [Ombudsman repairs spotlight, March 2019, case F](https://www.housing-ombudsman.org.uk/spotlight-report-on-repairs-complaints-final/), [August 2025 learning](https://www.housing-ombudsman.org.uk/reports/learning-from-severe-maladministration-reports/august-2025/).

Do not turn the remaining 21% into a claim that coordination caused every delay. Labour shortages, parts, funding, technical uncertainty and building approvals can dominate.

## Representative process today

This synthesis combines official landlord obligations and product workflow documentation. It is a representative operating model, not a universal agency SOP.

| Stage | Typical actor/system | Coordination burden |
|---|---|---|
| Report | Tenant by phone, portal, email or message | Identify property, duplicate request, gather evidence |
| Triage | Property manager, repair desk or diagnostic service | Urgency, trade, ownership, warranty and responsibility |
| Approval | Landlord/authorized manager | Quote, budget authority, access arrangements |
| Supplier selection | Preferred contractor list, marketplace, tender or manual contact | Trade coverage, competence, insurance, availability |
| Appointment | Coordinator, contractor and resident | Negotiate overlapping windows; obtain access consent |
| Attendance | Contractor/mobile work-order system | Record no-access, incomplete visit, findings and evidence |
| Follow-on | Coordinator and additional trades | Link prerequisite work to original unresolved defect |
| Completion | Contractor, resident and manager | Verify outcome, documentation, invoice and follow-up |

[Fixflo workflow](https://www.fixflo.com/features/workflow-management), [Re-Leased maintenance operations](https://www.re-leased.com/product/property-operations-maintenance), and [askporter repair journey](https://www.askporter.com/housing/repair-journey) show that many of these stages are already digitized or automated.

## Where cases stall

- A contractor's report is stored as a note but never converted into an actionable prerequisite.
- Work is marked completed because a visit or invoice is finished.
- Tenant availability is stale by the time the contractor responds.
- The contractor cancels, the resident is not told, or access instructions never reach the operative.
- One system owns the appointment while another owns the original issue.
- Approval, parts or specialist access have no explicit owner or due date.
- Repeated resident contact creates duplicates rather than updating the same case.
- Housing circumstances change while an old risk classification remains in force.

These are failure mechanisms to investigate and test, not measured frequencies.

## Regulatory relevance

English landlords retain repair and safety responsibilities; automation does not transfer those duties. [GOV.UK repairs guidance](https://www.gov.uk/private-renting/repairs) identifies landlord responsibilities including structure, installations and common areas.

Current [Awaab's Law guidance](https://www.gov.uk/government/publications/awaabs-law-guidance-for-social-landlords/awaabs-law-guidance-for-social-landlords-timeframes-for-repairs-in-the-social-rented-sector) includes a damaged-roof/scaffolding example and separates immediate safety work from preventative work. It applies to relevant English social housing; do not apply its clocks automatically to private lettings. Detailed policy boundaries are in docs/19.

## Value without invented savings

No reliable universal estimate of administrative minutes per repair, no-access cost or RepairFlow ROI was established. Vendor savings claims are sales evidence, not our performance.

Measure:

| Metric | Definition |
|---|---|
| Human coordination minutes | Time spent reading, chasing, scheduling and correcting each case |
| Unowned wait | Hours with a blocker but no owner/deadline |
| Dependency recovery delay | Time from prerequisite confirmation to next valid action |
| No-access rate | No-access attendances / planned attendances |
| Repeat contact | Resident/contractor contacts per case, separated by channel |
| False resolution | Reopened unresolved-defect cases / resolved cases |
| Safety | Missed escalations and inappropriate actions, with incident review |
| Cost | Model + voice + research + infrastructure + human review per case |

Economic model for a pilot:

`net monthly value = measured hours avoided × loaded hourly staff cost + evidenced avoidable visit costs − service costs − added review/correction costs`.

Do not count saved staff time as cash savings unless it actually reduces cost or releases useful capacity. Do not count all elapsed repair days as staff hours.

## Pilot design

Use one agency and one trade cluster. Establish baseline on consecutive cases, stratifying emergency/routine and single/multi-visit. Run shadow mode first; then bounded approvals. Report medians and tail delays, small-sample uncertainty and safety exceptions. Interview tenants about communication, not only managers about speed.
