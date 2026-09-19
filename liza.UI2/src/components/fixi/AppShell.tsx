import { Link } from "@tanstack/react-router";
import {
  Home,
  Wrench,
  Building2,
  HardHat,
  Users,
  BarChart3,
  MessageSquare,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { label: "Overview", icon: Home, to: "/maintenance" as const, active: false },
  { label: "Maintenance", icon: Wrench, to: "/maintenance" as const, active: true },
  { label: "Properties", icon: Building2, to: "/properties/14-king-street/history" as const, active: false },
  { label: "Contractors", icon: HardHat, to: "/maintenance" as const, active: false },
  { label: "Tenants", icon: Users, to: "/maintenance" as const, active: false },
  { label: "Insights", icon: BarChart3, to: "/maintenance" as const, active: false },
  { label: "Messages", icon: MessageSquare, to: "/maintenance" as const, active: false },
  { label: "Reports", icon: FileText, to: "/maintenance" as const, active: false },
];

export function FixiLogo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-soft text-primary">
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
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
                item.active
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
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-timeline-done opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-timeline-done" />
            </span>
            <div className="leading-tight">
              <div className="text-xs font-semibold">AI agent active</div>
              <div className="text-[11px] text-muted-foreground">Handling 24 tasks</div>
            </div>
          </div>
          <div className="flex items-center gap-2.5 px-1">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-status-purple text-[11px] font-semibold text-status-purple-foreground">
              VS
            </div>
            <div className="leading-tight">
              <div className="text-xs font-semibold">Vlad Shuliar</div>
              <div className="text-[11px] text-muted-foreground">Roche Properties</div>
            </div>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-xl border border-border bg-card shadow-card", className)}>{children}</div>
  );
}
