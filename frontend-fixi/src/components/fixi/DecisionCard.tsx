import { AlertTriangle } from "lucide-react";
import { Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { useDecideApproval } from "@/hooks/use-case-actions";
import type { ActionRecord } from "@/api/types";
import { titleCase } from "@/lib/format";

/** Renders every ActionRecord on this case sitting in AWAITING_APPROVAL as
 * an actionable approve/reject card.
 *
 * This is the fix for the incident where `snapshot.pending_actions` was
 * fetched but never read anywhere (typed `unknown[]` in api/types.ts,
 * no route/component touched it) -- a case could sit gated on an operator
 * decision with no visible next step. The caller (the ticket detail route)
 * renders this above the section tabs so it's visible regardless of which
 * tab/section is selected -- it must be impossible to miss. */
export function DecisionCard({
  caseId,
  pendingActions,
}: {
  caseId: string;
  pendingActions: ActionRecord[];
}) {
  const awaiting = pendingActions.filter((a) => a.state === "AWAITING_APPROVAL");
  if (awaiting.length === 0) return null;

  return (
    <Card className="mt-5 border-status-amber-foreground/25 bg-status-amber/40 p-5">
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-status-amber-foreground" />
        <div>
          <h2 className="text-[15px] font-semibold text-status-amber-foreground">
            {awaiting.length === 1
              ? "1 action needs your approval"
              : `${awaiting.length} actions need your approval`}
          </h2>
          <p className="mt-0.5 text-xs text-status-amber-foreground/80">
            The agent proposed this and is waiting on an operator decision before it can continue.
          </p>
        </div>
      </div>
      <ul className="mt-4 space-y-3">
        {awaiting.map((action) => (
          <DecisionRow key={action.id} caseId={caseId} action={action} />
        ))}
      </ul>
    </Card>
  );
}

function DecisionRow({ caseId, action }: { caseId: string; action: ActionRecord }) {
  const decide = useDecideApproval(caseId);

  // expected_case_version comes from THIS proposal (the version the
  // coordinator assumed when it proposed the action), not the case's
  // current/live version -- that's how the backend's staleness check
  // (executor.py:decide_approval) detects "something changed the case
  // since this was proposed, re-check before deciding" rather than always
  // trivially matching whatever the last poll happened to fetch.
  async function handleApprove() {
    try {
      await decide.mutateAsync({
        actionId: action.id,
        expectedCaseVersion: action.proposal.expected_case_version,
        approve: true,
        reason: "Approved by operator.",
        actionPayloadHash: action.payload_hash,
      });
    } catch {
      // handled by onError toast (see use-case-actions.ts)
    }
  }

  async function handleReject() {
    const reason = window.prompt("Reason for rejecting this action?");
    if (!reason) return;
    try {
      await decide.mutateAsync({
        actionId: action.id,
        expectedCaseVersion: action.proposal.expected_case_version,
        approve: false,
        reason,
        actionPayloadHash: action.payload_hash,
      });
    } catch {
      // handled by onError toast (see use-case-actions.ts)
    }
  }

  return (
    <li className="rounded-lg border border-border bg-card p-3">
      <div className="min-w-0">
        <Pill tone="amber">{titleCase(action.proposal.action.kind)}</Pill>
        <p className="mt-1.5 text-[13px] leading-relaxed">{action.proposal.decision_summary}</p>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          disabled={decide.isPending}
          onClick={() => void handleApprove()}
          className="h-8 rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground shadow-card transition-colors hover:opacity-90 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={decide.isPending}
          onClick={() => void handleReject()}
          className="h-8 rounded-lg border border-border bg-card px-3 text-xs font-medium text-destructive shadow-card transition-colors hover:bg-destructive/10 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </li>
  );
}
