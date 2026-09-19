import { useState } from "react";
import { useAuth } from "../hooks/useAuth";

export function LoginGate({ children }: { children: (creds: NonNullable<ReturnType<typeof useAuth>["creds"]>) => React.ReactNode }) {
  const { creds, login, logout, error, verifying } = useAuth();
  const [username, setUsername] = useState("operator");
  const [password, setPassword] = useState("");

  if (creds) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-4 py-1.5">
          <span className="text-xs text-slate-500">Signed in as {creds.username}</span>
          <button type="button" onClick={logout} className="text-xs text-slate-500 hover:text-slate-300">
            Sign out
          </button>
        </div>
        <div className="min-h-0 flex-1">{children(creds)}</div>
      </div>
    );
  }

  return (
    <div className="flex h-full items-center justify-center bg-slate-950">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          login(username, password);
        }}
        className="w-80 space-y-3 rounded-lg border border-slate-800 bg-slate-900 p-6"
      >
        <h1 className="text-base font-semibold text-slate-100">RepairFlow operator sign-in</h1>
        <input
          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Username"
          autoFocus
        />
        <input
          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-200"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
        />
        {error && <p className="text-xs text-rose-400">{error}</p>}
        <button
          type="submit"
          disabled={verifying}
          className="w-full rounded bg-sky-600 py-1.5 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {verifying ? "Checking…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
