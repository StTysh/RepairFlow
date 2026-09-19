import { useCallback, useEffect, useState } from "react";
import {
  clearCredentials,
  loadStoredCredentials,
  storeCredentials,
  verifyCredentials,
  type OperatorCredentials,
} from "../api/client";

// Placeholder used only when the backend has OPERATOR_AUTH_ENABLED=false --
// require_operator ignores these entirely in that mode, so the value itself
// is irrelevant; it just satisfies the "creds present" shape the rest of the
// app expects.
const AUTH_DISABLED_CREDS: OperatorCredentials = { username: "operator", password: "" };

export function useAuth() {
  const [creds, setCreds] = useState<OperatorCredentials | null>(() => loadStoredCredentials());
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  // If nothing is stored, check whether the backend even requires a login at
  // all (auth disabled locally) before showing the sign-in form.
  useEffect(() => {
    if (creds) return;
    let cancelled = false;
    verifyCredentials(AUTH_DISABLED_CREDS).then((ok) => {
      if (ok && !cancelled) setCreds(AUTH_DISABLED_CREDS);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
