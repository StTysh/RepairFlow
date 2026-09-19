import { useEffect, useState } from "react";
import { createApiClient, type OperatorCredentials } from "../api/client";
import type { components } from "../api/schema";

type CaseListItem = components["schemas"]["CaseListItem"];

const POLL_INTERVAL_MS = 3000;

export function useCaseList(creds: OperatorCredentials | null) {
  const [items, setItems] = useState<CaseListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!creds) return;
    const client = createApiClient(creds);
    let cancelled = false;

    async function poll() {
      const { data, error: apiError } = await client.GET("/api/v1/cases", { params: { query: { limit: 50 } } });
      if (cancelled) return;
      if (apiError) {
        setError("Could not load case list.");
        return;
      }
      setItems(data.items);
      setError(null);
    }

    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [creds]);

  return { items, error };
}
