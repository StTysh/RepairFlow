import { useState } from "react";
import { createApiClient, type OperatorCredentials } from "../api/client";
import type { components } from "../api/schema";
import { formatDateTime, titleCase } from "../lib/format";

type ActionRecord = components["schemas"]["ActionRecord"];
type CaseSnapshot = components["schemas"]["CaseSnapshot"];

function actionSummary(action: ActionRecord["proposal"]["action"]): string {
  switch (action.kind) {
    case "APPLY_TRIAGE":
      return `Triage: ${action.issue_description} (${titleCase(action.suggested_trade)})`;
    case "ADD_PREREQUISITE":
      return `Add prerequisite: ${titleCase(action.prerequisite_kind)} (${action.reason})`;
    case "SCHEDULE_VISIT":
      return `Schedule visit for work order ${action.work_order_id.slice(0, 8)}`;
    case "DISCOVER_CONTRACTORS":
      return `Discover ${titleCase(action.trade)} contractors near ${action.postcode}`;
    case "ACCEPT_REPORT":
      return `Accept report outcome: ${titleCase(action.outcome)}`;
    case "REQUEST_INFORMATION":
      return `Request information: ${action.questions.join(", ")}`;
    case "REQUEST_CONFIRMATION":
      return "Request tenant confirmation";
    case "RESOLVE_CASE":
      return "Resolve case";
    case "ESCALATE":
      return `Escalate (${action.reason_code}): ${action.operator_message}`;
    case "WAIT":
      return `Wait: ${action.reason} (for ${action.waiting_for})`;
    default:
      return "Unrecognized action";
  }
}

function DecisionRow({
  action,
  creds,
  caseVersion,
  onDecided,
}: {
  action: ActionRecord;
  creds: OperatorCredentials;
  caseVersion: number;
  onDecided: () => void;
}) {
  const [reason, setReason] = useState("");
  const [limitPence, setLimitPence] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(approve: boolean) {
    setBusy(approve ? "approve" : "reject");
    setError(null);
    try {
      const client = createApiClient(creds);
      const { error: apiError } = await client.POST("/api/v1/actions/{action_id}/approval", {
        params: { path: { action_id: action.id } },
        body: {
          action_id: action.id,
          expected_case_version: caseVersion,
          approve,
          authorized_limit_pence: limitPence ? Number(limitPence) : null,
          reason: reason || (approve ? "Approved by operator." : "Rejected by operator."),
          action_payload_hash: action.payload_hash,
        },
      });
      if (apiError) {
        setError(typeof apiError === "object" && apiError && "error" in apiError ? JSON.stringify(apiError) : "Decision failed.");
        return;
      }
      onDecided();
    } catch {
      setError("Could not reach the API.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-amber-400">Awaiting approval · {titleCase(action.kind)}</div>
          <p className="mt-1 text-sm text-slate-200">{actionSummary(action.proposal.action)}</p>
          <p className="mt-1 text-xs text-slate-400">{action.proposal.decision_summary}</p>
        </div>
        <span className="whitespace-nowrap text-[11px] text-slate-500">{formatDateTime(action.created_at)}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          type="text"
          placeholder="Reason (optional)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="min-w-40 flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600"
        />
        <input
          type="number"
          placeholder="Authorized limit (pence)"
          value={limitPence}
          onChange={(e) => setLimitPence(e.target.value)}
          className="w-40 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600"
        />
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => decide(true)}
          className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy === "approve" ? "Approving…" : "Approve"}
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => decide(false)}
          className="rounded bg-rose-600/80 px-3 py-1 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
        >
          {busy === "reject" ? "Rejecting…" : "Reject"}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-rose-400">{error}</p>}
    </div>
  );
}

export function DecisionCard({
  snapshot,
  creds,
  onDecided,
}: {
  snapshot: CaseSnapshot;
  creds: OperatorCredentials;
  onDecided: () => void;
}) {
  const pending = snapshot.pending_actions.filter((a) => a.state === "AWAITING_APPROVAL");

  if (pending.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-500">
        No decisions awaiting approval.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {pending.map((action) => (
        <DecisionRow
          key={action.id}
          action={action}
          creds={creds}
          caseVersion={snapshot.case.version}
          onDecided={onDecided}
        />
      ))}
    </div>
  );
}
