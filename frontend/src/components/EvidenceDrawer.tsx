import { useState } from "react";
import { BASE_URL, type OperatorCredentials } from "../api/client";
import type { components } from "../api/schema";
import { formatDateTime, titleCase } from "../lib/format";
import { ProvenanceBadge } from "./ProvenanceBadge";

type ContractorReport = components["schemas"]["ContractorReport"];
type Communication = components["schemas"]["Communication"];

function ReportRow({ report }: { report: ContractorReport }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-slate-200">Contractor report</span>
        <ProvenanceBadge provenance={report.provenance} />
        <span className="text-[10px] text-slate-500">{formatDateTime(report.observed_at)}</span>
        <span className="ml-auto text-[10px] text-slate-500">{titleCase(report.interpretation_status)}</span>
      </div>
      <p className="mt-1.5 text-xs text-slate-400">{report.text}</p>
    </div>
  );
}

function RecordingPlayer({ communication, creds }: { communication: Communication; creds: OperatorCredentials }) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${BASE_URL}/api/v1/communications/${communication.id}/recording`, {
        headers: { Authorization: `Basic ${btoa(`${creds.username}:${creds.password}`)}` },
      });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      setObjectUrl(URL.createObjectURL(blob));
    } catch {
      setError("Recording could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  if (objectUrl) return <audio controls src={objectUrl} className="mt-2 h-8 w-full" />;
  return (
    <button
      type="button"
      onClick={load}
      disabled={loading}
      className="mt-2 rounded border border-slate-700 bg-slate-800/60 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700 disabled:opacity-50"
    >
      {loading ? "Loading…" : error ?? "▶ Play recording"}
    </button>
  );
}

function CommunicationRow({ communication, creds }: { communication: Communication; creds: OperatorCredentials }) {
  const recording = communication.recording;
  return (
    <div className="rounded border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-slate-200">
          {titleCase(communication.purpose)} · {titleCase(communication.direction)}
        </span>
        <ProvenanceBadge provenance={communication.provenance} />
        <span className="text-[10px] text-slate-500">{titleCase(communication.state)}</span>
        <span className="ml-auto text-[10px] text-slate-500">{formatDateTime(communication.started_at)}</span>
      </div>

      {recording && recording.status !== "PENDING" && (
        <div className="mt-1 text-[11px] text-slate-500">
          Recording: {titleCase(recording.status)}
          {recording.status === "AVAILABLE" && <RecordingPlayer communication={communication} creds={creds} />}
        </div>
      )}

      {(communication.transcript?.length ?? 0) > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] text-sky-400 hover:text-sky-300">
            Transcript ({communication.transcript!.length} turns)
          </summary>
          <ul className="mt-1.5 space-y-1 border-l border-slate-800 pl-3">
            {communication.transcript!.map((turn) => (
              <li key={turn.turn_id} className="text-[11px] text-slate-400">
                <span className="font-medium text-slate-300">{titleCase(turn.speaker)}</span>{" "}
                <span className="text-slate-600">[{turn.time_in_call_secs.toFixed(1)}s]</span> {turn.text}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function EvidenceDrawer({
  reports,
  communications,
  creds,
}: {
  reports: ContractorReport[];
  communications: Communication[];
  creds: OperatorCredentials;
}) {
  if (reports.length === 0 && communications.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-500">
        No evidence recorded for this case yet.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence</h3>
      <div className="mt-3 space-y-2">
        {communications.map((c) => (
          <CommunicationRow key={c.id} communication={c} creds={creds} />
        ))}
        {reports.map((r) => (
          <ReportRow key={r.id} report={r} />
        ))}
      </div>
    </div>
  );
}
