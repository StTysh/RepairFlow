import { createContext, useContext } from "react";
import type { OperatorCredentials } from "@/api/client";

// Split out of LoginGate.tsx so that file only exports components (keeps
// react-refresh/only-export-components happy). See LoginGate.tsx for why
// this exists: routed pages under <Outlet /> can't receive the signed-in
// operator's credentials as a prop the way frontend's flat CaseWorkspace
// does, so LoginGate provides them through this context instead.
export const AuthedCredsContext = createContext<OperatorCredentials | null>(null);

export function useAuthedCreds(): OperatorCredentials {
  const creds = useContext(AuthedCredsContext);
  if (!creds) throw new Error("useAuthedCreds() called outside an authenticated <LoginGate>");
  return creds;
}
