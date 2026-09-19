import { useEffect, useRef, useState } from "react";
import { fetchCaseDetail, type OperatorCredentials } from "../api/client";
import type { components } from "../api/schema";

type CaseSnapshot = components["schemas"]["CaseSnapshot"];

const POLL_INTERVAL_MS = 1500;

/**
 * Polls GET /cases/{id} with known_version so the server can answer 304
 * (no body) once nothing has changed -- this hook is the one place that
 * distinguishes "no update" from "case data."
 */
export function useCaseDetail(creds: OperatorCredentials | null, caseId: string | null) {
  const [snapshot, setSnapshot] = useState<CaseSnapshot | null>(null);
  const [latestEventSeq, setLatestEventSeq] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const versionRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    versionRef.current = undefined;
    setSnapshot(null);
    setLatestEventSeq(0);
    setError(null);
  }, [caseId]);

  useEffect(() => {
    if (!creds || !caseId) return;
    let cancelled = false;

    async function poll() {
      try {
        const result = await fetchCaseDetail(creds!, caseId!, versionRef.current);
        if (cancelled || result.status === 304) return;
        versionRef.current = result.body.snapshot.case.version;
        setSnapshot(result.body.snapshot);
        setLatestEventSeq(result.body.latest_event_seq);
        setError(null);
      } catch {
        if (!cancelled) setError("Lost contact with the RepairFlow API.");
      }
    }

    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [creds, caseId]);

  return { snapshot, latestEventSeq, error };
}
