import { useEffect, useState } from "react";
import { createApiClient, type OperatorCredentials } from "../api/client";
import type { components } from "../api/schema";
import { formatDateTime } from "../lib/format";
import { ProvenanceBadge } from "./ProvenanceBadge";

type CaseEvent = components["schemas"]["CaseEvent"];
type ResearchSnapshot = components["schemas"]["ResearchSnapshot"];

export function ResearchDrawer({
  events,
  creds,
  tavilyLive,
}: {
  events: CaseEvent[];
  creds: OperatorCredentials;
  tavilyLive: boolean;
}) {
  const researchIds = Array.from(
    new Set(
      events
        .filter((e) => e.type === "RESEARCH_COMPLETED")
        .map((e) => (e.payload as { research_id?: string }).research_id)
        .filter((id): id is string => Boolean(id)),
    ),
  );

  const [snapshots, setSnapshots] = useState<Record<string, ResearchSnapshot>>({});

  useEffect(() => {
    if (researchIds.length === 0) return;
    const client = createApiClient(creds);
    let cancelled = false;
    (async () => {
      for (const id of researchIds) {
        if (snapshots[id]) continue;
        const { data } = await client.GET("/api/v1/research/{research_id}", { params: { path: { research_id: id } } });
        if (!cancelled && data) setSnapshots((prev) => ({ ...prev, [id]: data }));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [researchIds.join(",")]);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Contractor research</h3>
        {!tavilyLive && (
          <span className="rounded border border-slate-700 bg-slate-800/60 px-2 py-0.5 text-[10px] text-slate-400">
            Tavily not configured — fixture data only
          </span>
        )}
      </div>
      {researchIds.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500">
          No contractor research run for this case yet. A search result is evidence only — never a booked or approved
          contractor.
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          {researchIds.map((id) => {
            const snap = snapshots[id];
            if (!snap) return <p key={id} className="text-xs text-slate-500">Loading…</p>;
            return (
              <div key={id} className="rounded border border-slate-800 bg-slate-950/60 p-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-slate-200">{snap.query}</span>
                  <ProvenanceBadge provenance={snap.provenance} />
                  <span className="text-[10px] text-slate-500">{formatDateTime(snap.completed_at)}</span>
                </div>
                <ul className="mt-2 space-y-1.5">
                  {(snap.results ?? []).map((evidence, i) => (
                    <li key={i} className="text-[11px] text-slate-400">
                      <a href={evidence.url} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">
                        {evidence.title}
                      </a>
                      <span className="ml-1 text-slate-500">— {evidence.excerpt}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
