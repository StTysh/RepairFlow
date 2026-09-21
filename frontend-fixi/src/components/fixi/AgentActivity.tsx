import {
  AlertTriangle,
  ArrowRight,
  Brain,
  CheckCircle2,
  Clock,
  Eye,
  Hourglass,
  UserCheck,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { CaseFlow, RunDetail } from "@/components/fixi/CaseFlow";
import { useCaseEvents } from "@/hooks/use-case-events";
import { useCaseRuns } from "@/hooks/use-case-runs";
import type { CaseSnapshot, OrchestrationRun } from "@/api/types";
import { formatDateTime, formatRelative, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

/** What the coordinator is doing right now.
 *
 * The system had no representation of "waiting" at all. A `Wait` action
 * with no follow-up timer writes nothing durable -- the ActionRecord goes
 * straight to SUCCEEDED and disappears -- so a case correctly waiting on a
 * contractor's report looked exactly like a case nobody was thinking
 * about: status ACTIVE, no pending action, no due job. That is the single
 * most confusing thing about watching this system work, and it is what
 * this banner exists to fix.
 *
 * Every branch below is derived from a real field. Nothing is guessed: if
 * we cannot say what it is waiting for, it says so rather than inventing a
 * reason. */
type AgentState = {
  tone: "thinking" | "approval" | "waiting" | "escalated" | "closed";
  icon: typeof Brain;
  label: string;
  detail: string;
};

function deriveAgentState(snapshot: CaseSnapshot): AgentState {
  const { case: c, pending_actions, appointments, work_orders } = snapshot;

  if (snapshot.agent_active) {
    return {
      tone: "thinking",
      icon: Brain,
      label: "Thinking",
      detail: "The coordinator is reading the case and deciding what to do next.",
    };
  }

  const awaiting = pending_actions.find((a) => a.state === "AWAITING_APPROVAL");
  if (awaiting) {
    return {
      tone: "approval",
      icon: UserCheck,
      label: "Waiting for you",
      detail: `It has proposed ${titleCase(awaiting.proposal.action.kind)} and cannot proceed until you approve or reject it.`,
    };
  }

  if (c.status === "RESOLVED" || c.status === "CANCELLED") {
    return {
      tone: "closed",
      icon: CheckCircle2,
      label: titleCase(c.status),
      detail: "No further action is planned on this case.",
    };
  }

  if (c.status === "ESCALATED") {
    return {
      tone: "escalated",
      icon: AlertTriangle,
      label: "Escalated to a human",
      detail:
        c.escalation_reason ??
        "The coordinator stopped and handed this to a person. Resume it to hand it back.",
    };
  }

  // Waiting. Say what for, using only what the case actually records.
  const nextVisit = appointments.find(
    (a) =>
      (a.status === "CONFIRMED" || a.status === "PENDING") && a.end_at >= new Date().toISOString(),
  );
  if (nextVisit) {
    return {
      tone: "waiting",
      icon: Hourglass,
      label: "Waiting for the visit",
      detail: `Nothing to decide until the appointment on ${formatDateTime(nextVisit.start_at)} has happened.`,
    };
  }

  if (work_orders.some((w) => w.status === "AWAITING_REPORT")) {
    return {
      tone: "waiting",
      icon: Hourglass,
      label: "Waiting for the contractor's report",
      detail: "A visit has taken place. The next decision needs to know how it went.",
    };
  }

  if (c.status === "AWAITING_CONFIRMATION") {
    return {
      tone: "waiting",
      icon: Hourglass,
      label: "Waiting for the tenant to confirm",
      detail: "The work is reported complete; the case closes once the tenant confirms it.",
    };
  }

  if (c.next_follow_up_at) {
    const due = new Date(c.next_follow_up_at);
    const overdue = due.getTime() < Date.now();
    return {
      tone: "waiting",
      icon: Clock,
      label: overdue ? "Follow-up overdue" : "Waiting on a timer",
      detail: overdue
        ? `A follow-up was due ${formatRelative(c.next_follow_up_at)} and has not run.`
        : `It will wake itself ${formatRelative(c.next_follow_up_at)}.`,
    };
  }

  return {
    tone: "waiting",
    icon: Hourglass,
    label: "Waiting for new information",
    detail:
      "Nothing is scheduled and no timer is set — the next decision happens when something is reported.",
  };
}

const TONE_CLASS: Record<AgentState["tone"], string> = {
  thinking: "border-primary/40 bg-primary-soft text-primary",
  approval: "border-status-amber/40 bg-status-amber/10 text-foreground",
  waiting: "border-border bg-muted/40 text-foreground",
  escalated: "border-destructive/40 bg-destructive/10 text-foreground",
  closed: "border-timeline-done/40 bg-timeline-done/10 text-foreground",
};

/** The agent's decision history: one card per coordinator wake.
 *
 * Each round reads left to right the way the system actually works --
 * something woke it, it read a bounded set of records, it proposed one
 * action, and a deterministic policy decided whether that could execute
 * on its own. Showing those four together is the difference between "the
 * AI did something" and "here is why". */
export function AgentActivity({ snapshot }: { snapshot: CaseSnapshot }) {
  const runs = useCaseRuns(snapshot.case.id);
  const events = useCaseEvents(snapshot.case.id);
  const state = deriveAgentState(snapshot);
  const StateIcon = state.icon;
  const items = runs.data?.items ?? [];
  const eventItems = events.data?.items ?? [];
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const selectedRun = items.find((r) => r.id === selectedRunId) ?? null;

  return (
    <div className="space-y-4">
      <Card className={cn("flex items-start gap-3 border p-4", TONE_CLASS[state.tone])}>
        <StateIcon
          className={cn("mt-0.5 h-5 w-5 shrink-0", state.tone === "thinking" && "animate-pulse")}
        />
        <div className="min-w-0">
          <div className="text-section font-semibold">{state.label}</div>
          <p className="mt-0.5 text-xs opacity-90">{state.detail}</p>
        </div>
      </Card>

      <CaseFlow
        snapshot={snapshot}
        events={eventItems}
        runs={items}
        selectedRunId={selectedRunId}
        onSelectRun={setSelectedRunId}
      />

      {events.data?.truncated && (
        <p className="text-micro text-muted-foreground">
          This case has more history than is shown — the oldest events are not loaded. Everything
          above is accurate; it simply does not start at the beginning.
        </p>
      )}

      {selectedRun && <RunDetail run={selectedRun} />}

      <Card className="p-5">
        <div className="flex items-baseline gap-2">
          <h2 className="text-section font-semibold">Decision history</h2>
          <span className="text-xs text-muted-foreground">
            {items.length === 0 ? "" : `${items.length} round${items.length === 1 ? "" : "s"}`}
          </span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Every time the coordinator woke on this case: what it read, what it proposed, and what the
          policy did with it.
        </p>

        {runs.isLoading ? (
          <p className="mt-4 text-xs text-muted-foreground">Loading decision history…</p>
        ) : runs.isError ? (
          <p className="mt-4 text-xs text-muted-foreground">Could not load decision history.</p>
        ) : items.length === 0 ? (
          <p className="mt-4 text-xs text-muted-foreground">
            The coordinator has not run on this case yet. It wakes when something is reported.
          </p>
        ) : (
          <ol className="mt-4 space-y-3">
            {items.map((run, i) => (
              <RunCard key={run.id} run={run} round={items.length - i} />
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}

const RUN_STATE_TONE = {
  SUCCEEDED: "green",
  RUNNING: "blue",
  FAILED: "red",
  SUPERSEDED: "gray",
} as const;

function durationMs(run: OrchestrationRun): number | null {
  if (!run.finished_at) return null;
  return new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
}

function RunCard({ run, round }: { run: OrchestrationRun; round: number }) {
  const ms = durationMs(run);
  const proposal = run.proposal;

  return (
    <li className="rounded-xl border border-border p-3.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-xs font-semibold">Round {round}</span>
        <Pill tone={RUN_STATE_TONE[run.state] ?? "gray"}>{titleCase(run.state)}</Pill>
        {run.policy_result && <Pill tone="gray">{titleCase(run.policy_result)}</Pill>}
        <span className="text-micro text-muted-foreground">
          {formatRelative(run.started_at)}
          {ms !== null && ` · took ${(ms / 1000).toFixed(1)}s`}
        </span>
      </div>

      {/* Trigger -> reads -> proposal, in the order it happened. */}
      <div className="mt-3 space-y-2.5">
        <Step icon={ArrowRight} label="Woke because">
          an event on this case, at snapshot version {run.snapshot_version}
        </Step>

        <Step icon={Eye} label="Read">
          {run.tool_calls.length === 0 ? (
            <span className="text-muted-foreground">
              nothing — it decided from the snapshot alone
            </span>
          ) : (
            <span className="flex flex-wrap gap-1">
              {run.tool_calls.map((t) => (
                <span
                  key={t.id}
                  title={t.error_code ?? undefined}
                  className={cn(
                    "rounded-md border px-1.5 py-px font-mono text-micro",
                    t.outcome === "FAILED"
                      ? "border-destructive/40 text-destructive"
                      : "border-border text-muted-foreground",
                  )}
                >
                  {t.name}
                </span>
              ))}
            </span>
          )}
        </Step>

        <Step icon={Brain} label="Proposed">
          {proposal ? (
            <span>
              <span className="font-medium">{titleCase(proposal.action.kind)}</span>
              {proposal.decision_summary && (
                <span className="text-muted-foreground"> — {proposal.decision_summary}</span>
              )}
            </span>
          ) : (
            <span className="text-muted-foreground">nothing</span>
          )}
        </Step>

        {run.error_code && (
          <Step icon={XCircle} label="Failed">
            <span className="font-mono text-micro text-destructive">{run.error_code}</span>
          </Step>
        )}
      </div>

      <p className="mt-3 border-t border-border pt-2 text-micro text-muted-foreground">
        Model {run.model_id}
      </p>
    </li>
  );
}

function Step({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Brain;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.8} />
      <span className="w-20 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}
