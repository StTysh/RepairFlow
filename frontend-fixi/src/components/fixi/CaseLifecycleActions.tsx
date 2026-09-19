import { useNavigate } from "@tanstack/react-router";
import { Play, Trash2 } from "lucide-react";
import type { CaseStatus } from "@/lib/fixi-data";
import {
  useCancelCase,
  useDeleteCase,
  useReopenCase,
  useReplayCase,
  useResumeCase,
} from "@/hooks/use-case-actions";

/** The real lifecycle action buttons, replacing the mockup's status
 * dropdown (CLAUDE.md decision: no control that writes status directly).
 * Which buttons show depends on the legal transition graph in
 * backend/app/domain/transitions.py:
 *   ACTIVE               -> Cancel
 *   AWAITING_CONFIRMATION -> Cancel
 *   ESCALATED            -> Resume, Cancel
 *   RESOLVED              -> Reopen
 *   CANCELLED             -> (terminal, no actions)
 *
 * Resume/Reopen/Cancel all collect a required "reason" (and Resume also a
 * required "resolved_hold_evidence") via window.prompt() rather than a
 * bespoke modal -- these are rare, low-frequency operator actions, and a
 * blocking prompt is enough for this phase; NewTicketDialog is the one
 * flow that justified a real dialog (more than one field, and it's the
 * primary create action in this screen).
 */
export function CaseLifecycleActions({
  caseId,
  status,
  version,
}: {
  caseId: string;
  status: CaseStatus;
  version: number;
}) {
  const navigate = useNavigate();
  const resume = useResumeCase(caseId);
  const reopen = useReopenCase(caseId);
  const cancel = useCancelCase(caseId);
  const replay = useReplayCase(caseId);
  const deleteTicket = useDeleteCase(caseId);

  const busy =
    resume.isPending ||
    reopen.isPending ||
    cancel.isPending ||
    replay.isPending ||
    deleteTicket.isPending;

  async function handleDelete() {
    if (
      !window.confirm(
        "Permanently delete this ticket? This removes it and everything on it (events, calls, work orders) -- unlike Cancel, this can't be undone.",
      )
    ) {
      return;
    }
    try {
      await deleteTicket.mutateAsync();
      void navigate({ to: "/maintenance" });
    } catch {
      // handled by onError toast
    }
  }

  async function handleReplay() {
    if (
      !window.confirm(
        "Replay this ticket from scratch? This clears its history (events, calls, work orders) and re-triggers the coordinator on the same ticket number.",
      )
    ) {
      return;
    }
    try {
      await replay.mutateAsync();
    } catch {
      // handled by onError toast
    }
  }

  // mutateAsync's rejection is already surfaced via each hook's onError
  // toast (see use-case-actions.ts) -- catch-and-swallow here just avoids
  // an additional unhandled-rejection console entry on top of that toast.
  async function handleResume() {
    const reason = window.prompt("Reason for resuming this case?");
    if (!reason) return;
    const resolved_hold_evidence = window.prompt("What resolved the hold? (brief note)") ?? "";
    try {
      await resume.mutateAsync({ version, reason, resolved_hold_evidence });
    } catch {
      // handled by onError toast
    }
  }

  async function handleReopen() {
    const reason = window.prompt("Reason for reopening this case?");
    if (!reason) return;
    try {
      await reopen.mutateAsync({ version, reason });
    } catch {
      // handled by onError toast
    }
  }

  async function handleCancel() {
    const reason = window.prompt("Reason for cancelling this case?");
    if (!reason) return;
    try {
      await cancel.mutateAsync({ version, reason });
    } catch {
      // handled by onError toast
    }
  }

  const buttonClass =
    "h-9 rounded-lg border border-border bg-card px-3.5 text-sm font-medium shadow-card transition-colors hover:bg-accent disabled:opacity-50";

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className="flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-sm font-medium text-primary-foreground shadow-card transition-colors hover:opacity-90 disabled:opacity-50"
        disabled={busy}
        onClick={() => void handleReplay()}
        title="Reset this ticket to just-created and re-run the coordinator from scratch"
      >
        <Play className="h-4 w-4" />
        Play demo
      </button>
      {status === "ESCALATED" && (
        <button
          type="button"
          className={buttonClass}
          disabled={busy}
          onClick={() => void handleResume()}
        >
          Resume
        </button>
      )}
      {status === "RESOLVED" && (
        <button
          type="button"
          className={buttonClass}
          disabled={busy}
          onClick={() => void handleReopen()}
        >
          Reopen
        </button>
      )}
      {(status === "ACTIVE" || status === "AWAITING_CONFIRMATION" || status === "ESCALATED") && (
        <button
          type="button"
          className={`${buttonClass} text-destructive`}
          disabled={busy}
          onClick={() => void handleCancel()}
        >
          Cancel
        </button>
      )}
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card text-destructive shadow-card transition-colors hover:bg-destructive/10 disabled:opacity-50"
        disabled={busy}
        onClick={() => void handleDelete()}
        title="Permanently delete this ticket"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}
