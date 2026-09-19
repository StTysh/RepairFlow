import { useQuery } from "@tanstack/react-query";
import { fetchCaseList, type ListCasesParams } from "@/api/endpoints";
import { useAuthedCreds } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 4000;

/** List screen data source. Server-side filters (status/property_id/q) are
 * passed straight through as query params; anything the API doesn't filter
 * on server-side (e.g. urgency) is left to the caller to apply client-side
 * over `items`. */
export function useCaseList(params: ListCasesParams = {}) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["cases", params],
    queryFn: () => fetchCaseList(creds, params),
    refetchInterval: POLL_INTERVAL_MS,
    placeholderData: (previous) => previous,
  });
}
