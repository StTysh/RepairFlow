import { useState, type ReactNode } from "react";
import { useAuth } from "@/hooks/use-auth";
import { AuthedCredsContext } from "@/lib/auth-context";
import { FixiLogo } from "@/components/fixi/AppShell";

// Gates children behind a login form, exactly like frontend's LoginGate:
// verify credentials against the backend once, persist them to
// sessionStorage (via use-auth.ts / api/client.ts), and expose them to
// authenticated content afterwards -- here via AuthedCredsContext (see
// lib/auth-context.ts) since the authenticated content is <Outlet />,
// which can't receive props the way frontend's flat component tree does.

export function LoginGate({ children }: { children: ReactNode }) {
  const { creds, login, logout, error, verifying } = useAuth();
  const [username, setUsername] = useState("operator");
  const [password, setPassword] = useState("");

  if (creds) {
    return (
      <AuthedCredsContext.Provider value={creds}>
        {/*
          A real row in normal flow, not an absolute/fixed overlay: every
          routed page renders <AppShell> with its own full-width px-8 header
          row (Share/Edit/more-menu on the ticket page, Close buttons on the
          property-history page), so an overlay pinned to a screen corner
          ends up stacked on top of those controls instead of clear of them.
          Stacking this above <Outlet /> costs a few pixels of extra height
          instead.
        */}
        <div className="flex items-center justify-between border-b border-border bg-card px-4 py-1.5 text-xs">
          <span className="text-muted-foreground">Signed in as {creds.username}</span>
          <button
            type="button"
            onClick={logout}
            className="font-medium text-foreground hover:text-primary"
          >
            Sign out
          </button>
        </div>
        {children}
      </AuthedCredsContext.Provider>
    );
  }

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background px-4 font-sans antialiased">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void login(username, password);
        }}
        className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-panel"
      >
        <FixiLogo />
        <h1 className="mt-5 text-sm font-semibold text-foreground">Operator sign-in</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          Sign in with your Fixi operator credentials to continue.
        </p>

        <label
          className="mt-4 block text-xs font-medium text-muted-foreground"
          htmlFor="login-username"
        >
          Username
        </label>
        <input
          id="login-username"
          className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="operator"
          autoFocus
          autoComplete="username"
        />

        <label
          className="mt-3 block text-xs font-medium text-muted-foreground"
          htmlFor="login-password"
        >
          Password
        </label>
        <input
          id="login-password"
          className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          autoComplete="current-password"
        />

        {error && <p className="mt-3 text-xs text-destructive">{error}</p>}

        <button
          type="submit"
          disabled={verifying}
          className="mt-5 flex h-9 w-full items-center justify-center rounded-lg bg-primary text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {verifying ? "Checking…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
