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
import { useMemo } from "react";
import { Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import type { Dependency, WorkOrder, WorkOrderKind, WorkOrderStatus } from "@/api/types";
import type { StatusTone } from "@/lib/fixi-data";
import { formatPence, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// Fixed columns by kind, not an auto-layout library: the domain only ever
// has these three work order kinds (backend: app/schemas.py
// WorkOrderKind), and this graph is usually 1-3 nodes, so a hardcoded
// column per kind is simpler and more predictable than pulling in a
// graph-layout dependency for that. Columns for a kind with no work order
// on this case are skipped entirely (not reserved), so the common
// single-work-order case renders as one centred node, not one node
// stranded beside empty columns.
const KIND_ORDER: WorkOrderKind[] = ["SCAFFOLD_INSTALL", "REPAIR", "SCAFFOLD_REMOVE"];
const COLUMN_WIDTH = 260;
const ROW_HEIGHT = 150;

const workOrderKindLabel: Record<WorkOrderKind, string> = {
  SCAFFOLD_INSTALL: "Scaffold install",
  REPAIR: "Repair",
  SCAFFOLD_REMOVE: "Scaffold removal",
};

const STATUS_TONE: Record<WorkOrderStatus, StatusTone> = {
  READY: "blue",
  SCHEDULED: "purple",
  IN_PROGRESS: "purple",
  AWAITING_REPORT: "amber",
  BLOCKED: "red",
  COMPLETED: "green",
  CANCELLED: "gray",
};

// Literal class strings (not built from a template) so Tailwind's
// source scanner can see and generate every variant at build time --
// mirrors Badge.tsx's toneClasses.
const nodeBorderClasses: Record<StatusTone, string> = {
  red: "border-status-red-foreground/50",
  orange: "border-status-orange-foreground/50",
  green: "border-status-green-foreground/50",
  blue: "border-status-blue-foreground/50",
  amber: "border-status-amber-foreground/50",
  purple: "border-status-purple-foreground/50",
  gray: "border-border",
};

type WorkOrderNodeData = { workOrder: WorkOrder };
type WorkOrderNodeType = Node<WorkOrderNodeData, "workOrder">;

function WorkOrderNode({ data }: NodeProps<WorkOrderNodeType>) {
  const wo = data.workOrder;
  const tone = STATUS_TONE[wo.status];
  const quote = formatPence(wo.quote_pence);
  return (
    <div
      className={cn(
        "w-52 rounded-xl border-2 bg-card p-3 text-left shadow-card",
        nodeBorderClasses[tone],
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: "var(--muted-foreground)" }}
      />
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {workOrderKindLabel[wo.kind]}
      </div>
      <div className="mt-0.5 text-xs text-muted-foreground">{titleCase(wo.trade)}</div>
      <div className="mt-1.5">
        <Pill tone={tone}>{titleCase(wo.status)}</Pill>
      </div>
      {quote && <div className="mt-1.5 text-[11px] text-muted-foreground">Quoted {quote}</div>}
      {wo.required_for_resolution && (
        <div className="mt-1 text-[10px] font-medium text-status-amber-foreground">
          Required for resolution
        </div>
      )}
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: "var(--muted-foreground)" }}
      />
    </div>
  );
}

// Stable reference -- passing a fresh object here every render is a React
// Flow anti-pattern (it warns and re-mounts node types on every render).
const nodeTypes = { workOrder: WorkOrderNode };

const depEdgeColor: Record<Dependency["status"], string> = {
  OPEN: "var(--status-red-foreground)",
  SATISFIED: "var(--status-green-foreground)",
  INVALIDATED: "var(--muted-foreground)",
};

const depEdgeLabel: Record<Dependency["status"], string> = {
  OPEN: "blocks",
  SATISFIED: "satisfied",
  INVALIDATED: "invalidated",
};

/** Renders this case's work orders and the dependency edges between them --
 * a scaffold install blocking a roof repair until it's satisfied is the
 * demo's central story, and before this there was no visualisation of it
 * anywhere (CaseSnapshot.dependencies was typed `unknown[]` and never
 * read). Only ever draws what's actually on the snapshot: no synthesized
 * nodes/edges, no columns reserved for kinds that aren't present. Most
 * cases right now have zero dependencies -- a single node with no edges is
 * the normal, correct render for that, not a broken/empty state.
 *
 * Nodes/edges are derived with useMemo rather than seeded once into
 * useNodesState/useEdgesState: the snapshot is polled (docs/09), so a
 * dependency discovered mid-demo needs to actually appear without a
 * remount. */
export function WorkGraph({
  workOrders,
  dependencies,
}: {
  workOrders: WorkOrder[];
  dependencies: Dependency[];
}) {
  const { nodes, edges } = useMemo(() => {
    const presentKinds = KIND_ORDER.filter((kind) => workOrders.some((wo) => wo.kind === kind));
    const columnOf = new Map(presentKinds.map((kind, i) => [kind, i]));
    const rowCounters = new Map<WorkOrderKind, number>();

    const nodes: WorkOrderNodeType[] = workOrders.map((wo) => {
      const col = columnOf.get(wo.kind) ?? 0;
      const row = rowCounters.get(wo.kind) ?? 0;
      rowCounters.set(wo.kind, row + 1);
      return {
        id: wo.id,
        type: "workOrder",
        position: { x: col * COLUMN_WIDTH, y: row * ROW_HEIGHT },
        data: { workOrder: wo },
        draggable: false,
        selectable: false,
      };
    });

    const nodeIds = new Set(workOrders.map((wo) => wo.id));
    // React Flow silently drops an edge whose source/target don't resolve
    // to a node -- filtering explicitly here means a dependency row
    // referencing a work order that isn't on this snapshot degrades to
    // "no edge drawn" rather than a dangling reference nobody notices.
    const edges: Edge[] = dependencies
      .filter(
        (dep) =>
          nodeIds.has(dep.prerequisite_work_order_id) && nodeIds.has(dep.dependent_work_order_id),
      )
      .map((dep) => ({
        id: dep.id,
        source: dep.prerequisite_work_order_id,
        target: dep.dependent_work_order_id,
        label: depEdgeLabel[dep.status],
        animated: dep.status === "OPEN",
        style: { stroke: depEdgeColor[dep.status], strokeWidth: 1.5 },
        labelStyle: { fill: "var(--foreground)", fontSize: 11, fontWeight: 500 },
        labelBgStyle: { fill: "var(--card)" },
        labelBgPadding: [4, 2] as [number, number],
      }));

    return { nodes, edges };
  }, [workOrders, dependencies]);

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold">Work</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Work orders on this case and any dependency blocking one on another.
          </p>
        </div>
        {dependencies.length > 0 && (
          <div className="flex shrink-0 items-center gap-3 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-3 rounded-full bg-status-red-foreground/70" /> Blocks
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-3 rounded-full bg-status-green-foreground/70" /> Satisfied
            </span>
          </div>
        )}
      </div>

      {workOrders.length === 0 ? (
        <p className="mt-4 text-xs text-muted-foreground">No work orders on this case yet.</p>
      ) : (
        <div className="mt-4 h-72 overflow-hidden rounded-lg border border-border bg-background/40">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3, maxZoom: 1.1 }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnDrag
            zoomOnScroll
            proOptions={{ hideAttribution: true }}
          >
            <Background color="var(--border)" gap={20} />
          </ReactFlow>
        </div>
      )}
    </Card>
  );
}
