// Query/mutation hooks for the case-detail surfaces this phase adds:
// case editing, appointment rescheduling, documents and costs.
//
// Deliberately not touching api/endpoints.ts or api/types.ts (ownership
// split for this phase -- see the ticket route's owning agent notes): every
// response shape below is declared locally and every call goes straight
// through `request<T>`/`fetch` against `@/api/client`, same contract those
// files already use.
//
// Uploads and blob previews cannot go through `request<T>`: it
// unconditionally sets `Content-Type: application/json` whenever a body is
// present (see client.ts), which breaks multipart form uploads and isn't
// wanted for a binary GET either. Those two cases use `fetch` directly with
// `authHeader`/`BASE_URL`, throwing the same `ApiError` shape so callers can
// branch on `.status` (413, 409, ...) exactly like every other mutation
// here.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, authHeader, BASE_URL, request, type OperatorCredentials } from "@/api/client";
import type { CaseVersionResponse, Trade } from "@/api/types";
import { caseDetailQueryKey } from "@/hooks/use-case-detail";
import { useAuthedCreds } from "@/lib/auth-context";

async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object") {
      if ("detail" in body && typeof (body as { detail: unknown }).detail === "string") {
        return (body as { detail: string }).detail;
      }
      // The DomainError envelope (backend/app/api/errors.py) is
      // `{ error: { message, code, ... } }`, not `{ detail }` -- read that
      // shape too so a 413/409/422 raised as a DomainError still surfaces
      // its real message instead of a raw JSON dump.
      if ("error" in body) {
        const err = (body as { error: unknown }).error;
        if (err && typeof err === "object" && "message" in err) {
          const message = (err as { message: unknown }).message;
          if (typeof message === "string") return message;
        }
      }
    }
    return JSON.stringify(body);
  } catch {
    return res.statusText;
  }
}

// --- Case edit ---------------------------------------------------------

export interface CaseEditRequest {
  expected_version: number;
  title?: string;
  category?: Trade;
  location?: string;
  description?: string;
  access_notes?: string;
}

function editCase(
  creds: OperatorCredentials,
  caseId: string,
  body: CaseEditRequest,
): Promise<CaseVersionResponse> {
  return request<CaseVersionResponse>(creds, `/api/v1/cases/${caseId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** PATCH /api/v1/cases/{id}. A 409 (stale `expected_version`) is not
 * toasted as a generic failure -- CaseToolbar's Edit dialog shows a
 * dedicated "someone else changed this case" banner with a reload action
 * for that case, so this only toasts everything else. */
export function useEditCase(caseId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CaseEditRequest) => editCase(creds, caseId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: caseDetailQueryKey(caseId) });
      void queryClient.invalidateQueries({ queryKey: ["cases"] });
      toast.success("Case updated");
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 409) return;
      toast.error(`Could not update case: ${error.message}`);
    },
  });
}

// --- Appointment reschedule ---------------------------------------------

export interface RescheduleAppointmentRequest {
  start_at: string;
  end_at: string;
  reason: string;
  arranged_with: string;
}

export interface RescheduleAppointmentResponse {
  previous_appointment_id: string;
  appointment_id: string;
  status: string;
  case_version: number;
  note: string;
}

function rescheduleAppointment(
  creds: OperatorCredentials,
  appointmentId: string,
  body: RescheduleAppointmentRequest,
): Promise<RescheduleAppointmentResponse> {
  return request<RescheduleAppointmentResponse>(
    creds,
    `/api/v1/appointments/${appointmentId}/reschedule`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/** POST /api/v1/appointments/{id}/reschedule. The replacement always comes
 * back PENDING (backend never marks an operator-arranged slot as
 * confirmed) -- see RescheduleDialog.tsx for how that's surfaced. */
export function useRescheduleAppointment(caseId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { appointmentId: string; body: RescheduleAppointmentRequest }) =>
      rescheduleAppointment(creds, vars.appointmentId, vars.body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: caseDetailQueryKey(caseId) });
      void queryClient.invalidateQueries({ queryKey: ["upcoming-appointments"] });
      void queryClient.invalidateQueries({ queryKey: ["cases"] });
    },
    onError: (error: Error) => toast.error(`Could not reschedule the visit: ${error.message}`),
  });
}

// --- Documents ------------------------------------------------------------

export type RecordSubjectType = "PROPERTY" | "CASE" | "CONTRACTOR" | "TENANT";

export interface DocumentRecord {
  id: string;
  subject_type: RecordSubjectType;
  subject_id: string;
  display_name: string;
  content_type: string;
  size_bytes: number;
  description: string | null;
  uploaded_by: string;
  uploaded_at: string;
  is_archived: boolean;
}

export interface DocumentListResponse {
  items: DocumentRecord[];
}

function documentsQueryKey(subjectType: RecordSubjectType, subjectId: string) {
  return ["documents", subjectType, subjectId] as const;
}

export function useDocuments(subjectType: RecordSubjectType, subjectId: string) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: documentsQueryKey(subjectType, subjectId),
    queryFn: () =>
      request<DocumentListResponse>(
        creds,
        `/api/v1/documents?subject_type=${subjectType}&subject_id=${subjectId}`,
      ),
  });
}

async function uploadDocument(
  creds: OperatorCredentials,
  params: { subjectType: RecordSubjectType; subjectId: string; file: File; description?: string },
): Promise<DocumentRecord> {
  const form = new FormData();
  form.set("subject_type", params.subjectType);
  form.set("subject_id", params.subjectId);
  if (params.description) form.set("description", params.description);
  form.set("file", params.file);
  const res = await fetch(`${BASE_URL}/api/v1/documents`, {
    method: "POST",
    // No Content-Type here on purpose: the browser has to set the
    // multipart boundary itself from the FormData body.
    headers: { Authorization: authHeader(creds) },
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, await readErrorDetail(res));
  return (await res.json()) as DocumentRecord;
}

export function useUploadDocument(subjectType: RecordSubjectType, subjectId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { file: File; description?: string }) =>
      uploadDocument(creds, { subjectType, subjectId, ...params }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentsQueryKey(subjectType, subjectId) });
      toast.success("File uploaded");
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 413) {
        toast.error(error.message || "That file is too large to upload.");
      } else {
        toast.error(`Could not upload that file: ${error.message}`);
      }
    },
  });
}

export function useDeleteDocument(subjectType: RecordSubjectType, subjectId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      request<void>(creds, `/api/v1/documents/${documentId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentsQueryKey(subjectType, subjectId) });
      toast.success("File deleted");
    },
    onError: (error: Error) => toast.error(`Could not delete that file: ${error.message}`),
  });
}

/** Authenticated blob fetch for inline preview -- the browser will not
 * attach HTTP Basic to a bare `<img src>`/`<iframe src>`, so the bytes have
 * to be fetched by hand and turned into an object URL. Callers own
 * revoking it (on unmount / when swapping documents). */
export async function fetchDocumentObjectUrl(
  creds: OperatorCredentials,
  documentId: string,
  download: boolean,
): Promise<string> {
  const res = await fetch(
    `${BASE_URL}/api/v1/documents/${documentId}/content?download=${download}`,
    { headers: { Authorization: authHeader(creds) } },
  );
  if (!res.ok) throw new ApiError(res.status, await readErrorDetail(res));
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

// --- Costs ---------------------------------------------------------------

export type CostKind = "QUOTE" | "INVOICE" | "ADJUSTMENT";

export interface CostEntryRecord {
  id: string;
  case_id: string;
  work_order_id: string | null;
  kind: CostKind;
  amount_pence: number;
  description: string;
  incurred_at: string;
  recorded_by: string;
  recorded_at: string;
  is_archived: boolean;
}

/** Mirrors backend/app/api/costs.py's `_compute_totals` exactly -- see that
 * module's docstring for what each figure means. `committed_pence` is a
 * current best estimate (invoice-if-present-else-quote, per work order),
 * not a sum of quoted+invoiced -- render it labelled as such. */
export interface CostTotals {
  quoted_pence: number;
  invoiced_pence: number;
  adjustments_pence: number;
  net_pence: number;
  committed_pence: number;
}

export interface CostListResponse {
  items: CostEntryRecord[];
  totals: CostTotals;
}

export interface CostCreateRequest {
  work_order_id?: string | null;
  kind: CostKind;
  amount_pence: number;
  description: string;
  incurred_at: string;
}

export interface CostUpdateRequest {
  work_order_id?: string | null;
  kind?: CostKind;
  amount_pence?: number;
  description?: string;
  incurred_at?: string;
}

function costsQueryKey(caseId: string) {
  return ["case-costs", caseId] as const;
}

export function useCaseCosts(caseId: string) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: costsQueryKey(caseId),
    queryFn: () => request<CostListResponse>(creds, `/api/v1/cases/${caseId}/costs`),
  });
}

/** Every cost mutation invalidates the case-level costs list plus the case
 * detail (the summary quote/limit block reads off the snapshot) plus every
 * screen elsewhere that charts spend off these same rows, so a saved cost
 * shows up immediately rather than on the next unrelated poll tick. */
function useInvalidateCosts(caseId: string) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: costsQueryKey(caseId) });
    void queryClient.invalidateQueries({ queryKey: caseDetailQueryKey(caseId) });
    void queryClient.invalidateQueries({ queryKey: ["property-stats"] });
    void queryClient.invalidateQueries({ queryKey: ["insights"] });
    // Real key is ["reports-summary", filters] (use-reports.ts) -- ["reports"]
    // matched nothing, so the Reports screen never refreshed after a cost
    // was recorded (docs/audit/07, invalidation audit).
    void queryClient.invalidateQueries({ queryKey: ["reports-summary"] });
  };
}

export function useCreateCost(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateCosts(caseId);
  return useMutation({
    mutationFn: (body: CostCreateRequest) =>
      request<CostEntryRecord>(creds, `/api/v1/cases/${caseId}/costs`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      invalidate();
      toast.success("Cost recorded");
    },
    onError: (error: Error) => toast.error(`Could not record that cost: ${error.message}`),
  });
}

export function useUpdateCost(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateCosts(caseId);
  return useMutation({
    mutationFn: (vars: { costId: string; body: CostUpdateRequest }) =>
      request<CostEntryRecord>(creds, `/api/v1/costs/${vars.costId}`, {
        method: "PATCH",
        body: JSON.stringify(vars.body),
      }),
    onSuccess: () => {
      invalidate();
      toast.success("Cost updated");
    },
    onError: (error: Error) => toast.error(`Could not update that cost: ${error.message}`),
  });
}

export function useDeleteCost(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateCosts(caseId);
  return useMutation({
    mutationFn: (costId: string) =>
      request<void>(creds, `/api/v1/costs/${costId}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast.success("Cost deleted");
    },
    onError: (error: Error) => toast.error(`Could not delete that cost: ${error.message}`),
  });
}
