import { useQuery } from "@tanstack/react-query";
import { request } from "@/api/client";
import { useAuthedCreds } from "@/lib/auth-context";

/** The sidebar's Messages badge.
 *
 * Reads the same endpoint the Messages screen's per-thread counts are
 * derived from, so the badge and the list can never disagree. */
export function useGlobalUnreadCount() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["messages-unread-count"],
    refetchInterval: 15000,
    queryFn: () => request<{ unread_count: number }>(creds, "/api/v1/messages/unread-count"),
  });
}
