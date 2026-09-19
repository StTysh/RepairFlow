import { useQuery } from "@tanstack/react-query";
import { fetchNotifications } from "@/api/endpoints";
import { useAuthedCreds } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 5000;

/** Bell-icon feed in UtilityBar. Same polling shape as useDashboardMetrics
 * (no known_version/etag on this endpoint, so a plain interval poll). */
export function useNotifications() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => fetchNotifications(creds),
    refetchInterval: POLL_INTERVAL_MS,
  });
}
