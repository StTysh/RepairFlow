import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  cancelAppointment,
  cancelCase,
  decideActionApproval,
  deleteCase,
  reopenCase,
  replayCase,
  resumeCase,
} from "@/api/endpoints";
import type { CancelCaseRequest, ReopenCaseRequest, ResumeCaseRequest } from "@/api/types";
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

/** Demo-only: permanently removes this ticket. Unlike the other lifecycle
 * actions, there's no case-detail query left to invalidate afterward (the
 * ticket is gone) -- the caller is responsible for navigating away. */
export function useDeleteCase(caseId: string) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteCase(creds, caseId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cases"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-metrics"] });
      toast.success("Ticket deleted");
    },
    onError: (error: Error) => toast.error(`Could not delete ticket: ${error.message}`),
  });
}

export function useReplayCase(caseId: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateAfterAction(caseId);
  return useMutation({
    mutationFn: () => replayCase(creds, caseId),
    onSuccess: () => {
      invalidate();
      toast.success("Replaying from scratch — the coordinator is re-triaging now");
    },
    onError: (error: Error) => toast.error(`Could not replay case: ${error.message}`),
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
