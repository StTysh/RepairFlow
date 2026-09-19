import { useQuery } from "@tanstack/react-query";
import { fetchUpcomingAppointments } from "@/api/endpoints";
import { useAuthedCreds } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 5000;

/** Cross-case "Upcoming visits" sidebar card on the Maintenance list. Same
 * polling shape as useDashboardMetrics/useNotifications. */
export function useUpcomingAppointments() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["upcoming-appointments"],
    queryFn: () => fetchUpcomingAppointments(creds),
    refetchInterval: POLL_INTERVAL_MS,
  });
}
