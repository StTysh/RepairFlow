import { useQuery } from "@tanstack/react-query";
import { fetchCaseEvents } from "@/api/endpoints";
import { useAuthedCreds } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 4000;

/** Backs the ticket detail Timeline -- the only activity feed in this
 * phase (no Messages/chat tab; see CLAUDE.md decision). Refetches the
 * full (capped) list each poll rather than tracking after_seq
 * incrementally: simplest thing that works at demo scale, and the next
 * phase is free to switch this to incremental loading if the event volume
 * grows. */
export function useCaseEvents(caseId: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["case-events", caseId],
    enabled: caseId !== null,
    refetchInterval: POLL_INTERVAL_MS,
    queryFn: () => fetchCaseEvents(creds, caseId!, { limit: 100 }),
  });
}
