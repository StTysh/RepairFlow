import { AlertTriangle, Ban, Check } from "lucide-react";
import { useMemo } from "react";
import { Card } from "@/components/fixi/AppShell";
import type { CaseSnapshot, Dependency, WorkOrder } from "@/api/types";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type StepTone = "done" | "current" | "upcoming" | "blocked" | "skipped";

interface Step {
  key: "reported" | "diagnosing" | "on_site" | "follow_up" | "resolved";
  label: string;
  tone: StepTone;
  note?: string;
}

type VisitOutcomeValue = "COMPLETED" | "BLOCKED" | "NO_ACCESS" | "FAILED" | "UNKNOWN";
const ATTENDED_OUTCOMES = new Set<VisitOutcomeValue>(["COMPLETED", "BLOCKED"]);
const OUTCOME_LABEL: Record<string, string> = {
  NO_ACCESS: "no access",
  FAILED: "failed",
  UNKNOWN: "outcome unclear",
};

/**
 * Derives the reference UI's 5-step progression -- Reported, Diagnosing,
 * Contractor on site, Follow up, Resolved -- from real fields on the case
 * snapshot. Never a scripted sequence: every rule below names the exact
 * field(s) it reads, and a case that doesn't walk a straight line
 * (escalated, cancelled, blocked by a dependency, needs a second visit)
 * gets an honest, distinct rendering rather than being squeezed onto the
 * happy path.
 */
export function deriveCaseProgress(snapshot: CaseSnapshot): {
  steps: Step[];
  banner: { tone: "escalated" | "cancelled"; text: string } | null;
} {
  const c = snapshot.case;
  const workOrders = snapshot.work_orders;
  const appointments = snapshot.appointments;
  const dependencies = snapshot.dependencies;

  // Step 1 -- Reported. A case row existing at all *is* "reported"; there
  // is no "not yet reported" state this page can ever be showing.
  const reported: StepTone = "done";

  // Step 2 -- Diagnosing. Done once the coordinator has produced at least
  // one scoped work order (WorkOrder rows are created once triage decides
  // what work is actually needed -- backend/app/domain/services.py).
  // Before that, whatever the case status says, the case is still being
  // triaged.
  const diagnosingDone = workOrders.length > 0;

  // Step 3 -- Contractor on site. VisitOutcome is not a boolean (backend
  // schemas.py VisitOutcome: COMPLETED | BLOCKED | NO_ACCESS | FAILED |
  // UNKNOWN). COMPLETED/BLOCKED mean a contractor genuinely attended and
  // something was observed; NO_ACCESS/FAILED/UNKNOWN mean an attempt was
  // made but nobody actually got on site. Counting those as "done" would
  // render a failed attempt as a successful visit -- exactly the fake
  // progress this indicator must not show. So this step is "done" only
  // once some appointment's visit_outcome is COMPLETED or BLOCKED.
  const attended = appointments.filter(
    (a) => a.visit_outcome !== null && ATTENDED_OUTCOMES.has(a.visit_outcome as VisitOutcomeValue),
  );
  const failedAttempts = appointments.filter(
    (a) => a.visit_outcome !== null && !ATTENDED_OUTCOMES.has(a.visit_outcome as VisitOutcomeValue),
  );
  const onSiteDone = attended.length > 0;
  const hasBookedVisit = appointments.some(
    (a) => a.status === "CONFIRMED" || a.status === "PENDING",
  );

  // Step 4 -- Follow up. "Current" while the repair remains unresolved
  // after a visit outcome was recorded, or the case has reached
  // AWAITING_CONFIRMATION (the state machine's own name for "waiting on
  // the tenant to confirm the fix" -- docs/07), or the tenant has already
  // confirmed but the case hasn't been formally closed out yet
  // (issue.tenant_resolution_confirmed_at).
  const tenantConfirmed = snapshot.issue.tenant_resolution_confirmed_at !== null;

  // Step 5 -- Resolved. Mirrors case.status directly: resolution is a
  // coordinator/approval decision (CLAUDE.md "no closure inferred from
  // silence"), never inferred here from elapsed time or a lack of events.
  const resolvedDone = c.status === "RESOLVED";

  const diagnosing: StepTone = diagnosingDone ? "done" : "current";
  const onSite: StepTone = onSiteDone ? "done" : diagnosingDone ? "current" : "upcoming";
  let followUp: StepTone;
  if (resolvedDone) followUp = "done";
  else if (onSiteDone || c.status === "AWAITING_CONFIRMATION" || tenantConfirmed)
    followUp = "current";
  else followUp = "upcoming";
  const resolved: StepTone = resolvedDone ? "done" : "upcoming";

  const steps: Step[] = [
    { key: "reported", label: "Reported", tone: reported },
    { key: "diagnosing", label: "Diagnosing", tone: diagnosing },
    { key: "on_site", label: "Contractor on site", tone: onSite },
    { key: "follow_up", label: "Follow up", tone: followUp },
    { key: "resolved", label: "Resolved", tone: resolved },
  ];
  const stepByKey = (key: Step["key"]) => steps.find((s) => s.key === key)!;

  // Note: a work order stuck BLOCKED or an OPEN dependency means something
  // on this case cannot proceed until another work order clears it (the
  // scaffold-before-roof-repair story in WorkGraph.tsx) -- surface that on
  // whichever step is currently active rather than leaving the dot
  // unexplained.
  const anyBlockedWorkOrder = workOrders.some((w: WorkOrder) => w.status === "BLOCKED");
  const anyOpenDependency = dependencies.some((d: Dependency) => d.status === "OPEN");
  if (anyBlockedWorkOrder || anyOpenDependency) {
    const target = stepByKey(diagnosingDone ? "on_site" : "diagnosing");
    if (target.tone !== "done") target.note = "Blocked by a dependency on another work order.";
  }

  // Note: a failed/no-access attempt is real information, not "nothing
  // happened yet". attempt_number is how a genuine second-visit case is
  // told apart from a first attempt that simply hasn't happened.
  if (!onSiteDone && failedAttempts.length > 0) {
    const latest = [...failedAttempts].sort((a, b) => b.start_at.localeCompare(a.start_at))[0]!;
    const label = OUTCOME_LABEL[latest.visit_outcome ?? "UNKNOWN"] ?? "unresolved";
    stepByKey("on_site").note =
      `Attempt ${latest.attempt_number} on ${formatDate(latest.start_at)}: ${label}.` +
      (hasBookedVisit ? " A further visit is booked." : "");
  } else if (!onSiteDone && hasBookedVisit) {
    stepByKey("on_site").note = "Visit booked, not yet attended.";
  } else if (onSiteDone && !resolvedDone && attended.length > 1) {
    stepByKey("on_site").note = `${attended.length} visits attended.`;
  }

  if (tenantConfirmed && !resolvedDone) {
    stepByKey("follow_up").note = "Tenant has confirmed the repair; awaiting case closure.";
  }

  // Not every case walks this line -- escalation and cancellation are
  // overlays on top of whatever real progress already happened, not a
  // sixth/seventh step squeezed onto the same row.
  let banner: { tone: "escalated" | "cancelled"; text: string } | null = null;

  if (c.status === "CANCELLED") {
    banner = { tone: "cancelled", text: "This case was cancelled. No further steps will happen." };
    for (const s of steps) {
      if (s.tone === "current" || s.tone === "upcoming") s.tone = "skipped";
    }
  } else if (c.status === "ESCALATED") {
    banner = {
      tone: "escalated",
      text: c.escalation_reason
        ? `Escalated, held for an operator: ${c.escalation_reason}`
        : "Escalated, held for an operator.",
    };
    const current = steps.find((s) => s.tone === "current");
    if (current) current.tone = "blocked";
  }

  return { steps, banner };
}

function StepDot({ tone }: { tone: StepTone }) {
  switch (tone) {
    case "done":
      return (
        <span className="relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-timeline-done text-primary-foreground">
          <Check className="h-3 w-3" strokeWidth={3} />
        </span>
      );
    case "current":
      return (
        <span className="relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 border-timeline-current bg-card">
          <span className="h-2 w-2 rounded-full bg-timeline-current" />
        </span>
      );
    case "blocked":
      return (
        <span className="relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 border-status-red-foreground bg-status-red text-status-red-foreground">
          <AlertTriangle className="h-3 w-3" strokeWidth={2.5} />
        </span>
      );
    case "skipped":
      return (
        <span className="relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 border-dashed border-muted-foreground/40 bg-card text-muted-foreground">
          <Ban className="h-2.5 w-2.5" />
        </span>
      );
    case "upcoming":
    default:
      return (
        <span className="relative z-10 h-5 w-5 shrink-0 rounded-full border-2 border-timeline-future bg-card" />
      );
  }
}

export function CaseProgress({ snapshot }: { snapshot: CaseSnapshot }) {
  const { steps, banner } = useMemo(() => deriveCaseProgress(snapshot), [snapshot]);

  return (
    <Card className="mt-4 px-4 py-4 sm:px-6">
      {banner && (
        <div
          className={cn(
            "mb-4 flex items-start gap-2 rounded-lg border px-3 py-2 text-xs leading-relaxed",
            banner.tone === "escalated"
              ? "border-status-red-foreground/25 bg-status-red/40 text-status-red-foreground"
              : "border-border bg-muted text-muted-foreground",
          )}
        >
          {banner.tone === "escalated" ? (
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          ) : (
            <Ban className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          )}
          <span>{banner.text}</span>
        </div>
      )}
      <ol className="flex items-start">
        {steps.map((s, i) => (
          <li key={s.key} className="relative flex flex-1 flex-col items-center px-1 text-center">
            {i < steps.length - 1 && (
              <span
                className={cn(
                  "absolute left-1/2 top-2.5 h-px w-full",
                  s.tone === "done" ? "bg-timeline-done" : "bg-timeline-future",
                )}
              />
            )}
            <StepDot tone={s.tone} />
            <div
              className={cn(
                "mt-1.5 text-xs font-medium",
                (s.tone === "upcoming" || s.tone === "skipped") && "text-muted-foreground",
              )}
            >
              {s.label}
            </div>
            {s.note && (
              <div className="mt-0.5 max-w-[10rem] text-[10px] leading-snug text-muted-foreground">
                {s.note}
              </div>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}
