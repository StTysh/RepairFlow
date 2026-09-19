import { useEffect, useState } from "react";
import { createApiClient, type OperatorCredentials } from "../api/client";
import type { components } from "../api/schema";

type ReadinessResponse = components["schemas"]["ReadinessResponse"];

export function useReadiness(creds: OperatorCredentials | null) {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);

  useEffect(() => {
    if (!creds) return;
    const client = createApiClient(creds);
    let cancelled = false;
    client.GET("/api/v1/readiness").then(({ data }) => {
      if (!cancelled && data) setReadiness(data);
    });
    return () => {
      cancelled = true;
    };
  }, [creds]);

  return readiness;
}
