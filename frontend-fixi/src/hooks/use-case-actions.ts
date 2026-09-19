import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { cancelAppointment, cancelCase, reopenCase, replayCase, resumeCase } from "@/api/endpoints";
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
