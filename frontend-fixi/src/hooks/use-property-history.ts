import { useQuery } from "@tanstack/react-query";
import { fetchPropertyHistory } from "@/api/endpoints";
import { useAuthedCreds } from "@/lib/auth-context";

const POLL_INTERVAL_MS = 10000;

export function usePropertyHistory(propertyId: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["property-history", propertyId],
    enabled: propertyId !== null,
    refetchInterval: POLL_INTERVAL_MS,
    queryFn: () => fetchPropertyHistory(creds, propertyId!),
  });
}
