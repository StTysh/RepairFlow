import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronRight, X } from "lucide-react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { propertyHistory, propertyStats } from "@/lib/fixi-data";
import { cn } from "@/lib/utils";
import houseExterior from "@/assets/house-exterior.jpg";

export const Route = createFileRoute("/properties/14-king-street/history")({
  head: () => ({
    meta: [
      { title: "Property history — 14 King Street — Fixi" },
      {
        name: "description",
        content:
          "Full maintenance history for 14 King Street, Walthamstow: every issue, outcome, contractor and cost since 2021.",
      },
      { property: "og:title", content: "Property history — 14 King Street — Fixi" },
      {
        property: "og:description",
        content: "Full maintenance history for 14 King Street, Walthamstow.",
      },
    ],
  }),
  component: HistoryPage,
});

const tabs = ["Maintenance history", "Property details", "Documents", "Notes"];

function HistoryPage() {
  return (
    <AppShell>
      <div className="px-8 py-6">
        <div className="flex items-center justify-between">
          <Link
            to="/maintenance/tickets/$ticketId/{-$section}"
            params={{ ticketId: "1042", section: undefined }}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" /> Close
          </Link>
          <Link
            to="/maintenance/tickets/$ticketId/{-$section}"
            params={{ ticketId: "1042", section: undefined }}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </Link>
        </div>

        <div className="mt-4 flex items-start justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Property history</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              14 King Street, Walthamstow, E17 6QX
            </p>
          </div>
          <img
            src={houseExterior}
            alt="14 King Street"
            width={912}
            height={736}
            className="h-20 w-32 rounded-lg object-cover"
          />
        </div>

        <section className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          {propertyStats.map((s) => (
            <Card key={s.label} className="px-4 py-3">
              <div className="text-lg font-bold tracking-tight">{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </Card>
          ))}
        </section>

        <div className="mt-5 flex gap-6 border-b border-border text-sm">
          {tabs.map((t, i) => (
            <button
              key={t}
              className={cn(
                "-mb-px border-b-2 pb-2.5 font-medium transition-colors",
                i === 0
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t}
            </button>
          ))}
        </div>

        <Card className="mt-4 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">Date ↓</th>
                <th className="px-4 py-2.5 font-medium">Issue</th>
                <th className="px-4 py-2.5 font-medium">State</th>
                <th className="px-4 py-2.5 font-medium">Outcome</th>
                <th className="px-4 py-2.5 font-medium">Contractor</th>
                <th className="px-4 py-2.5 font-medium">Cost</th>
                <th className="px-4 py-2.5 font-medium">View</th>
              </tr>
            </thead>
            <tbody>
              {propertyHistory.map((h) => (
                <tr
                  key={h.date}
                  className="border-b border-border last:border-0 transition-colors hover:bg-muted/60"
                >
                  <td className="px-4 py-3 text-muted-foreground">{h.date}</td>
                  <td className="px-4 py-3 font-medium">{h.issue}</td>
                  <td className="px-4 py-3">
                    <Pill tone="green">{h.state}</Pill>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{h.outcome}</td>
                  <td className="px-4 py-3 text-muted-foreground">{h.contractor}</td>
                  <td className="px-4 py-3">{h.cost}</td>
                  <td className="px-4 py-3">
                    <button className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </AppShell>
  );
}
