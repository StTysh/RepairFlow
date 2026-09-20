// Hand-written types mirroring the backend's OpenAPI schema (verified
// against a live /openapi.json from the branch that adds these routes --
// see the field notes below for what's confirmed vs. best-effort).
//
// Only the fields the UI actually reads are modelled; anything unused is
// typed loosely (`unknown`/`Record<string, unknown>`) rather than fully
// reproduced, since a generated client isn't in place yet for this app
// (frontend/ has openapi-fetch + a generated schema.ts; frontend-fixi
// doesn't talk to enough of the API yet to justify the codegen step --
// worth revisiting once a future phase adds VoicePanel, which will want
// a lot more of the schema typed precisely).

import type { CaseStatus, Urgency } from "@/lib/fixi-data";

export type Provenance = "LIVE" | "SIMULATED" | "FIXTURE";
export type AppointmentStatus = "PENDING" | "CONFIRMED" | "FINISHED" | "CANCELLED";
export type Trade = "ROOFING" | "SCAFFOLDING" | "PLUMBING" | "ELECTRICAL" | "OTHER";

// --- Case list -------------------------------------------------------------

export interface CaseListItem {
  id: string;
  case_number: number;
  title: string;
  status: CaseStatus;
  version: number;
  updated_at: string;
  property_address: string;
  urgency: Urgency;
  assigned_contractor_name: string | null;
}

export interface CaseListResponse {
  items: CaseListItem[];
  next_cursor: string | null;
}

// --- Case detail / snapshot -------------------------------------------------

export interface Property {
  id: string;
  address_line: string;
  postcode: string;
  timezone: string;
  landlord_reference: string;
  roof_responsibility: string;
  access_notes: string | null;
}

export interface Tenant {
  id: string;
  property_id: string;
  display_name: string;
  phone_e164: string | null;
  email: string | null;
  preferred_channel: string;
  contact_allowed: boolean;
  accessibility_notes: string | null;
}

export interface AssignedContractor {
  id: string;
  display_name: string;
  trade: Trade | null;
  contact_reference: string | null;
  phone: string | null;
  provenance: Provenance;
}

export type WorkOrderKind = "REPAIR" | "SCAFFOLD_INSTALL" | "SCAFFOLD_REMOVE";
export type WorkOrderStatus =
  "READY" | "SCHEDULED" | "IN_PROGRESS" | "AWAITING_REPORT" | "BLOCKED" | "COMPLETED" | "CANCELLED";

export interface WorkOrder {
  id: string;
  case_id: string;
  issue_id: string;
  kind: WorkOrderKind;
  trade: Trade;
  scope: string;
  status: WorkOrderStatus;
  contractor_id: string | null;
  required_for_resolution: boolean;
  /** A quote, not an actual/final invoiced cost -- render labelled as
   * "Quoted", never as "Cost". Null means no quote recorded yet. */
  quote_pence: number | null;
  /** The spend ceiling the operator approved, separate from the quote
   * itself -- render labelled as "Approved limit". */
  approved_limit_pence: number | null;
  completion_report_id: string | null;
  created_at: string;
  updated_at: string;
}

export type DependencyStatus = "OPEN" | "SATISFIED" | "INVALIDATED";

/** A prerequisite-to-dependent edge between two work orders (backend:
 * app/schemas.py Dependency) -- e.g. a scaffold install blocking a roof
 * repair until it's satisfied. Discovered from a contractor report, not
 * invented by the UI; `satisfied_by_report_id` is null until another
 * report satisfies it. Backs WorkGraph.tsx. */
export interface Dependency {
  id: string;
  case_id: string;
  prerequisite_work_order_id: string;
  dependent_work_order_id: string;
  status: DependencyStatus;
  reason: string;
  discovered_from_report_id: string;
  satisfied_by_report_id: string | null;
  created_at: string;
  satisfied_at: string | null;
}

export interface Appointment {
  id: string;
  case_id: string;
  work_order_id: string;
  contractor_id: string;
  slot_id: string;
  start_at: string;
  end_at: string;
  status: AppointmentStatus;
  visit_outcome: string | null;
  connector: string;
  provider_booking_id: string | null;
  action_id: string;
  attempt_number: number;
  availability_revision: number;
  provenance: Provenance;
}

export interface RiskAssessment {
  urgency: Urgency;
  [key: string]: unknown;
}

export type SourceType = "EVENT" | "REPORT" | "TRANSCRIPT" | "VOICE_TOOL" | "WEB" | "OPERATOR";
export type InterpretationStatus = "PENDING" | "APPLIED" | "REVIEW";

export interface EvidenceRef {
  source_type: SourceType;
  source_id: string;
  locator: string | null;
  observed_at: string;
  provenance: Provenance;
}

/** A contractor's reported fact against one appointment -- untrusted until
 * the coordinator interprets it (interpretation_status). Populated by real
 * ElevenLabs contractor calls, or by an operator writing up what a
 * contractor told them via POST /api/v1/cases/{id}/field-updates
 * (kind=CONTRACTOR_REPORT) -- see RecordFieldUpdateDialog.tsx. */
export interface ContractorReport {
  id: string;
  case_id: string;
  work_order_id: string;
  appointment_id: string;
  contractor_id: string;
  text: string;
  observed_at: string;
  received_at: string;
  source_ref: EvidenceRef;
  provenance: Provenance;
  interpretation_status: InterpretationStatus;
  interpreted_action_id: string | null;
}

// --- Pending actions (approvals) --------------------------------------------

export type ActionState =
  | "PROPOSED"
  | "AWAITING_APPROVAL"
  | "PENDING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "UNKNOWN"
  | "REJECTED";

/** The coordinator's typed NextAction union (backend/app/schemas.py) has ~10
 * variants (APPLY_TRIAGE, SCHEDULE_VISIT, ESCALATE, ...), each with its own
 * fields beyond `kind`. Only `kind` is modelled precisely here since that's
 * all the approval card renders -- see DecisionCard.tsx. */
export interface ActionRecordAction {
  kind: string;
  [key: string]: unknown;
}

export interface ActionRecordProposal {
  case_id: string;
  expected_case_version: number;
  trigger_event_id: string;
  decision_summary: string;
  evidence_refs: unknown[];
  action: ActionRecordAction;
}

/** A proposed write the coordinator wants to make. Most auto-apply; ones the
 * policy flags as risky/costly (backend/app/domain/policy.py) sit in state
 * AWAITING_APPROVAL until an operator approves/rejects via
 * POST /actions/{id}/approval -- see DecisionCard.tsx and
 * hooks/use-case-actions.ts's useDecideApproval. */
export interface ActionRecord {
  id: string;
  case_id: string;
  kind: string;
  target_id: string | null;
  idempotency_key: string;
  payload_hash: string;
  proposal: ActionRecordProposal;
  state: ActionState;
}

export interface RepairCase {
  id: string;
  case_number: number;
  property_id: string;
  tenant_id: string;
  status: CaseStatus;
  version: number;
  title: string;
  risk: RiskAssessment;
  created_at: string;
  updated_at: string;
  owner_operator_id: string;
  last_decision_summary: string | null;
  next_follow_up_at: string | null;
  escalation_reason: string | null;
  resume_status: CaseStatus | null;
}

export interface RepairIssue {
  id: string;
  case_id: string;
  description: string;
  location: string;
  started_at: string | null;
  evidence_refs: unknown[];
  tenant_resolution_confirmed_at: string | null;
  unresolved_concerns: string[];
}

export interface CaseEvent {
  id: string;
  case_id: string;
  seq: number;
  type: string;
  occurred_at: string;
  received_at: string;
  actor_type: string;
  actor_id: string;
  provenance: Provenance;
  payload: Record<string, unknown>;
  display_title: string;
  display_description: string;
}

export interface CaseEventsResponse {
  items: CaseEvent[];
  next_cursor: string | null;
}

export type CommPurpose = "INTAKE" | "AVAILABILITY" | "FOLLOW_UP" | "CONTRACTOR";
export type CommDirection = "INBOUND" | "OUTBOUND" | "BROWSER";
export type CommState = "REQUESTED" | "ACTIVE" | "ENDED" | "FAILED";
export type CallOutcomeStatus = "ANSWERED" | "NO_ANSWER" | "VOICEMAIL" | "FAILED" | "UNKNOWN";

export interface TranscriptTurn {
  turn_id: string;
  speaker: "AGENT" | "USER" | "TOOL" | "UNKNOWN";
  text: string;
  time_in_call_secs: number;
  tool_name: string | null;
}

export interface CallOutcome {
  communication_id: string;
  conversation_id: string | null;
  outcome: CallOutcomeStatus;
  tenant_confirms_resolved: boolean | null;
  missing_questions: string[];
  ended_at: string | null;
  /** ElevenLabs' own post-call analysis summary -- real provider output,
   * not generated by this app. May be absent for older calls fetched
   * before this field was captured. */
  transcript_summary: string | null;
}

export interface Recording {
  status: "PENDING" | "AVAILABLE" | "FAILED" | "UNAVAILABLE";
  media_path: string | null;
  media_type: string | null;
  byte_count: number | null;
  sha256: string | null;
  acquired_at: string | null;
  error_code: string | null;
}

export interface Communication {
  id: string;
  case_id: string | null;
  tenant_id: string | null;
  purpose: CommPurpose;
  direction: CommDirection;
  provider_conversation_id: string | null;
  provider_call_sid: string | null;
  state: CommState;
  started_at: string | null;
  ended_at: string | null;
  transcript: TranscriptTurn[];
  outcome: CallOutcome | null;
  recording: Recording;
  provenance: Provenance;
}

// availability / approved_contractors are still explicitly out of scope
// for this phase (VoicePanel/provenance badges would build on them, but
// VoicePanel was never a working feature even in the old frontend -- see
// its own docstring -- so this is deferred, not blocked) -- typed as
// unknown[] here so CaseSnapshot is complete and nothing needs `as any`
// when reading the other fields. work_orders, dependencies, appointments,
// latest_reports and pending_actions ARE typed (WorkGraph / Costs tab /
// DecisionCard approval card / RecordFieldUpdateDialog appointment
// picker).
export interface CaseSnapshot {
  case: RepairCase;
  issue: RepairIssue;
  property: Property;
  tenant: Tenant;
  assigned_contractor: AssignedContractor | null;
  next_appointment: Appointment | null;
  work_orders: WorkOrder[];
  dependencies: Dependency[];
  appointments: Appointment[];
  latest_reports: ContractorReport[];
  communications: Communication[];
  availability: unknown[];
  approved_contractors: unknown[];
  pending_actions: ActionRecord[];
  recent_events: CaseEvent[];
  policy_snapshot: Record<string, unknown>;
  snapshot_version: number;
  agent_active: boolean;
}

export interface CaseDetailResponse {
  snapshot: CaseSnapshot;
  latest_event_seq: number;
}

// --- Dashboard metrics -------------------------------------------------------

export interface DashboardMetrics {
  active: number;
  awaiting_confirmation: number;
  resolved: number;
  escalated: number;
  cancelled: number;
  total: number;
  resolved_this_week: number;
  agent_active: boolean;
  /** Mean hours between a case's created_at and its latest CASE_RESOLVED
   * event, for cases resolved in the last 30 days (backend:
   * DashboardMetricsResponse.avg_resolution_hours). Null when nothing has
   * resolved in that window -- never a fabricated average. */
  avg_resolution_hours: number | null;
  /** "vs 7 days ago" trend, from a documented simplified replay of the
   * CaseEvent log (backend: services.reconstructed_status_counts), not a
   * literal historical audit. Null whenever the comparison would be
   * undefined/misleading -- render no arrow, not a fake one. */
  active_delta_pct: number | null;
  awaiting_confirmation_delta_pct: number | null;
  escalated_delta_pct: number | null;
}

// --- Notifications (bell icon) ------------------------------------------------
//
// GET /api/v1/notifications. Derived entirely from existing ActionRecord
// (AWAITING_APPROVAL) and CaseEvent (CASE_ESCALATED) rows -- no separate
// notification-authoring system and no persisted read-state table (see
// backend/app/api/notifications.py, services.load_notifications).

export type NotificationKind = "AWAITING_APPROVAL" | "CASE_ESCALATED";

export interface NotificationItem {
  id: string;
  kind: NotificationKind;
  case_id: string;
  case_number: number;
  case_title: string;
  occurred_at: string;
  message: string;
  unread: boolean;
}

export interface NotificationsResponse {
  items: NotificationItem[];
  unread_count: number;
}

// --- Upcoming appointments (cross-case) ---------------------------------------
//
// GET /api/v1/appointments/upcoming -- every CONFIRMED appointment starting
// in the future, soonest first, across all cases (backend/app/api/cases.py
// get_upcoming_appointments).

export interface UpcomingAppointmentItem {
  appointment_id: string;
  case_id: string;
  case_number: number;
  case_title: string;
  work_order_id: string;
  trade: Trade;
  start_at: string;
  end_at: string;
  status: AppointmentStatus;
  property_address: string;
  contractor_id: string;
  contractor_name: string;
}

export interface UpcomingAppointmentsResponse {
  items: UpcomingAppointmentItem[];
}

// --- Property history --------------------------------------------------------

export interface PropertyHistoryItem {
  case_id: string;
  case_number: number;
  title: string;
  status: CaseStatus;
  created_at: string;
  resolved_at: string | null;
  outcome: string | null;
  // Same selection rule as CaseListItem.assigned_contractor_name: null
  // until some work order on the case actually has a contractor assigned.
  contractor_name: string | null;
  // Sum of quote_pence across every work order on the case. Named
  // "quoted", not "cost"/"spend": nothing here represents money actually
  // paid. Null when the case has no work orders yet.
  quoted_pence: number | null;
  // The case's "primary" trade, for property-history grouping. Null when
  // the case has no work orders yet.
  trade: Trade | null;
}

export interface PropertyHistoryResponse {
  property_id: string;
  items: PropertyHistoryItem[];
}

// --- Property stats (charts) --------------------------------------------------

export interface TradeQuoteBreakdown {
  trade: Trade;
  quoted_pence: number;
  // This trade's share of quoted_pence across all trades for the
  // property, 0-100. Real computed value, 0 when the property has no
  // quoted work at all.
  percentage: number;
}

export interface YearlyQuoteTotal {
  year: number;
  quoted_pence: number;
}

export interface RecurringIssue {
  trade: Trade;
  occurrence_count: number;
  last_occurred_at: string;
}

export interface PropertyStatsResponse {
  property_id: string;
  // Count of cases currently CaseStatus.ACTIVE for this property -- the
  // same strict reading DashboardMetricsResponse uses, not a broader
  // "still open" definition spanning AWAITING_CONFIRMATION/ESCALATED too.
  active_count: number;
  total_count: number;
  quoted_by_trade: TradeQuoteBreakdown[];
  quoted_by_year: YearlyQuoteTotal[];
  recurring_issues: RecurringIssue[];
  build_year: number | null;
}

// --- Demo / intake ------------------------------------------------------------

/** One row of GET /api/v1/properties (backend/app/api/properties.py's
 * PropertyListItem). Replaced the demo seed-reference shape, which
 * carried a single `tenant_id`/`tenant_name` because the seeded data
 * happened to have exactly one tenant per property -- the real directory
 * returns a count and the tenants are fetched per property. */
export interface PropertyListItem {
  id: string;
  address_line: string;
  postcode: string;
  landlord_reference: string;
  property_type: string | null;
  bedrooms: number | null;
  build_year: number | null;
  photo_key: string | null;
  timezone: string;
  roof_responsibility: string;
  access_notes: string | null;
  is_archived: boolean;
  open_case_count: number;
  total_case_count: number;
  tenant_count: number;
}

/** GET /api/v1/properties -- the real property directory, which replaced
 * the demo seed-reference endpoint the New Ticket form used to read. */
export interface PropertyListResponse {
  items: PropertyListItem[];
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
}

export type SafetyAnswer = "YES" | "NO" | "UNKNOWN";

export interface SafetyAnswers {
  gas?: SafetyAnswer;
  fire?: SafetyAnswer;
  water_near_electrics?: SafetyAnswer;
  structural_danger?: SafetyAnswer;
  uncontrolled_flood?: SafetyAnswer;
  vulnerability_concern?: SafetyAnswer;
}

/** POST /api/v1/cases -- an operator typing a reported repair into the New
 * Ticket form. A real intake channel (a housing officer taking a report at
 * the counter or on the phone), not a demo shortcut: it goes through the
 * same triage, policy and events as the voice path. */
export interface OperatorIntakeRequest {
  property_id: string;
  tenant_id: string;
  description: string;
  location: string;
  source_text: string;
  category?: Trade | null;
  safety_answers?: SafetyAnswers;
}

export type CommandResultStatus = "APPLIED" | "NOOP" | "PENDING" | "REJECTED" | "UNKNOWN";

export interface CommandResult {
  action_id: string | null;
  status: CommandResultStatus;
  case_version: number;
  event_ids: string[];
  resource_ids: Record<string, string>;
  error: unknown;
}

export interface IntakeResponse {
  case_id: string;
  communication_id: string;
  result: CommandResult;
}

// --- Action approvals -----------------------------------------------------------

/** Body for POST /api/v1/actions/{action_id}/approval. `expected_case_version`
 * comes from the ActionRecord's proposal.expected_case_version and
 * `action_payload_hash` from its payload_hash -- both echoed back so the
 * backend can detect a stale/tampered decision (docs/18). */
export interface ApprovalDecisionRequest {
  action_id: string;
  expected_case_version: number;
  approve: boolean;
  reason: string;
  action_payload_hash: string;
}

export interface ApprovalResponse {
  result: CommandResult;
}

// --- Lifecycle actions ---------------------------------------------------------

export interface CaseVersionResponse {
  case_id: string;
  version: number;
}

export interface ResumeCaseRequest {
  version: number;
  reason: string;
  resolved_hold_evidence: string;
}

export interface ReopenCaseRequest {
  version: number;
  reason: string;
  evidence_refs?: unknown[];
}

export interface CancelCaseRequest {
  version: number;
  reason: string;
}

export interface CancellationRequest {
  appointment_id: string;
  reason: string;
}

export type CancellationStatus = "CANCELLED" | "PENDING" | "REJECTED" | "UNKNOWN";

export interface CancellationOutcome {
  status: CancellationStatus;
  provider_booking_id: string | null;
  reason: string | null;
  provenance: Provenance;
}

export interface AppointmentCancelResponse {
  appointment_id: string;
  outcome: CancellationOutcome;
  case_version: number;
}

// --- Operator-recorded field updates ---------------------------------------
//
// POST /api/v1/cases/{case_id}/field-updates
// (backend/app/api/field_updates.py). A named operator recording what a
// contractor or tenant actually told them -- real second-hand information
// with recorded attribution, not a simulated event. `reported_by` names
// the person who said it; the operator's own identity comes from the
// authenticated session, never from this body.
//
// Mirrors the backend's discriminated union on `kind` exactly, so a
// strict extra-field rejection cannot bite.

export interface ContractorReportUpdate {
  kind: "CONTRACTOR_REPORT";
  appointment_id: string;
  text: string;
  observed_at: string;
  reported_by: string;
}

export interface TenantUpdate {
  kind: "TENANT_UPDATE";
  confirms_resolved: boolean;
  text: string;
  reported_by: string;
}

export interface AttendanceWindowEndedUpdate {
  kind: "ATTENDANCE_WINDOW_ENDED";
  appointment_id: string;
}

export type FieldUpdateRequest =
  ContractorReportUpdate | TenantUpdate | AttendanceWindowEndedUpdate;

export interface ReportSubmitResponse {
  report_id: string;
  result: CommandResult;
}

export interface TenantUpdateResponse {
  communication_id: string;
  result: CommandResult;
}

/** Which variant comes back depends on which `kind` was submitted; all
 * three carry a `result`, which is all any caller needs. */
export type FieldUpdateResponse = ReportSubmitResponse | TenantUpdateResponse | ApprovalResponse;

// --- Messages (display-only, read-only) -------------------------------------
//
// GET /api/v1/cases/{case_id}/messages (backend/app/schemas.py Message).
// Display-only tenant/contractor/operator message thread -- never read by
// the coordinator, not part of CaseSnapshot (CLAUDE.md: chat history is not
// authoritative state). There's no write/send endpoint yet. See
// components/fixi/MessagesPanel.tsx.

export type MessageSenderType = "TENANT" | "CONTRACTOR" | "OPERATOR";

export interface Message {
  id: string;
  case_id: string;
  sender_type: MessageSenderType;
  sender_name: string;
  text: string;
  photo_url: string | null;
  created_at: string;
}

export interface CaseMessagesResponse {
  case_id: string;
  items: Message[];
}
