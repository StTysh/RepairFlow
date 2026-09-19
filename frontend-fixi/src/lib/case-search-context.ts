import { createContext, useContext } from "react";

// Bridges the global search input in UtilityBar (rendered once, inside
// AppShell, above every page -- see AppShell.tsx) with whichever page
// actually has a case list to filter by it (currently just the Maintenance
// list). Provided in __root.tsx's RootComponent, above <Outlet/>, so it's
// available to every routed page and to AppShell itself -- same split as
// AuthedCredsContext/LoginGate (see auth-context.ts for why *-context.ts
// files only export non-component context/hook values, not the provider).
export interface CaseSearchState {
  search: string;
  setSearch: (value: string) => void;
}

export const CaseSearchContext = createContext<CaseSearchState | null>(null);

export function useCaseSearch(): CaseSearchState {
  const ctx = useContext(CaseSearchContext);
  if (!ctx) throw new Error("useCaseSearch() called outside the root CaseSearchContext.Provider");
  return ctx;
}
