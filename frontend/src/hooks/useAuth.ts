import { useCallback, useState } from "react";
import {
  clearCredentials,
  loadStoredCredentials,
  storeCredentials,
  verifyCredentials,
  type OperatorCredentials,
} from "../api/client";

export function useAuth() {
  const [creds, setCreds] = useState<OperatorCredentials | null>(() => loadStoredCredentials());
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  const login = useCallback(async (username: string, password: string) => {
    setVerifying(true);
    setError(null);
    const candidate = { username, password };
    try {
      const ok = await verifyCredentials(candidate);
      if (!ok) {
        setError("Invalid operator credentials.");
        return false;
      }
      storeCredentials(candidate);
      setCreds(candidate);
      return true;
    } catch {
      setError("Could not reach the RepairFlow API. Is the backend running?");
      return false;
    } finally {
      setVerifying(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearCredentials();
    setCreds(null);
  }, []);

  return { creds, login, logout, error, verifying };
}
