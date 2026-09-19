import type { components } from "../api/schema";
import { formatDateTime, titleCase } from "../lib/format";

type CaseSnapshot = components["schemas"]["CaseSnapshot"];

const STATUS_STYLES: Record<string, string> = {
  ACTIVE: "bg-sky-500/15 text-sky-300 border-sky-500/40",
  AWAITING_CONFIRMATION: "bg-violet-500/15 text-violet-300 border-violet-500/40",
  RESOLVED: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  ESCALATED: "bg-rose-500/15 text-rose-300 border-rose-500/40",
  CANCELLED: "bg-slate-600/20 text-slate-400 border-slate-600/40",
};

const URGENCY_STYLES: Record<string, string> = {
  EMERGENCY: "bg-rose-500/15 text-rose-300 border-rose-500/40",
  URGENT: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  ROUTINE: "bg-slate-500/15 text-slate-300 border-slate-500/40",
  UNKNOWN: "bg-slate-700/30 text-slate-400 border-slate-700/50",
};

export function CaseHeader({ snapshot }: { snapshot: CaseSnapshot }) {
  const { case: repairCase, issue } = snapshot;
  const hazardFlags = (
    [
      ["Gas", repairCase.risk.gas],
      ["Fire", repairCase.risk.fire],
      ["Water near electrics", repairCase.risk.water_near_electrics],
      ["Structural danger", repairCase.risk.structural_danger],
      ["Uncontrolled flood", repairCase.risk.uncontrolled_flood],
      ["Vulnerability concern", repairCase.risk.vulnerability_concern],
    ] as const
  ).filter(([, answer]) => answer === "YES" || answer === "UNKNOWN");

  return (
    <div className="border-b border-slate-800 bg-slate-900/60 px-6 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-slate-100">{repairCase.title}</h1>
            <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[repairCase.status] ?? ""}`}>
              {titleCase(repairCase.status)}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${URGENCY_STYLES[repairCase.risk.urgency] ?? ""}`}>
              {titleCase(repairCase.risk.urgency)}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            {issue.location} · v{repairCase.version} · updated {formatDateTime(repairCase.updated_at)}
          </p>
          {repairCase.last_decision_summary && (
            <p className="mt-2 max-w-2xl text-sm text-slate-300">{repairCase.last_decision_summary}</p>
          )}
          {repairCase.escalation_reason && (
            <p className="mt-2 text-sm text-rose-300">Escalated: {repairCase.escalation_reason}</p>
          )}
        </div>
      </div>
      {hazardFlags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {hazardFlags.map(([label, answer]) => (
            <span
              key={label}
              className={`rounded border px-2 py-0.5 text-[11px] font-medium ${
                answer === "YES" ? "border-rose-500/50 bg-rose-500/10 text-rose-300" : "border-amber-500/40 bg-amber-500/10 text-amber-300"
              }`}
            >
              {label}: {answer === "YES" ? "confirmed" : "unknown"}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
