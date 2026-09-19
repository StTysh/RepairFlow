import { useQuery } from "@tanstack/react-query";
import { fetchDashboardMetrics } from "@/api/endpoints";
import { useAuthedCreds } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 5000;

export function useDashboardMetrics() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: () => fetchDashboardMetrics(creds),
    refetchInterval: POLL_INTERVAL_MS,
  });
}
