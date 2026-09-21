import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useReactFlow,
  useStore,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Brain, Check, CircleDot, Copy, Hourglass, Inbox, UserCheck, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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

// Declared node sizes, used for the fit before the real ones are known.
//
// React Flow measures nodes with a ResizeObserver, and until a node is
// measured it contributes almost nothing to the bounding box fitView is
// computing against. With eleven unmeasured nodes the box collapses to
// roughly one card, fitView asks for ~3.6x, and the clamp at maxZoom
// hands back 1.6 -- a canvas showing its content at 137% of the pane,
// overflowing on both sides, with the built-in "fit view" button unable
// to correct it because it recomputes from the same empty box.
//
// That is easy to hit: a browser tab that is not rendering (backgrounded,
// occluded, or a prerender) runs no rendering steps, so no ResizeObserver
// callback is ever delivered and the nodes stay unmeasured indefinitely.
// `initialWidth`/`initialHeight` are React Flow's answer -- a declared
// box used only until the measured one arrives, so the first fit is
// right even when measurement is late or never comes.
//
// STEP_W must track `w-56` on StepNode below. The height is a typical
// card, not a maximum: it only has to make the box approximately right.
const STEP_W = 224;
const STEP_H = 104;
const LABEL_W = 56;
const LABEL_H = 18;

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
          <div className={cn("text-xs font-semibold", isNow && "text-strong")}>{step.title}</div>
          {step.detail && (
            <p className="mt-0.5 line-clamp-3 text-micro leading-snug text-muted-foreground">
              {step.detail}
            </p>
          )}
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        {step.badge ? <Pill tone="gray">{step.badge}</Pill> : <span />}
        {step.at && (
          <span className="text-micro text-muted-foreground">{formatRelative(step.at)}</span>
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
    <div className="pointer-events-none select-none text-micro font-semibold uppercase tracking-wide text-muted-foreground">
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
/**
 * Zoom limits. These are the ReactFlow props, not fitView options,
 * because `fitBounds` reads the clamp from the store rather than from
 * its own argument -- and they also bound what manual zooming can do,
 * which is what we want: below ~0.4 the labels stop being readable and
 * above 1.6 a card is comically large.
 */
const MIN_ZOOM = 0.4;
const MAX_ZOOM = 1.6;

/** How much of the canvas to leave as margin around the graph. */
const FIT_PADDING = 0.06;

/**
 * Fits an EXPLICIT box, recomputed whenever the graph's extent changes.
 *
 * `<ReactFlow fitView>` fits to the bounding box React Flow derives from
 * its own node measurements, and that is the problem: measurement is
 * asynchronous (a ResizeObserver), so the box is whatever has been
 * measured at the moment of the call. Observed on this canvas: the first
 * fit ran against an almost-empty box, asked for ~3.6x, got the maxZoom
 * clamp, and left the graph at 137% of its pane -- overflowing both
 * edges, with the built-in "fit view" button recomputing the same wrong
 * answer. Declaring `initialWidth`/`initialHeight` improved it but did
 * not make it deterministic: consecutive loads measured 0.837 and 1.6.
 *
 * This component sidesteps measurement. The layout is ours -- fixed
 * column width, fixed row height, a known node width -- so the extent is
 * arithmetic, not observation, and `fitBounds` takes it directly. The
 * one thing still measured is the canvas itself, which React Flow needs
 * regardless and which is a single stable element.
 */
function FitToBounds({
  bounds,
}: {
  bounds: { x: number; y: number; width: number; height: number };
}) {
  const { fitBounds } = useReactFlow();
  // The canvas's own size is the one thing fitBounds still reads from
  // the store, and it arrives asynchronously like everything else -- two
  // consecutive loads fitted at 1.10 and 0.87 purely because the panel
  // had a different height at the moment of the call. Subscribing to it
  // means the fit is redone when the panel settles.
  const paneWidth = useStore((s) => s.width);
  const paneHeight = useStore((s) => s.height);
  const { x, y, width, height } = bounds;

  useEffect(() => {
    if (!paneWidth || !paneHeight) return;
    // duration 0: this is a correction, not a transition. Animating it
    // would draw the eye to the canvas every time a poll adds a step.
    void fitBounds({ x, y, width, height }, { padding: FIT_PADDING, duration: 0 });
  }, [fitBounds, x, y, width, height, paneWidth, paneHeight]);

  return null;
}

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

  const { nodes, edges, columns, bounds } = useMemo(() => {
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
        initialWidth: STEP_W,
        initialHeight: STEP_H,
        data: { step, selected: step.runId != null && step.runId === selectedRunId },
      };
    });

    const labelNodes: RoundLabelNodeType[] = rounds.map((r, i) => ({
      id: `round-label:${r}`,
      type: "roundLabel",
      position: { x: i * COLUMN_WIDTH + 4, y: 0 },
      initialWidth: LABEL_W,
      initialHeight: LABEL_H,
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

    // The extent, from the layout rather than from measurement. The last
    // column starts at (n-1) * COLUMN_WIDTH and is STEP_W wide; the
    // deepest row starts at LABEL_OFFSET + row * ROW_HEIGHT and is
    // STEP_H tall.
    const lastRow = Math.max(0, ...stepNodes.map((n) => n.position.y));
    const bounds = {
      x: 0,
      y: 0,
      width: Math.max(1, (rounds.length - 1) * COLUMN_WIDTH + STEP_W),
      // One ROW_HEIGHT past the last row, not one STEP_H. Card heights
      // vary with their text, and STEP_H is only a typical value -- a
      // taller bottom card then hung 111px below the panel. Rows are
      // ROW_HEIGHT apart, so a card can never exceed that without
      // colliding with the row beneath it, which makes this the tight
      // upper bound rather than a guess.
      height: Math.max(1, lastRow + ROW_HEIGHT),
    };

    return { nodes: [...labelNodes, ...stepNodes], edges, columns: rounds.length, bounds };
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
  // Was a flat `Math.min(720, ...)`. On a 1226px-tall window the canvas
  // came out 634px with the graph using 43% of it. Clamp to the window so
  // a tall screen gets a tall canvas, with a floor for short ones.
  const contentHeight = LABEL_OFFSET + 60 + deepestColumn * ROW_HEIGHT;
  const height = `clamp(420px, min(${contentHeight}px, calc(100vh - 340px)), 900px)`;

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
          <h2 className="text-section font-semibold">How this case has gone</h2>
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

      <div className="mt-3 flex flex-wrap items-center gap-3 text-micro text-muted-foreground">
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
        {/* No `key={steps.length}` here any more. It remounted the entire
         * canvas whenever a step arrived -- which, on a 4s poll against a
         * live case, threw away the viewport mid-read. React Flow updates
         * `nodes`/`edges` by identity, and the ids are stable
         * (`event:<id>` / `run:<id>`), so it does not need the remount. */}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          minZoom={MIN_ZOOM}
          maxZoom={MAX_ZOOM}
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
          onNodeClick={(_, node) => {
            const step = (node.data as StepNodeData).step;
            if (!step.runId) return;
            onSelectRun(step.runId === selectedRunId ? null : step.runId);
          }}
        >
          <FitToBounds bounds={bounds} />
          <Background color="var(--border)" gap={20} />
          {/* The pan/zoom hint text was conditional on `columns > 4`, so a
           * 4-round case offered no affordance at all while still being
           * pannable. Controls are always present and always honest. */}
          <Controls showInteractive={false} position="bottom-right" className="!shadow-card" />
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
        <p className="mt-3 text-micro text-muted-foreground">
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
        <h2 className="text-section font-semibold">Why it decided that</h2>
        <span className="text-micro text-muted-foreground">
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
            <span className="font-mono text-micro text-destructive">{run.error_code}</span>
          </Row>
        )}
        <Row label="Model">
          <span className="font-mono text-micro">{run.model_id}</span>
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
