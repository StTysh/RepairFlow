import { Link, useRouterState } from "@tanstack/react-router";
import { Wrench, Building2 } from "lucide-react";
import { useDashboardMetrics } from "@/hooks/use-dashboard-metrics";
import { useAuthedCreds } from "@/lib/auth-context";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

// Contractors/Tenants/Insights/Messages/Reports were removed rather than
// left pointing at /maintenance: none has a dedicated screen or backing
// data model (Messages specifically was a deliberate product decision --
// see docs on the Timeline being the one activity feed, not a generic
// chat). A nav item that goes nowhere real is worse than no nav item.
const nav = [
  { label: "Maintenance", icon: Wrench, to: "/maintenance" as const },
  { label: "Properties", icon: Building2, to: "/properties" as const },
];

export function FixiLogo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-soft text-primary">
        <svg
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 11.5 12 4l9 7.5" />
          <path d="M5 10v9h14v-9" />
          <path d="M10 19v-5h4v5" />
        </svg>
      </div>
      <div className="leading-tight">
        <div className="text-[17px] font-bold tracking-tight text-foreground">Fixi</div>
        <div className="text-[10.5px] text-muted-foreground">Properties, solved.</div>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const creds = useAuthedCreds();
  const metrics = useDashboardMetrics();
  const activeCount = metrics.data?.active;
  // Real signal from the backend (any job due/leased or a coordinator run
  // actually mid-flight) -- not decorative. Pulses only while something is
  // genuinely happening; sits still and grey when idle.
  const agentThinking = metrics.data?.agent_active ?? false;
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  return (
    <div className="flex min-h-screen w-full bg-background font-sans text-foreground antialiased">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-4 py-5 lg:flex">
        <FixiLogo />
        <nav className="mt-7 flex flex-col gap-0.5">
          {nav.map((item) => (
            <Link
              key={item.label}
              to={item.to}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors",
                pathname.startsWith(item.to)
                  ? "bg-sidebar-primary text-sidebar-primary-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent",
              )}
            >
              <item.icon className="h-4 w-4" strokeWidth={1.9} />
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-3">
          <div className="flex items-center gap-2.5 rounded-lg border border-sidebar-border bg-card px-3 py-2.5 shadow-card">
            <span className="relative flex h-2.5 w-2.5">
              {agentThinking && (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-timeline-done opacity-60" />
              )}
              <span
                className={cn(
                  "relative inline-flex h-2.5 w-2.5 rounded-full",
                  agentThinking ? "bg-timeline-done" : "bg-muted-foreground/40",
                )}
              />
            </span>
            <div className="leading-tight">
              <div className="text-xs font-semibold">
                {agentThinking ? "AI agent thinking…" : "AI agent idle"}
              </div>
              <div className="text-[11px] text-muted-foreground">
                {activeCount !== undefined
                  ? `Handling ${activeCount} active case${activeCount === 1 ? "" : "s"}`
                  : "Handling cases…"}
              </div>
            </div>
          </div>
          {/* Real signed-in operator (see LoginGate's "Signed in as" bar) --
           * used to be a hardcoded "Vlad Shuliar / Roche Properties" from
           * the original mockup with no backing user/org model anywhere in
           * this API. No organisation concept exists here, so this only
           * shows what's actually known: the credential the operator
           * signed in with. */}
          <div className="flex items-center gap-2.5 px-1">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-status-purple text-[11px] font-semibold text-status-purple-foreground">
              {initials(creds.username)}
            </div>
            <div className="text-xs font-semibold">{creds.username}</div>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-xl border border-border bg-card shadow-card", className)}>
      {children}
    </div>
  );
}
