// Typed fetch functions, one per endpoint this UI wires up. Hooks in
// src/hooks call these; components should go through the hooks, not these
// directly (keeps auth/query-key/polling concerns in one layer -- see
// hooks/README notes referenced from the top-level report).

import { request, requestOrNotModified, type OperatorCredentials } from "@/api/client";
import type {
  AppointmentCancelResponse,
  ApprovalDecisionRequest,
  ApprovalResponse,
  CancelCaseRequest,
  CancellationRequest,
  CaseDetailResponse,
  CaseEventsResponse,
  CaseListResponse,
  CaseRunsResponse,
  CaseVersionResponse,
  DashboardMetrics,
  FieldUpdateRequest,
  FieldUpdateResponse,
  IntakeResponse,
  NotificationsResponse,
  OperatorIntakeRequest,
  PropertyHistoryResponse,
  PropertyListResponse,
  PropertyStatsResponse,
  ReopenCaseRequest,
  ResumeCaseRequest,
  RetryRecordingResponse,
  SearchResponse,
  UpcomingAppointmentsResponse,
} from "@/api/types";
// CaseStatus is a UI-facing display concept as much as a wire type (see
// lib/fixi-data.ts), so it's defined there rather than in api/types.ts.
import type { CaseStatus } from "@/lib/fixi-data";

export interface ListCasesParams {
  status?: CaseStatus | undefined;
  property_id?: string | undefined;
  q?: string | undefined;
  limit?: number | undefined;
  cursor?: string | undefined;
  /** Off by default, matching the API: archival sample history must never
   * enter an operational queue uninvited. On, every archival row is
   * badged so it can't be mistaken for work to do. */
  include_archived?: boolean | undefined;
}

export function fetchCaseList(
  creds: OperatorCredentials,
  params: ListCasesParams = {},
): Promise<CaseListResponse> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.property_id) search.set("property_id", params.property_id);
  if (params.q) search.set("q", params.q);
  search.set("limit", String(params.limit ?? 100));
  if (params.cursor) search.set("cursor", params.cursor);
  if (params.include_archived) search.set("include_archived", "true");
  return request<CaseListResponse>(creds, `/api/v1/cases?${search.toString()}`);
}

/** Polls GET /cases/{id} with known_version so the server can answer 304
 * (no body) once nothing has changed. */
export function fetchCaseDetail(creds: OperatorCredentials, caseId: string, knownVersion?: number) {
  return requestOrNotModified<CaseDetailResponse>(creds, `/api/v1/cases/${caseId}`, knownVersion);
}

export function fetchCaseEvents(
  creds: OperatorCredentials,
  caseId: string,
  params: { after_seq?: number; limit?: number } = {},
): Promise<CaseEventsResponse> {
  const search = new URLSearchParams();
  if (params.after_seq) search.set("after_seq", String(params.after_seq));
  search.set("limit", String(params.limit ?? 50));
  return request<CaseEventsResponse>(creds, `/api/v1/cases/${caseId}/events?${search.toString()}`);
}

export function fetchDashboardMetrics(creds: OperatorCredentials): Promise<DashboardMetrics> {
  return request<DashboardMetrics>(creds, "/api/v1/metrics/dashboard");
}

/** Bell-icon feed -- see api/types.ts's NotificationsResponse docstring. */
export function fetchNotifications(creds: OperatorCredentials): Promise<NotificationsResponse> {
  return request<NotificationsResponse>(creds, "/api/v1/notifications");
}

/** Cross-case "next visits" list for the Maintenance sidebar -- see
 * api/types.ts's UpcomingAppointmentsResponse docstring. */
export function fetchUpcomingAppointments(
  creds: OperatorCredentials,
): Promise<UpcomingAppointmentsResponse> {
  return request<UpcomingAppointmentsResponse>(creds, "/api/v1/appointments/upcoming");
}

export function fetchPropertyHistory(
  creds: OperatorCredentials,
  propertyId: string,
): Promise<PropertyHistoryResponse> {
  return request<PropertyHistoryResponse>(creds, `/api/v1/properties/${propertyId}/history`);
}

export function fetchProperties(
  creds: OperatorCredentials,
  params: { q?: string | undefined; limit?: number | undefined; offset?: number | undefined } = {},
): Promise<PropertyListResponse> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  search.set("limit", String(params.limit ?? 200));
  if (params.offset) search.set("offset", String(params.offset));
  return request<PropertyListResponse>(creds, `/api/v1/properties?${search.toString()}`);
}

/** Create a case from an operator-recorded report (POST /api/v1/cases). */
export function submitOperatorIntake(
  creds: OperatorCredentials,
  body: OperatorIntakeRequest,
): Promise<IntakeResponse> {
  return request<IntakeResponse>(creds, "/api/v1/cases", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Record what a contractor or tenant actually told the operator
 * (POST /api/v1/cases/{id}/field-updates). The operator's identity is taken
 * from the authenticated session server-side, so it cannot be spoofed here;
 * `reported_by` inside the body names the person who gave the report. */
export function submitFieldUpdate(
  creds: OperatorCredentials,
  caseId: string,
  body: FieldUpdateRequest,
): Promise<FieldUpdateResponse> {
  return request<FieldUpdateResponse>(creds, `/api/v1/cases/${caseId}/field-updates`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchPropertyStats(
  creds: OperatorCredentials,
  propertyId: string,
): Promise<PropertyStatsResponse> {
  return request<PropertyStatsResponse>(creds, `/api/v1/properties/${propertyId}/stats`);
}

export function resumeCase(
  creds: OperatorCredentials,
  caseId: string,
  body: ResumeCaseRequest,
): Promise<CaseVersionResponse> {
  return request<CaseVersionResponse>(creds, `/api/v1/cases/${caseId}/resume`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function reopenCase(
  creds: OperatorCredentials,
  caseId: string,
  body: ReopenCaseRequest,
): Promise<CaseVersionResponse> {
  return request<CaseVersionResponse>(creds, `/api/v1/cases/${caseId}/reopen`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function cancelCase(
  creds: OperatorCredentials,
  caseId: string,
  body: CancelCaseRequest,
): Promise<CaseVersionResponse> {
  return request<CaseVersionResponse>(creds, `/api/v1/cases/${caseId}/cancel`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Approve or reject an ActionRecord sitting in AWAITING_APPROVAL. The
 * caller supplies expected_case_version/action_payload_hash echoed from
 * that ActionRecord (see ApprovalDecisionRequest) so the backend can
 * reject a stale or tampered decision. */
export function decideActionApproval(
  creds: OperatorCredentials,
  actionId: string,
  body: ApprovalDecisionRequest,
): Promise<ApprovalResponse> {
  return request<ApprovalResponse>(creds, `/api/v1/actions/${actionId}/approval`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Cancelling an appointment IS the reschedule flow (no separate
 * reschedule endpoint): cancel here, then the coordinator proposes a
 * fresh visit through the normal policy/approval path. */
export function cancelAppointment(
  creds: OperatorCredentials,
  appointmentId: string,
  reason: string,
): Promise<AppointmentCancelResponse> {
  const body: CancellationRequest = { appointment_id: appointmentId, reason };
  return request<AppointmentCancelResponse>(creds, `/api/v1/appointments/${appointmentId}/cancel`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Global cross-entity search. The backend has served this since the
 * migration; until 2026-09-21 nothing in the UI called it, so the search box
 * only client-filtered the already-loaded ticket list while its placeholder
 * promised tenants and contractors too. */
export function fetchGlobalSearch(creds: OperatorCredentials, q: string): Promise<SearchResponse> {
  return request<SearchResponse>(creds, `/api/v1/search?q=${encodeURIComponent(q)}`);
}

/** Re-queue the audio/transcript fetch for a call whose recording failed or
 * is still pending. The endpoint has existed since the migration with no UI
 * caller, so a failed fetch was a dead end on screen even though CLAUDE.md
 * requires recordings be persisted and playable. */
export function retryRecording(
  creds: OperatorCredentials,
  communicationId: string,
): Promise<RetryRecordingResponse> {
  return request<RetryRecordingResponse>(
    creds,
    `/api/v1/communications/${communicationId}/retry-recording`,
    { method: "POST" },
  );
}

/** The coordinator's reasoning history for a case: one row per wake, with
 * the tools it read, what it proposed and what policy decided. */
export function fetchCaseRuns(
  creds: OperatorCredentials,
  caseId: string,
  limit = 50,
): Promise<CaseRunsResponse> {
  return request<CaseRunsResponse>(creds, `/api/v1/cases/${caseId}/runs?limit=${limit}`);
}
