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
  CaseMessagesResponse,
  CaseVersionResponse,
  DashboardMetrics,
  DemoIntakeRequest,
  DemoSeedRefs,
  IntakeResponse,
  PropertyHistoryResponse,
  PropertyStatsResponse,
  ReopenCaseRequest,
  ResumeCaseRequest,
  SimulationObservationRequest,
  SimulationObservationResponse,
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

/** Read-only tenant/contractor/operator message thread for a case -- display
 * only, never fed to the coordinator (CLAUDE.md: chat history is not
 * authoritative state). No write/send endpoint exists yet. */
export function fetchCaseMessages(
  creds: OperatorCredentials,
  caseId: string,
): Promise<CaseMessagesResponse> {
  return request<CaseMessagesResponse>(creds, `/api/v1/cases/${caseId}/messages`);
}

export function fetchDashboardMetrics(creds: OperatorCredentials): Promise<DashboardMetrics> {
  return request<DashboardMetrics>(creds, "/api/v1/metrics/dashboard");
}

export function fetchPropertyHistory(
  creds: OperatorCredentials,
  propertyId: string,
): Promise<PropertyHistoryResponse> {
  return request<PropertyHistoryResponse>(creds, `/api/v1/properties/${propertyId}/history`);
}

export function fetchPropertyStats(
  creds: OperatorCredentials,
  propertyId: string,
): Promise<PropertyStatsResponse> {
  return request<PropertyStatsResponse>(creds, `/api/v1/properties/${propertyId}/stats`);
}

export function fetchDemoSeedRefs(creds: OperatorCredentials): Promise<DemoSeedRefs> {
  return request<DemoSeedRefs>(creds, "/api/v1/demo/seed-refs");
}

export function submitDemoIntake(
  creds: OperatorCredentials,
  body: DemoIntakeRequest,
): Promise<IntakeResponse> {
  return request<IntakeResponse>(creds, "/api/v1/demo/intake", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Demo-only: resets this one case back to its just-created state (same id,
 * same case_number) and re-triggers the coordinator -- a repeatable "Play"
 * button for a rehearsed demo case rather than retyping an intake each time. */
export function replayCase(creds: OperatorCredentials, caseId: string): Promise<IntakeResponse> {
  return request<IntakeResponse>(creds, `/api/v1/demo/cases/${caseId}/replay`, {
    method: "POST",
  });
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

/** Demo-only: permanently removes a test/duplicate ticket, unlike Cancel
 * (which just marks it terminal but keeps it around). */
export function deleteCase(
  creds: OperatorCredentials,
  caseId: string,
): Promise<{ cleared: boolean }> {
  return request<{ cleared: boolean }>(creds, `/api/v1/demo/cases/${caseId}`, {
    method: "DELETE",
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

/** Demo-only: records a manually-simulated contractor report / tenant
 * feedback / attendance-window-ended observation, exactly as if it had
 * arrived from a real phone call -- there's no live contractor/tenant
 * channel in this MVP. Submitted with SIMULATED provenance by the backend
 * (backend/app/api/demo.py's demo_simulation_observation), not something
 * this call fabricates itself. See SimulateObservationDialog.tsx. */
export function submitSimulationObservation(
  creds: OperatorCredentials,
  caseId: string,
  body: SimulationObservationRequest,
): Promise<SimulationObservationResponse> {
  return request<SimulationObservationResponse>(
    creds,
    `/api/v1/demo/cases/${caseId}/observations`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}
