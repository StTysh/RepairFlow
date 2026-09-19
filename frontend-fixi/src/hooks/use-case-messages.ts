import { useQuery } from "@tanstack/react-query";
import { fetchCaseMessages } from "@/api/endpoints";
import { useAuthedCreds } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 4000;

/** Backs the ticket detail Messages tab -- a read-only tenant/contractor/
 * operator thread (GET /api/v1/cases/{id}/messages). Display-only: chat
 * history is never authoritative state and the coordinator never reads it
 * (CLAUDE.md) -- this hook exists purely so the operator UI can show it. */
export function useCaseMessages(caseId: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["case-messages", caseId],
    enabled: caseId !== null,
    refetchInterval: POLL_INTERVAL_MS,
    queryFn: () => fetchCaseMessages(creds, caseId!),
  });
}
