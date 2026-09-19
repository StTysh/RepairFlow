import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCaseDetail } from "@/api/endpoints";
import type { CaseDetailResponse } from "@/api/types";
import { useAuthedCreds } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 2000;

export function caseDetailQueryKey(caseId: string | null) {
  return ["case-detail", caseId] as const;
}

/** Polls GET /cases/{id} with known_version so the server can answer 304
 * (no body) once nothing has changed -- ported from
 * frontend/src/hooks/useCaseDetail.ts's technique, adapted to React Query:
 * the "known version" is just whatever this exact query key already has
 * cached, so switching case ids naturally starts a fresh poll instead of
 * needing a manually-reset ref. */
export function useCaseDetail(caseId: string | null) {
  const creds = useAuthedCreds();
  const queryClient = useQueryClient();
  const queryKey = caseDetailQueryKey(caseId);

  return useQuery<CaseDetailResponse>({
    queryKey,
    enabled: caseId !== null,
    refetchInterval: POLL_INTERVAL_MS,
    queryFn: async () => {
      if (!caseId) throw new Error("useCaseDetail called without a case id");
      const previous = queryClient.getQueryData<CaseDetailResponse>(queryKey);
      const result = await fetchCaseDetail(creds, caseId, previous?.snapshot.case.version);
      if (result.status === 304) {
        // 304 only happens once we've already loaded this case at least
        // once, so `previous` should always be set here -- but if the
        // cache was evicted between the version check and this branch,
        // fall back to an unconditional fetch rather than returning
        // undefined (which React Query treats as an error).
        if (previous) return previous;
        const fresh = await fetchCaseDetail(creds, caseId);
        if (fresh.status !== 200) throw new Error(`failed to load case ${caseId}`);
        return fresh.body;
      }
      return result.body;
    },
  });
}
