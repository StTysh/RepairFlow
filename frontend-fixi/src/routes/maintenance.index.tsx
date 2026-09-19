import { createFileRoute, Link } from "@tanstack/react-router";
import { Bell, ChevronDown, MoreHorizontal, Plus, Search } from "lucide-react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { PriorityBadge, StatusBadge } from "@/components/fixi/Badge";
import { kpis, tickets } from "@/lib/fixi-data";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/maintenance/")({
  head: () => ({
    meta: [
      { title: "Maintenance — Fixi" },
      {
        name: "description",
        content:
          "All property issues, from report to resolution. Track open, in-progress and resolved maintenance tickets.",
      },
      { property: "og:title", content: "Maintenance — Fixi" },
      { property: "og:description", content: "All property issues, from report to resolution." },
    ],
  }),
  component: MaintenancePage,
});

const filters = ["All", "Open", "In progress", "Waiting", "Resolved"];

function MaintenancePage() {
  return (
    <AppShell>
      <div className="px-8 py-6">
        <header className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Maintenance</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              All property issues, from report to resolution.
            </p>
          </div>
          <div className="flex items-center gap-2.5">
            <label className="flex h-9 w-72 items-center gap-2 rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground shadow-card">
              <Search className="h-4 w-4" />
              <input
                className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
                placeholder="Search tickets, addresses, tenants..."
              />
            </label>
            <button className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground shadow-card hover:bg-accent">
              <Bell className="h-4 w-4" />
              <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-destructive" />
            </button>
            <button className="flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-sm font-medium text-primary-foreground shadow-card transition-colors hover:bg-primary/90">
              <Plus className="h-4 w-4" /> New Ticket
            </button>
          </div>
        </header>

        <section className="mt-6 grid grid-cols-2 gap-3 xl:grid-cols-5">
          {kpis.map((k) => (
            <Card key={k.label} className="px-4 py-3.5">
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold tracking-tight">{k.value}</span>
                {k.badge && (
                  <span className="rounded-md bg-status-green px-1.5 py-0.5 text-[11px] font-semibold text-status-green-foreground">
                    {k.badge}
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">{k.label}</div>
            </Card>
          ))}
        </section>

        <section className="mt-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-1.5">
            {filters.map((f, i) => (
              <button
                key={f}
                className={cn(
                  "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
                  i === 0
                    ? "border-foreground bg-foreground text-background"
                    : "border-border bg-card text-foreground hover:bg-accent",
                )}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            {["All priorities", "All properties"].map((d) => (
              <button
                key={d}
                className="flex h-8 items-center gap-6 rounded-lg border border-border bg-card px-3 text-xs font-medium text-foreground hover:bg-accent"
              >
                {d} <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            ))}
          </div>
        </section>

        <Card className="mt-4 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">#</th>
                <th className="px-4 py-2.5 font-medium">Issue</th>
                <th className="px-4 py-2.5 font-medium">Address</th>
                <th className="px-4 py-2.5 font-medium">Priority</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Assigned to</th>
                <th className="px-4 py-2.5 font-medium">Updated ↓</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {tickets.map((t) => {
                const isCase = t.id === 1042;
                return (
                  <tr
                    key={t.id}
                    className={cn(
                      "group border-b border-border last:border-0 transition-colors",
                      isCase
                        ? "bg-selected outline outline-2 -outline-offset-2 outline-selected-ring"
                        : "hover:bg-muted/60",
                    )}
                  >
                    <td className="px-4 py-3 text-muted-foreground">
                      {isCase ? (
                        <Link
                          to="/maintenance/tickets/$ticketId/{-$section}"
                          params={{ ticketId: "1042", section: undefined }}
                          className="block"
                        >
                          #{t.id}
                        </Link>
                      ) : (
                        `#${t.id}`
                      )}
                    </td>
                    <td className="px-4 py-3 font-medium">
                      {isCase ? (
                        <Link
                          to="/maintenance/tickets/$ticketId/{-$section}"
                          params={{ ticketId: "1042", section: undefined }}
                          className="block hover:underline"
                        >
                          {t.issue}
                        </Link>
                      ) : (
                        t.issue
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{t.address}</td>
                    <td className="px-4 py-3">
                      <PriorityBadge priority={t.priority} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={t.status} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{t.assignedTo ?? "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{t.updated}</td>
                    <td className="px-4 py-3 text-right">
                      <button className="rounded-md p-1 text-muted-foreground hover:bg-accent">
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>
    </AppShell>
  );
}
