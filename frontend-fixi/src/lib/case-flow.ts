import type { CaseEvent, CaseSnapshot, OrchestrationRun } from "@/api/types";

/** Turning a case's history into a readable story.
 *
 * Kept out of the component so the interesting part -- deciding what the
 * nodes ARE -- can be tested without a renderer. The component only lays
 * these out.
 *
 * Three jobs, one graph, per the design agreed 2026-09-21:
 *   decide   the terminal "now" node carries what needs a human
 *   explain  collapsed, the spine reads as a sentence per node
 *   verify   a decision node opens its round's tools/evidence/policy
 *
 * Nothing here invents history. A case with no recorded events produces a
 * short graph that says so, because that is the truth about that case --
 * the legacy seeded cases (#6-#14) genuinely have no event log.
 */

export type FlowNodeKind = "trigger" | "decision" | "effect" | "now";

export type NowTone = "needs-you" | "waiting" | "done" | "escalated" | "thinking";

export interface FlowStep {
  id: string;
  kind: FlowNodeKind;
  /** One line, plain English, readable aloud to a landlord. */
  title: string;
  /** Optional second line with the specifics. */
  detail?: string;
  at?: string;
  /** Present on `decision` steps: the run to open in the detail panel. */
  runId?: string;
  /** Present on `now` steps. */
  tone?: NowTone;
  /** Badge text, e.g. "auto-approved", "needed you". */
  badge?: string;
  /** Which pass of the loop this belongs to.
   *
   * The system works in rounds: something arrives, the agent reads and
   * proposes once, the world changes, then it waits for the next thing.
   * Grouping by round is what makes a long case legible -- a flat
   * chronological strip of 27 nodes tells you the order but not the
   * structure, and you cannot see that the same loop ran nine times. */
  round: number;
}

/** What each event type means to a person, rather than to the schema.
 *
 * Only the types the archive and the live path actually produce are
 * spelled out; anything else falls back to a humanised form of its name,
 * so a new EventType shows up as readable text instead of vanishing. */
const EVENT_TITLE: Record<string, string> = {
  CASE_CREATED: "Issue reported",
  INFORMATION_RECEIVED: "New information came in",
  AVAILABILITY_RECEIVED: "Tenant gave their availability",
  RESEARCH_COMPLETED: "Searched for contractors",
  WORK_ORDER_CREATED: "Work order raised",
  APPOINTMENT_CONFIRMED: "Visit booked",
  APPOINTMENT_CANCELLED: "Visit cancelled",
  APPOINTMENT_RESCHEDULED: "Visit rescheduled",
  APPOINTMENT_WINDOW_ENDED: "Visit window ended",
  CONTRACTOR_REPORT_RECEIVED: "Contractor reported back",
  DEPENDENCY_DISCOVERED: "Blocker found",
  DEPENDENCY_SATISFIED: "Blocker cleared",
  WORK_ORDER_COMPLETED: "Work completed",
  TENANT_CONFIRMATION_RECEIVED: "Tenant confirmed the fix",
  FOLLOW_UP_DUE: "Follow-up came due",
  APPROVAL_DECIDED: "You made a decision",
  CASE_ESCALATED: "Escalated to a person",
  CASE_RESUMED: "Case resumed",
  CASE_RESOLVED: "Case resolved",
  CASE_CANCELLED: "Case cancelled",
  CALL_INITIATED: "Call started",
  CALL_SKIPPED: "Call skipped",
  CALL_ENDED: "Call ended",
  CALL_FAILED: "Call failed",
  RECORDING_AVAILABLE: "Recording available",
  RECORDING_FAILED: "Recording could not be fetched",
  ACTION_FAILED: "An action failed",
  ACTION_UNKNOWN: "An action's outcome is unknown",
  OPERATOR_INFO_REQUESTED: "Information requested from you",
  CASE_EDITED: "Case details edited",
};

/** Events that represent something the system DID, rather than something
 * that happened to it. Drawn as effects so the story alternates
 * "something happened -> the agent decided -> the world changed". */
const EFFECT_EVENTS = new Set([
  "WORK_ORDER_CREATED",
  "APPOINTMENT_CONFIRMED",
  "APPOINTMENT_RESCHEDULED",
  "APPOINTMENT_CANCELLED",
  "DEPENDENCY_DISCOVERED",
  "DEPENDENCY_SATISFIED",
  "WORK_ORDER_COMPLETED",
  "CALL_INITIATED",
  "RECORDING_AVAILABLE",
  "CASE_RESOLVED",
  "CASE_CANCELLED",
  "CASE_ESCALATED",
]);

export function humaniseEventType(type: string): string {
  return (
    EVENT_TITLE[type] ??
    type
      .toLowerCase()
      .replace(/_/g, " ")
      .replace(/^./, (c) => c.toUpperCase())
  );
}

export function humaniseActionKind(kind: string): string {
  return kind
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/^./, (c) => c.toUpperCase());
}

/** The current state, in the same vocabulary AgentActivity's banner uses.
 * Derived only from real fields; when it cannot tell, it says so. */
export function deriveNow(snapshot: CaseSnapshot): {
  tone: NowTone;
  title: string;
  detail: string;
} {
  const { case: c, pending_actions, appointments, work_orders } = snapshot;

  if (snapshot.agent_active) {
    return { tone: "thinking", title: "Thinking", detail: "Deciding what to do next." };
  }
  const awaiting = pending_actions.find((a) => a.state === "AWAITING_APPROVAL");
  if (awaiting) {
    return {
      tone: "needs-you",
      title: "Needs you",
      detail: `${humaniseActionKind(awaiting.proposal.action.kind)} is waiting on your decision.`,
    };
  }
  if (c.status === "RESOLVED") {
    return { tone: "done", title: "Resolved", detail: "Verified fixed, nothing outstanding." };
  }
  if (c.status === "CANCELLED") {
    return { tone: "done", title: "Cancelled", detail: "This case was called off." };
  }
  if (c.status === "ESCALATED") {
    return {
      tone: "escalated",
      title: "With a person",
      detail: c.escalation_reason ?? "Handed to a human to resolve.",
    };
  }
  const now = new Date().toISOString();
  const upcoming = appointments.find(
    (a) => (a.status === "CONFIRMED" || a.status === "PENDING") && a.end_at >= now,
  );
  if (upcoming) {
    return { tone: "waiting", title: "Waiting for the visit", detail: "Booked and not yet due." };
  }
  if (work_orders.some((w) => w.status === "AWAITING_REPORT")) {
    return {
      tone: "waiting",
      title: "Waiting for the contractor",
      detail: "A visit happened; the write-up has not arrived.",
    };
  }
  if (c.status === "AWAITING_CONFIRMATION") {
    return {
      tone: "waiting",
      title: "Waiting for the tenant",
      detail: "Work reported done; closes once the tenant confirms.",
    };
  }
  if (c.next_follow_up_at) {
    return {
      tone: "waiting",
      title: "Waiting on a timer",
      detail: `Wakes itself at ${c.next_follow_up_at}.`,
    };
  }
  return {
    tone: "waiting",
    title: "Waiting for new information",
    detail: "Nothing scheduled and no timer — the next move needs something to be reported.",
  };
}

/** Compose the story.
 *
 * Events are the spine because every real case has them and they are
 * append-only. Runs are attached to the event that triggered them, so a
 * decision appears where it actually happened rather than in a separate
 *列 of its own. */
export function buildCaseFlow(
  snapshot: CaseSnapshot,
  events: CaseEvent[],
  runs: OrchestrationRun[],
): FlowStep[] {
  const ordered = [...events].sort((a, b) => a.seq - b.seq);
  const runsByTrigger = new Map<string, OrchestrationRun>();
  for (const run of runs) runsByTrigger.set(run.trigger_event_id, run);

  const steps: FlowStep[] = [];

  for (const ev of ordered) {
    steps.push({
      round: 0, // assigned below, once the whole sequence is in time order
      id: `event:${ev.id}`,
      kind: EFFECT_EVENTS.has(ev.type) ? "effect" : "trigger",
      title: humaniseEventType(ev.type),
      ...(ev.display_description ? { detail: ev.display_description } : {}),
      at: ev.occurred_at,
    });

    // A run triggered by this event belongs immediately after it: the
    // thing happened, then the agent thought about it.
    const run = runsByTrigger.get(ev.id);
    if (run) {
      const proposal = run.proposal;
      steps.push({
        round: 0,
        id: `run:${run.id}`,
        kind: "decision",
        title: proposal ? humaniseActionKind(proposal.action.kind) : "Considered the case",
        ...(proposal?.decision_summary ? { detail: proposal.decision_summary } : {}),
        at: run.started_at,
        runId: run.id,
        ...(run.policy_result ? { badge: run.policy_result.toLowerCase().replace(/_/g, " ") } : {}),
      });
    }
  }

  // Runs whose trigger event is not in the loaded window still happened,
  // and dropping them would silently understate what the agent did.
  for (const run of runs) {
    if (steps.some((s) => s.runId === run.id)) continue;
    steps.push({
      round: 0,
      id: `run:${run.id}`,
      kind: "decision",
      title: run.proposal ? humaniseActionKind(run.proposal.action.kind) : "Considered the case",
      ...(run.proposal?.decision_summary ? { detail: run.proposal.decision_summary } : {}),
      at: run.started_at,
      runId: run.id,
      ...(run.policy_result ? { badge: run.policy_result.toLowerCase().replace(/_/g, " ") } : {}),
    });
  }

  steps.sort((a, b) => (a.at ?? "").localeCompare(b.at ?? ""));

  // A round is one pass of the loop, and the thing that defines a pass is
  // the agent waking and deciding once -- not an inbound event. Keying on
  // triggers looked right and was wrong: a run can be woken by something
  // the system itself did (a ScheduleVisit woken by WORK_ORDER_CREATED),
  // so two decisions landed in one round and drew on top of each other.
  //
  // So: each decision numbers a round. A trigger belongs to the round it
  // kicks off (look forward), an effect to the round that produced it
  // (look back). That is what makes a column answer "this arrived, the
  // agent concluded this, and these things changed as a result".
  const decisionRound = new Map<string, number>();
  let n = 0;
  for (const step of steps) {
    if (step.kind === "decision") {
      n += 1;
      decisionRound.set(step.id, n);
    }
  }
  const totalRounds = Math.max(n, 1);

  let seen = 0;
  const forward: number[] = steps.map(() => 0);
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const step = steps[i]!;
    if (step.kind === "decision") seen = decisionRound.get(step.id)!;
    forward[i] = seen || totalRounds;
  }
  let back = 0;
  steps.forEach((step, i) => {
    if (step.kind === "decision") back = decisionRound.get(step.id)!;
    step.round =
      step.kind === "decision"
        ? decisionRound.get(step.id)!
        : step.kind === "trigger"
          ? forward[i]!
          : Math.max(back, 1);
  });

  const now = deriveNow(snapshot);
  steps.push({
    id: "now",
    kind: "now",
    title: now.title,
    detail: now.detail,
    tone: now.tone,
    round: totalRounds + 1,
  });

  return steps;
}

/** The same story as plain text, for the "explain it to someone" job.
 * Built from the identical steps so the copy can never drift from the
 * graph the operator is looking at. */
export function summariseCaseFlow(steps: FlowStep[], caseTitle: string): string {
  const lines = [caseTitle, ""];
  for (const s of steps) {
    if (s.kind === "now") {
      lines.push(`Now: ${s.title}${s.detail ? ` — ${s.detail}` : ""}`);
      continue;
    }
    const when = s.at ? `${s.at.slice(0, 10)}  ` : "";
    lines.push(`${when}${s.title}${s.detail ? ` — ${s.detail}` : ""}`);
  }
  return lines.join("\n");
}
