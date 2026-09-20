import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  cancelAppointment,
  cancelCase,
  decideActionApproval,
  reopenCase,
  resumeCase,
  submitFieldUpdate,
} from "@/api/endpoints";
import type {
  CancelCaseRequest,
  FieldUpdateRequest,
  ReopenCaseRequest,
  ResumeCaseRequest,
} from "@/api/types";
import { caseDetailQueryKey } from "@/hooks/use-case-detail";
import { useAuthedCreds } from "@/lib/auth-context";

/** Every lifecycle action needs the case's current `version` for optimistic
 * concurrency (a stale version -> the backend rejects with a conflict, and
 * ApiError.status carries that through to the toast here) and invalidates
 * both this case's detail query and the list/dashboard so status changes
 * are visible everywhere immediately instead of waiting for the next poll
 * tick. */
function useInvalidateAfterAction(caseId: string) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: caseDetailQueryKey(caseId) });
    void queryClient.invalidateQueries({ queryKey: ["cases"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard-metrics"] });
    void queryClient.invalidateQueries({ queryKey: ["case-events", caseId] });
  };
}

export function useResumeCase(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateAfterAction(caseId);
  return useMutation({
    mutationFn: (body: ResumeCaseRequest) => resumeCase(creds, caseId, body),
    onSuccess: () => {
      invalidate();
      toast.success("Case resumed");
    },
    onError: (error: Error) => toast.error(`Could not resume case: ${error.message}`),
  });
}

export function useReopenCase(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateAfterAction(caseId);
  return useMutation({
    mutationFn: (body: ReopenCaseRequest) => reopenCase(creds, caseId, body),
    onSuccess: () => {
      invalidate();
      toast.success("Case reopened");
    },
    onError: (error: Error) => toast.error(`Could not reopen case: ${error.message}`),
  });
}

export function useCancelCase(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateAfterAction(caseId);
  return useMutation({
    mutationFn: (body: CancelCaseRequest) => cancelCase(creds, caseId, body),
    onSuccess: () => {
      invalidate();
      toast.success("Case cancelled");
    },
    onError: (error: Error) => toast.error(`Could not cancel case: ${error.message}`),
  });
}

/** Approve/reject one ActionRecord that's sitting in AWAITING_APPROVAL --
 * see api/endpoints.ts's decideActionApproval and DecisionCard.tsx, which
 * is the only caller. Both outcomes need the case-detail query invalidated
 * (approval either applies the write immediately or records the rejection,
 * either way the snapshot's pending_actions/version has changed). */
export function useDecideApproval(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateAfterAction(caseId);
  return useMutation({
    mutationFn: (vars: {
      actionId: string;
      expectedCaseVersion: number;
      approve: boolean;
      reason: string;
      actionPayloadHash: string;
    }) =>
      decideActionApproval(creds, vars.actionId, {
        action_id: vars.actionId,
        expected_case_version: vars.expectedCaseVersion,
        approve: vars.approve,
        reason: vars.reason,
        action_payload_hash: vars.actionPayloadHash,
      }),
    onSuccess: (_data, vars) => {
      invalidate();
      toast.success(vars.approve ? "Action approved" : "Action rejected");
    },
    onError: (error: Error) => toast.error(`Could not record decision: ${error.message}`),
  });
}

/** Cancelling an appointment is the whole "reschedule" flow -- see
 * api/endpoints.ts's cancelAppointment docstring. */
export function useCancelAppointment(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateAfterAction(caseId);
  return useMutation({
    mutationFn: (vars: { appointmentId: string; reason: string }) =>
      cancelAppointment(creds, vars.appointmentId, vars.reason),
    onSuccess: () => {
      invalidate();
      toast.success("Appointment cancelled — the coordinator will propose a new visit");
    },
    onError: (error: Error) => toast.error(`Could not cancel appointment: ${error.message}`),
  });
}

/** Record what a contractor or tenant actually told the operator.
 *
 * Replaces the retired "simulate an observation" demo mutation. Same
 * domain services underneath; the difference is that this records a real
 * report relayed by a named person at a recorded time, rather than
 * asserting a fictional event. See api/endpoints.ts's submitFieldUpdate
 * and RecordFieldUpdateDialog.tsx. */
export function useSubmitFieldUpdate(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateAfterAction(caseId);
  return useMutation({
    mutationFn: (body: FieldUpdateRequest) => submitFieldUpdate(creds, caseId, body),
    onSuccess: () => {
      invalidate();
      toast.success("Update recorded on the case");
    },
    onError: (error: Error) => toast.error(`Could not record that update: ${error.message}`),
  });
}
