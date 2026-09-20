import { useQuery } from "@tanstack/react-query";
import { request } from "@/api/client";
import { useAuthedCreds } from "@/lib/auth-context";

/** Live agent/workload reading for the sidebar's status panel.
 *
 * Split out of `use-dashboard-metrics` so the shell can poll a small
 * payload on its own schedule: it is mounted on every screen, whereas the
 * full dashboard metrics are only wanted where they are displayed. */
export interface AgentStatus {
  agent_active: boolean;
  active: number;
}

const POLL_INTERVAL_MS = 10000;

export function useAgentStatus() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["agent-status"],
    refetchInterval: POLL_INTERVAL_MS,
    queryFn: () => request<AgentStatus>(creds, "/api/v1/metrics/dashboard"),
  });
}
