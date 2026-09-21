import { describe, expect, it } from "vitest";
import type { CaseEvent, CaseSnapshot, OrchestrationRun } from "@/api/types";
import { buildCaseFlow, deriveNow, humaniseEventType, summariseCaseFlow } from "@/lib/case-flow";

// Minimal fixtures. Only the fields buildCaseFlow/deriveNow actually read
// are populated; the rest is cast, because filling ~40 unread fields per
// object would obscure what each test is about.
function snapshot(over: Partial<CaseSnapshot> = {}): CaseSnapshot {
  return {
    case: {
      id: "c1",
      case_number: 7,
      status: "ACTIVE",
      title: "Leak in the bathroom",
      next_follow_up_at: null,
      escalation_reason: null,
    },
    pending_actions: [],
    appointments: [],
    work_orders: [],
    agent_active: false,
    ...over,
  } as unknown as CaseSnapshot;
}

function event(seq: number, type: string, at: string, id = `e${seq}`): CaseEvent {
  return {
    id,
    seq,
    type,
    occurred_at: at,
    display_description: "",
  } as unknown as CaseEvent;
}

function run(id: string, triggerEventId: string, at: string, kind: string): OrchestrationRun {
  return {
    id,
    trigger_event_id: triggerEventId,
    started_at: at,
    model_id: "fixture:test",
    state: "SUCCEEDED",
    tool_calls: [],
    policy_result: "AUTO_APPROVED",
    proposal: {
      decision_summary: `because of ${kind}`,
      evidence_refs: [],
      action: { kind },
    },
  } as unknown as OrchestrationRun;
}

describe("buildCaseFlow", () => {
  it("orders the story by time and ends with the current state", () => {
    const steps = buildCaseFlow(
      snapshot(),
      [
        event(2, "WORK_ORDER_CREATED", "2026-01-02T10:00:00Z"),
        event(1, "CASE_CREATED", "2026-01-01T10:00:00Z"),
      ],
      [],
    );
    expect(steps.map((s) => s.title)).toEqual([
      "Issue reported",
      "Work order raised",
      "Waiting for new information",
    ]);
    expect(steps[steps.length - 1]!.kind).toBe("now");
  });

  it("places a decision immediately after the event that triggered it", () => {
    const steps = buildCaseFlow(
      snapshot(),
      [event(1, "CASE_CREATED", "2026-01-01T10:00:00Z", "trigger-1")],
      [run("r1", "trigger-1", "2026-01-01T10:00:05Z", "ApplyTriage")],
    );
    expect(steps.map((s) => s.kind)).toEqual(["trigger", "decision", "now"]);
    expect(steps[1]!.title).toBe("Apply triage");
    expect(steps[1]!.runId).toBe("r1");
  });

  it("keeps a run whose trigger event is outside the loaded window", () => {
    // The events endpoint is paginated; dropping such a run would
    // silently understate what the agent did.
    const steps = buildCaseFlow(
      snapshot(),
      [event(9, "CONTRACTOR_REPORT_RECEIVED", "2026-01-09T10:00:00Z")],
      [run("r9", "an-event-not-loaded", "2026-01-09T10:00:05Z", "AcceptReport")],
    );
    expect(steps.some((s) => s.runId === "r9")).toBe(true);
  });

  it("draws only the current state when a case has no recorded history", () => {
    // The legacy seeded cases genuinely have no event log. The graph must
    // say so rather than invent a spine.
    const steps = buildCaseFlow(snapshot(), [], []);
    expect(steps).toHaveLength(1);
    expect(steps[0]!.kind).toBe("now");
  });

  it("separates what happened to the case from what the system did", () => {
    const steps = buildCaseFlow(
      snapshot(),
      [
        event(1, "CASE_CREATED", "2026-01-01T10:00:00Z"),
        event(2, "APPOINTMENT_CONFIRMED", "2026-01-02T10:00:00Z"),
      ],
      [],
    );
    expect(steps[0]!.kind).toBe("trigger");
    expect(steps[1]!.kind).toBe("effect");
  });

  it("handles a multi-visit case as successive rounds", () => {
    const steps = buildCaseFlow(
      snapshot(),
      [
        event(1, "CASE_CREATED", "2026-01-01T10:00:00Z", "t1"),
        event(2, "APPOINTMENT_CONFIRMED", "2026-01-02T10:00:00Z"),
        event(3, "CONTRACTOR_REPORT_RECEIVED", "2026-01-03T10:00:00Z", "t3"),
        event(4, "APPOINTMENT_CONFIRMED", "2026-01-05T10:00:00Z"),
        event(5, "WORK_ORDER_COMPLETED", "2026-01-06T10:00:00Z"),
      ],
      [
        run("r1", "t1", "2026-01-01T10:00:05Z", "ApplyTriage"),
        run("r3", "t3", "2026-01-03T10:00:05Z", "ScheduleVisit"),
      ],
    );
    expect(steps.filter((s) => s.kind === "decision")).toHaveLength(2);
    // Two bookings must both survive -- a repeat visit is the whole point.
    expect(steps.filter((s) => s.title === "Visit booked")).toHaveLength(2);
  });
});

describe("deriveNow", () => {
  it("puts an approval ahead of everything else", () => {
    const now = deriveNow(
      snapshot({
        pending_actions: [
          { state: "AWAITING_APPROVAL", proposal: { action: { kind: "ScheduleVisit" } } },
        ],
      } as unknown as Partial<CaseSnapshot>),
    );
    expect(now.tone).toBe("needs-you");
    expect(now.detail).toContain("Schedule visit");
  });

  it("names the contractor when a visit has happened and no report is in", () => {
    const now = deriveNow(
      snapshot({
        work_orders: [{ status: "AWAITING_REPORT" }],
      } as unknown as Partial<CaseSnapshot>),
    );
    expect(now.tone).toBe("waiting");
    expect(now.title).toBe("Waiting for the contractor");
  });

  it("admits when it cannot tell what is being waited on", () => {
    const now = deriveNow(snapshot());
    expect(now.title).toBe("Waiting for new information");
  });

  it("reports a resolved case as done", () => {
    const now = deriveNow(
      snapshot({ case: { status: "RESOLVED" } } as unknown as Partial<CaseSnapshot>),
    );
    expect(now.tone).toBe("done");
  });
});

describe("summariseCaseFlow", () => {
  it("renders the same story as plain text so the copy cannot drift", () => {
    const steps = buildCaseFlow(snapshot(), [event(1, "CASE_CREATED", "2026-01-01T10:00:00Z")], []);
    const text = summariseCaseFlow(steps, "#7 — Leak in the bathroom");
    expect(text).toContain("#7 — Leak in the bathroom");
    expect(text).toContain("2026-01-01  Issue reported");
    expect(text).toContain("Now: Waiting for new information");
  });
});

describe("humaniseEventType", () => {
  it("falls back to readable text for an unknown type", () => {
    // A new EventType must not vanish from the graph.
    expect(humaniseEventType("SOMETHING_NEW_HAPPENED")).toBe("Something new happened");
  });
});
