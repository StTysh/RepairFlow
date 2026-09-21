import {
  Background,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Brain, Check, CircleDot, Copy, Hourglass, Inbox, UserCheck, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import { Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import type { CaseEvent, CaseSnapshot, OrchestrationRun } from "@/api/types";
import { buildCaseFlow, summariseCaseFlow, type FlowStep, type NowTone } from "@/lib/case-flow";
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

// One column per round of the loop, lanes down the column by kind.
//
// The first version laid every step out in a serpentine grid four wide.
// Order was right and structure was invisible: nothing about a node's
// position told you what it related to, alternate rows read right-to-left,
// and on a 27-step case you could not find which visit belonged to which
// report. Position now means something -- across is time (one column per
// round), down is role (what arrived / what the agent decided / what
// changed) -- so "which appointment came out of that report" is answered
// by looking down the same column.
//
// Spacing is deliberately generous. The canvas pans and zooms, so packing
// nodes tightly buys nothing and costs legibility.
const COLUMN_WIDTH = 300;
const ROW_HEIGHT = 132;
const LABEL_OFFSET = 46;

// The connection points themselves add visual noise at this node density,
// and the routing is legible without them.
const HIDDEN_HANDLE = { opacity: 0, width: 1, height: 1 } as const;

const KIND_ICON = {
  trigger: Inbox,
  decision: Brain,
  effect: Wrench,
  now: CircleDot,
} as const;

const KIND_BORDER = {
  trigger: "border-border",
  decision: "border-primary/50",
  effect: "border-timeline-done/50",
  now: "border-border",
} as const;

const NOW_BORDER: Record<NowTone, string> = {
  "needs-you": "border-status-amber-foreground/60 bg-status-amber/30",
  waiting: "border-border bg-muted/50",
  done: "border-timeline-done/60 bg-timeline-done/10",
  escalated: "border-destructive/60 bg-destructive/10",
  thinking: "border-primary/60 bg-primary-soft",
};

const NOW_ICON: Record<NowTone, typeof Brain> = {
  "needs-you": UserCheck,
  waiting: Hourglass,
  done: Check,
  escalated: CircleDot,
  thinking: Brain,
};

type StepNodeData = { step: FlowStep; selected: boolean };
type StepNodeType = Node<StepNodeData, "step">;

function StepNode({ data }: NodeProps<StepNodeType>) {
  const { step } = data;
  const isNow = step.kind === "now";
  const Icon = isNow ? NOW_ICON[step.tone ?? "waiting"] : KIND_ICON[step.kind];

  return (
    <div
      className={cn(
        "w-56 rounded-xl border-2 bg-card p-3 text-left shadow-card",
        isNow ? NOW_BORDER[step.tone ?? "waiting"] : KIND_BORDER[step.kind],
        data.selected && "ring-2 ring-ring",
        step.runId && "cursor-pointer",
      )}
    >
      {/* Four handles, two of each: an edge into the next round leaves
       * right and arrives left, an edge to the next step in the same
       * round leaves bottom and arrives top. Invisible -- the dots add
       * noise at this density and the routing reads fine without them. */}
      <Handle id="l" type="target" position={Position.Left} style={HIDDEN_HANDLE} />
      <Handle id="t" type="target" position={Position.Top} style={HIDDEN_HANDLE} />
      <div className="flex items-start gap-2">
        <Icon
          className={cn(
            "mt-0.5 h-3.5 w-3.5 shrink-0",
            isNow ? "text-foreground" : "text-muted-foreground",
            step.tone === "thinking" && "animate-pulse",
          )}
          strokeWidth={1.9}
        />
        <div className="min-w-0">
          <div className={cn("text-xs font-semibold", isNow && "text-[13px]")}>{step.title}</div>
          {step.detail && (
            <p className="mt-0.5 line-clamp-3 text-[11px] leading-snug text-muted-foreground">
              {step.detail}
            </p>
          )}
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        {step.badge ? <Pill tone="gray">{step.badge}</Pill> : <span />}
        {step.at && (
          <span className="text-[10px] text-muted-foreground">{formatRelative(step.at)}</span>
        )}
      </div>
      <Handle id="r" type="source" position={Position.Right} style={HIDDEN_HANDLE} />
      <Handle id="b" type="source" position={Position.Bottom} style={HIDDEN_HANDLE} />
    </div>
  );
}

/** A column heading. Not a step -- it carries no handles and takes part in
 * no edge; it exists so a long case reads as "this loop ran nine times"
 * rather than as an undifferentiated wall of cards. */
function RoundLabelNode({ data }: NodeProps<RoundLabelNodeType>) {
  return (
    <div className="pointer-events-none select-none text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
      {data.label}
    </div>
  );
}

type RoundLabelNodeData = { label: string };
type RoundLabelNodeType = Node<RoundLabelNodeData, "roundLabel">;

const nodeTypes = { step: StepNode, roundLabel: RoundLabelNode };

/** The case as a story: what came in, what the agent decided, what
 * changed, and where it stands now.
 *
 * Laid out as a snake (six per row) rather than one long line, so a case
 * with a dozen rounds stays readable without horizontal scrolling. Time
 * runs left to right, then wraps.
 *
 * Reasoning is NOT duplicated here -- clicking a decision node selects it
 * and the round's full detail (tools read, evidence, policy, model,
 * timing) renders below, so the graph stays legible and the audit trail
 * stays complete. */
export function CaseFlow({
  snapshot,
  events,
  runs,
  selectedRunId,
  onSelectRun,
}: {
  snapshot: CaseSnapshot;
  events: CaseEvent[];
  runs: OrchestrationRun[];
  selectedRunId: string | null;
  onSelectRun: (runId: string | null) => void;
}) {
  const steps = useMemo(() => buildCaseFlow(snapshot, events, runs), [snapshot, events, runs]);
  const [copied, setCopied] = useState(false);

  const { nodes, edges, columns } = useMemo(() => {
    // Lay each round out as its own column. Row 0 is what arrived, row 1
    // is what the agent decided about it, rows 2+ are what changed as a
    // result -- so reading down a column answers "and then what?", and
    // reading across answers "how many times did this go round?".
    const rounds = [...new Set(steps.map((s) => s.round))].sort((a, b) => a - b);
    const columnOf = new Map(rounds.map((r, i) => [r, i]));
    // Rows are assigned per column so nothing can ever land on top of
    // anything else, while still keeping the usual case aligned: one
    // trigger at row 0, its decision at row 1, its effects from row 2.
    // A column with two triggers pushes its decision down rather than
    // overlapping -- correctness first, alignment where it is free.
    const triggerCount = new Map<number, number>();
    for (const step of steps) {
      if (step.kind === "trigger") {
        triggerCount.set(step.round, (triggerCount.get(step.round) ?? 0) + 1);
      }
    }
    const cursor = new Map<string, number>();
    const nextRow = (key: string, from: number) => {
      const row = Math.max(cursor.get(key) ?? from, from);
      cursor.set(key, row + 1);
      return row;
    };

    const stepNodes: StepNodeType[] = steps.map((step) => {
      const col = columnOf.get(step.round) ?? 0;
      const decisionRow = Math.max(triggerCount.get(step.round) ?? 1, 1);
      let row: number;
      if (step.kind === "trigger") row = nextRow(`t:${col}`, 0);
      else if (step.kind === "decision") row = nextRow(`d:${col}`, decisionRow);
      else if (step.kind === "now") row = 1;
      else row = nextRow(`e:${col}`, decisionRow + 1);
      return {
        id: step.id,
        type: "step",
        position: { x: col * COLUMN_WIDTH, y: LABEL_OFFSET + row * ROW_HEIGHT },
        data: { step, selected: step.runId != null && step.runId === selectedRunId },
      };
    });

    const labelNodes: RoundLabelNodeType[] = rounds.map((r, i) => ({
      id: `round-label:${r}`,
      type: "roundLabel",
      position: { x: i * COLUMN_WIDTH + 4, y: 0 },
      draggable: false,
      selectable: false,
      data: { label: i === rounds.length - 1 ? "Now" : `Round ${i + 1}` },
    }));

    // Edges follow the same chain as before; only the handles change, so a
    // hop within a column runs top-to-bottom and a hop to the next round
    // runs left-to-right instead of looping back on itself.
    const edges: Edge[] = steps.slice(1).map((step, i) => {
      const prev = steps[i]!;
      const sameColumn = prev.round === step.round;
      return {
        id: `${prev.id}->${step.id}`,
        source: prev.id,
        target: step.id,
        sourceHandle: sameColumn ? "b" : "r",
        targetHandle: sameColumn ? "t" : "l",
        animated: step.kind === "now" && step.tone === "thinking",
        style: { stroke: "var(--border)", strokeWidth: 1.5 },
      };
    });

    return { nodes: [...labelNodes, ...stepNodes], edges, columns: rounds.length };
  }, [steps, selectedRunId]);

  const decisionCount = steps.filter((s) => s.kind === "decision").length;
  // Height follows the DEEPEST column, not the total step count: a case
  // with nine rounds is wide, not tall, and the canvas pans sideways.
  const deepestColumn = Math.max(
    3,
    ...[...new Set(steps.map((s) => s.round))].map((r) => {
      const inRound = steps.filter((s) => s.round === r);
      const triggers = Math.max(inRound.filter((s) => s.kind === "trigger").length, 1);
      const effects = inRound.filter((s) => s.kind === "effect").length;
      return triggers + 1 + effects;
    }),
  );
  const height = Math.min(720, LABEL_OFFSET + 60 + deepestColumn * ROW_HEIGHT);

  async function copySummary() {
    const text = summariseCaseFlow(steps, `#${snapshot.case.case_number} — ${snapshot.case.title}`);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be unavailable (permissions, insecure context).
      // Failing quietly is right: nothing is lost and the graph is still
      // on screen to read from.
    }
  }

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">How this case has gone</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Everything that came in, every decision the agent made, and where it stands now.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void copySummary()}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-accent"
        >
          <Copy className="h-3.5 w-3.5" />
          {copied ? "Copied" : "Copy summary"}
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        <LegendDot className="border-border" label="Came in" />
        <LegendDot className="border-primary/50" label="Agent decided" />
        <LegendDot className="border-timeline-done/50" label="Something changed" />
        {decisionCount > 0 && <span>· click a decision to see its reasoning</span>}
        {columns > 4 && <span>· drag to pan, scroll to zoom</span>}
      </div>

      <div
        className="mt-3 overflow-hidden rounded-lg border border-border bg-background/40"
        style={{ height }}
      >
        <ReactFlow
          key={steps.length}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          // minZoom floor matters more than fitting everything in: a
          // nine-round case is ~2700px wide and fitting that into a panel
          // would shrink the text past reading. Clamp, and let it pan.
          fitViewOptions={{ padding: 0.18, minZoom: 0.55, maxZoom: 1 }}
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, node) => {
            const step = (node.data as StepNodeData).step;
            if (!step.runId) return;
            onSelectRun(step.runId === selectedRunId ? null : step.runId);
          }}
        >
          <Background color="var(--border)" gap={20} />
        </ReactFlow>
      </div>

      {/* The canvas is unreadable to a screen reader and unreachable by
       * keyboard, so the same story is also emitted as an ordered list.
       * Charts.tsx and PropertyStatsCharts.tsx already pair every visual
       * with an sr-only data list; WorkGraph.tsx does not, which
       * docs/audit/08 flags -- this component should not repeat that. */}
      <ol className="sr-only">
        {steps.map((step) => (
          <li key={`sr-${step.id}`}>
            {step.at ? `${formatDateTime(step.at)}: ` : ""}
            {step.kind === "now" ? "Currently: " : ""}
            {step.title}
            {step.detail ? `. ${step.detail}` : ""}
            {step.badge ? `. Policy: ${step.badge}` : ""}
          </li>
        ))}
      </ol>

      {events.length === 0 && runs.length === 0 && (
        <p className="mt-3 text-[11px] text-muted-foreground">
          No event log was recorded for this case, so there is no history to draw beyond its current
          state. Cases raised before the event log existed look like this.
        </p>
      )}
    </Card>
  );
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("h-2.5 w-2.5 rounded-[3px] border-2 bg-card", className)} />
      {label}
    </span>
  );
}

/** The full audit for one round, shown under the graph when its node is
 * clicked. This is the "verify the AI got it right" job: what it read,
 * what it cited, what the policy did, which model, how long. */
export function RunDetail({ run }: { run: OrchestrationRun }) {
  const ms = run.finished_at
    ? new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
    : null;
  const proposal = run.proposal;

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Why it decided that</h2>
        <span className="text-[11px] text-muted-foreground">
          {formatDateTime(run.started_at)}
          {ms !== null && ` · ${(ms / 1000).toFixed(1)}s`}
        </span>
      </div>

      <dl className="mt-3 space-y-2.5 text-xs">
        <Row label="Read">
          {run.tool_calls.length === 0 ? (
            <span className="text-muted-foreground">
              nothing — decided from the case snapshot alone
            </span>
          ) : (
            <span className="flex flex-wrap gap-1">
              {run.tool_calls.map((t) => (
                <span
                  key={t.id}
                  title={t.error_code ?? undefined}
                  className={cn(
                    "rounded-md border px-1.5 py-px font-mono text-[10px]",
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
        </Row>

        <Row label="Concluded">
          {proposal?.decision_summary ?? (
            <span className="text-muted-foreground">no summary recorded</span>
          )}
        </Row>

        <Row label="Evidence">
          {proposal && proposal.evidence_refs.length > 0 ? (
            `${proposal.evidence_refs.length} record${proposal.evidence_refs.length === 1 ? "" : "s"} cited`
          ) : (
            <span className="text-muted-foreground">none cited</span>
          )}
        </Row>

        {run.policy_result && <Row label="Policy">{run.policy_result}</Row>}
        {run.error_code && (
          <Row label="Failed">
            <span className="font-mono text-[11px] text-destructive">{run.error_code}</span>
          </Row>
        )}
        <Row label="Model">
          <span className="font-mono text-[11px]">{run.model_id}</span>
        </Row>
      </dl>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5">
      <dt className="w-20 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 flex-1">{children}</dd>
    </div>
  );
}
