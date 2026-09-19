import { Background, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { components } from "../api/schema";
import { formatPence, titleCase } from "../lib/format";

type CaseSnapshot = components["schemas"]["CaseSnapshot"];
type WorkOrder = components["schemas"]["WorkOrder"];
type WorkOrderKind = components["schemas"]["WorkOrderKind"];

// Fixed layout, not auto-computed (docs/04's fallback ladder pre-authorizes
// this for the MVP): the domain only ever has these three work order
// kinds, so a hardcoded column per kind is simpler and more predictable
// than pulling in a graph-layout library for a 3-node graph.
const KIND_X: Record<WorkOrderKind, number> = {
  SCAFFOLD_INSTALL: 20,
  REPAIR: 300,
  SCAFFOLD_REMOVE: 580,
};

const STATUS_COLOR: Record<string, string> = {
  READY: "#38bdf8",
  SCHEDULED: "#a78bfa",
  IN_PROGRESS: "#a78bfa",
  AWAITING_REPORT: "#fbbf24",
  BLOCKED: "#fb7185",
  COMPLETED: "#34d399",
  CANCELLED: "#64748b",
};

function workOrderNode(wo: WorkOrder): Node {
  const color = STATUS_COLOR[wo.status] ?? "#64748b";
  return {
    id: wo.id,
    position: { x: KIND_X[wo.kind] ?? 300, y: 110 },
    data: {
      label: (
        <div className="w-44 text-left">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-200">{titleCase(wo.kind)}</div>
          <div className="mt-0.5 text-[11px] text-slate-400">{titleCase(wo.trade)}</div>
          <div className="mt-1 text-xs font-medium" style={{ color }}>
            {titleCase(wo.status)}
          </div>
          {wo.quote_pence !== null && wo.quote_pence !== undefined && (
            <div className="mt-1 text-[11px] text-slate-500">{formatPence(wo.quote_pence)}</div>
          )}
          {wo.required_for_resolution && <div className="mt-1 text-[10px] text-amber-400">required for resolution</div>}
        </div>
      ),
    },
    style: {
      border: `1.5px solid ${color}`,
      borderRadius: 10,
      background: "#0f172a",
      padding: 10,
      width: 190,
    },
  };
}

export function WorkGraph({ snapshot }: { snapshot: CaseSnapshot }) {
  const { nodes, edges } = useMemo(() => {
    const issueNode: Node = {
      id: `issue:${snapshot.issue.id}`,
      position: { x: 300, y: -20 },
      data: {
        label: (
          <div className="w-56 text-left">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-300">Issue</div>
            <div className="mt-0.5 text-xs text-slate-400">{snapshot.issue.description}</div>
          </div>
        ),
      },
      style: {
        border: "1.5px solid #475569",
        borderRadius: 10,
        background: "#111827",
        padding: 10,
        width: 220,
      },
      draggable: false,
    };

    const woNodes = snapshot.work_orders.map((wo) => ({ ...workOrderNode(wo), draggable: false }));

    const issueEdges: Edge[] = snapshot.work_orders
      .filter((wo) => wo.kind === "REPAIR")
      .map((wo) => ({
        id: `issue-${wo.id}`,
        source: issueNode.id,
        target: wo.id,
        style: { stroke: "#475569" },
      }));

    const depEdges: Edge[] = snapshot.dependencies.map((dep) => ({
      id: dep.id,
      source: dep.prerequisite_work_order_id,
      target: dep.dependent_work_order_id,
      label: dep.status === "SATISFIED" ? "satisfied" : "blocks",
      animated: dep.status === "OPEN",
      style: { stroke: dep.status === "OPEN" ? "#fb7185" : "#34d399" },
      labelStyle: { fill: "#cbd5e1", fontSize: 10 },
      labelBgStyle: { fill: "#0f172a" },
    }));

    return { nodes: [issueNode, ...woNodes], edges: [...issueEdges, ...depEdges] };
  }, [snapshot]);

  return (
    <div className="h-72 rounded-lg border border-slate-800 bg-slate-950">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag
        zoomOnScroll
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e293b" gap={20} />
      </ReactFlow>
    </div>
  );
}
