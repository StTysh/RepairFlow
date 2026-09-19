import { useEffect, useState } from "react";
import { createApiClient, type OperatorCredentials } from "../api/client";
import type { components } from "../api/schema";
import { formatDateTime, titleCase } from "../lib/format";
import { ProvenanceBadge } from "./ProvenanceBadge";

type CaseEvent = components["schemas"]["CaseEvent"];

function payloadPreview(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return entries
    .slice(0, 3)
    .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(" · ");
}

function EventRow({ event }: { event: CaseEvent }) {
  return (
    <li className="relative border-l border-slate-800 pb-4 pl-4">
      <span className="absolute -left-[5px] top-1 h-2.5 w-2.5 rounded-full bg-slate-600" />
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-slate-200">{titleCase(event.type)}</span>
        <ProvenanceBadge provenance={event.provenance} />
        <span className="text-[11px] text-slate-500">
          #{event.seq} · {formatDateTime(event.occurred_at)} · {event.actor_type}
        </span>
      </div>
      {payloadPreview(event.payload) && <p className="mt-0.5 text-xs text-slate-400">{payloadPreview(event.payload)}</p>}
    </li>
  );
}

export function Timeline({
  events,
  creds,
  caseId,
}: {
  events: CaseEvent[];
  creds: OperatorCredentials;
  caseId: string;
}) {
  const [showAll, setShowAll] = useState(false);
  const [fullEvents, setFullEvents] = useState<CaseEvent[] | null>(null);

  useEffect(() => {
    if (!showAll) return;
    let cancelled = false;
    (async () => {
      const client = createApiClient(creds);
      const { data } = await client.GET("/api/v1/cases/{case_id}/events", {
        params: { path: { case_id: caseId }, query: { limit: 100 } },
      });
      if (!cancelled && data) setFullEvents(data.items);
    })();
    return () => {
      cancelled = true;
    };
  }, [showAll, creds, caseId]);

  const display = (showAll && fullEvents ? fullEvents : events).slice().sort((a, b) => b.seq - a.seq);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Timeline</h3>
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="text-[11px] text-sky-400 hover:text-sky-300"
        >
          {showAll ? "Show recent" : "Show full history"}
        </button>
      </div>
      <ol className="mt-3 max-h-96 overflow-y-auto">
        {display.map((event) => (
          <EventRow key={event.id} event={event} />
        ))}
      </ol>
    </div>
  );
}
