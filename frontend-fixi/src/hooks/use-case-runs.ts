import { useQuery } from "@tanstack/react-query";
import { fetchCaseRuns } from "@/api/endpoints";
import { useAuthedCreds } from "@/lib/auth-context";

/** Matches the case-detail poll: a run appears as a side effect of the same
 * coordinator activity the snapshot reflects, so refreshing them at
 * different rates makes the two disagree on screen. */
const POLL_INTERVAL_MS = 4000;

export function caseRunsQueryKey(caseId: string) {
  return ["case-runs", caseId] as const;
}

/** The coordinator's reasoning history for one case.
 *
 * `GET /cases/{id}/runs` has been served since the migration with zero
 * frontend callers, so every decided, executed or failed decision was
 * invisible: the UI showed only the one proposal currently awaiting
 * approval, and lost it the moment it was approved. */
export function useCaseRuns(caseId: string) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: caseRunsQueryKey(caseId),
    queryFn: () => fetchCaseRuns(creds, caseId),
    refetchInterval: POLL_INTERVAL_MS,
  });
}
