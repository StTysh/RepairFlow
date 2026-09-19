import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronRight, FileQuestion, StickyNote, X } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import {
  QuotedByTradeDonut,
  QuotedByYearBars,
  RecurringIssuesList,
} from "@/components/fixi/PropertyStatsCharts";
import { usePropertyHistory, usePropertyStats } from "@/hooks/use-property-history";
import { useSeedRefs } from "@/hooks/use-new-ticket";
import { statusTone } from "@/lib/fixi-data";
import { formatDate, formatPence, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";
import houseExterior from "@/assets/house-exterior.jpg";

// `address`/`postcode` are passed through from whichever screen linked here
// (currently only the ticket detail page's SummaryColumn) since
// GET /api/v1/properties/{id}/history returns only case rows, not the
// property's own address -- there's no property-by-id read endpoint in
// this phase. Landing here directly (no search params) still works; the
// header just falls back to showing the raw property id.
const searchSchema = z.object({
  address: z.string().optional(),
  postcode: z.string().optional(),
});

export const Route = createFileRoute("/properties/$propertyId/history")({
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      { title: "Property history — Fixi" },
      {
        name: "description",
        content: "Every maintenance case recorded for this property, from report to resolution.",
      },
      { property: "og:title", content: "Property history — Fixi" },
    ],
  }),
  component: HistoryPage,
});

const tabs = ["history", "property", "documents", "notes"] as const;
type Tab = (typeof tabs)[number];
const tabLabel: Record<Tab, string> = {
  history: "Maintenance history",
  property: "Property details",
  documents: "Documents",
  notes: "Notes",
};

function HistoryPage() {
  const { propertyId } = Route.useParams();
  const { address, postcode } = Route.useSearch();
  const [tab, setTab] = useState<Tab>("history");
  const history = usePropertyHistory(propertyId);
  const items = history.data?.items ?? [];
  // GET /properties/{id}/stats -- active_count/total_count here are the
  // canonical counts (same strict "CaseStatus.ACTIVE only" reading
  // DashboardMetricsResponse uses), not re-derived client-side from the
  // history items above.
  const propertyStats = usePropertyStats(propertyId);
  const statsData = propertyStats.data;
  // Full property record (address/postcode/landlord ref/access notes,
  // tenant name/phone) -- sourced from the demo seed-refs list rather than
  // a dedicated property-by-id endpoint, since none exists in this phase.
  // A property outside that seeded set (shouldn't happen via this app's
  // own "+ New Ticket" flow, but possible if this route is reached some
  // other way) just falls back to the address/postcode passed in search
  // params below.
  const seedRefs = useSeedRefs();
  const propertyDetails =
    seedRefs.data?.properties.find((p) => p.property_id === propertyId) ?? null;

  const statValue = (n: number | undefined) =>
    propertyStats.isLoading ? "…" : propertyStats.isError ? "—" : String(n ?? 0);

  const stats = [
    { value: statValue(statsData?.active_count), label: "Active tickets" },
    { value: statValue(statsData?.total_count), label: "Total tickets" },
    {
      value: propertyStats.isLoading
        ? "…"
        : propertyStats.isError
          ? "—"
          : (statsData?.build_year?.toString() ?? "—"),
      label:
        !propertyStats.isLoading && !propertyStats.isError && statsData?.build_year == null
          ? "Build year unknown"
          : "Build year",
    },
  ];

  return (
    <AppShell>
      <div className="px-8 py-6">
        <div className="flex items-center justify-between">
          {/* A plain Link rather than router.history.back(): landing here
           * directly (bookmark, shared link, refresh) leaves no history
           * entry to go back to, which would make Close a dead end. */}
          <Link
            to="/maintenance"
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" /> Close
          </Link>
        </div>

        <div className="mt-4 flex items-start justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Property history</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {address ? `${address}${postcode ? `, ${postcode}` : ""}` : propertyId}
            </p>
          </div>
          <img
            src={houseExterior}
            alt=""
            width={912}
            height={736}
            className="h-20 w-32 rounded-lg object-cover"
          />
        </div>

        <section className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-3">
          {stats.map((s) => (
            <Card key={s.label} className="px-4 py-3">
              <div className="text-lg font-bold tracking-tight">{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </Card>
          ))}
        </section>

        <div className="mt-5 flex gap-6 border-b border-border text-sm">
          {tabs.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "-mb-px border-b-2 pb-2.5 font-medium transition-colors",
                tab === t
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {tabLabel[t]}
            </button>
          ))}
        </div>

        {tab === "history" && (
          <>
            {/* Real GET /properties/{id}/stats data -- see
             * PropertyStatsCharts.tsx. Gated on isLoading/isError here
             * (mirrors the "Loading history…" / "Could not load…" rows in
             * the table below) so "no quoted work yet" is only ever shown
             * once the backend has actually confirmed `[]` -- not while
             * still waiting on the request or after it failed. */}
            <section className="mt-4 grid gap-3 xl:grid-cols-3">
              {propertyStats.isLoading ? (
                <Card className="p-4 xl:col-span-3">
                  <p className="py-6 text-center text-xs text-muted-foreground">
                    Loading property insights…
                  </p>
                </Card>
              ) : propertyStats.isError ? (
                <Card className="p-4 xl:col-span-3">
                  <p className="py-6 text-center text-xs text-destructive">
                    Could not load property insights.
                  </p>
                </Card>
              ) : (
                <>
                  <QuotedByTradeDonut data={statsData?.quoted_by_trade ?? []} />
                  <QuotedByYearBars data={statsData?.quoted_by_year ?? []} />
                  <RecurringIssuesList data={statsData?.recurring_issues ?? []} />
                </>
              )}
            </section>

            <Card className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[900px] text-[13px]">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2.5 font-medium">Date ↓</th>
                    <th className="px-4 py-2.5 font-medium">Issue</th>
                    <th className="px-4 py-2.5 font-medium">Trade</th>
                    <th className="px-4 py-2.5 font-medium">Status</th>
                    <th className="px-4 py-2.5 font-medium">Outcome</th>
                    <th className="px-4 py-2.5 font-medium">Contractor</th>
                    <th className="px-4 py-2.5 font-medium">Quoted</th>
                    <th className="px-4 py-2.5 font-medium">View</th>
                  </tr>
                </thead>
                <tbody>
                  {history.isLoading && (
                    <tr>
                      <td
                        colSpan={8}
                        className="px-4 py-8 text-center text-xs text-muted-foreground"
                      >
                        Loading history…
                      </td>
                    </tr>
                  )}
                  {history.isError && (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center text-xs text-destructive">
                        Could not load property history.
                      </td>
                    </tr>
                  )}
                  {!history.isLoading && items.length === 0 && (
                    <tr>
                      <td
                        colSpan={8}
                        className="px-4 py-8 text-center text-xs text-muted-foreground"
                      >
                        No recorded cases for this property yet.
                      </td>
                    </tr>
                  )}
                  {items.map((h) => (
                    <tr
                      key={h.case_id}
                      className="border-b border-border last:border-0 transition-colors hover:bg-muted/60"
                    >
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(h.created_at)}
                      </td>
                      <td className="max-w-sm truncate px-4 py-3 font-medium" title={h.title}>
                        {h.title}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {h.trade ? titleCase(h.trade) : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Pill tone={statusTone(h.status)}>{h.status}</Pill>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{h.outcome ?? "—"}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {h.contractor_name ?? "—"}
                      </td>
                      <td className="px-4 py-3 font-medium">
                        {formatPence(h.quoted_pence) ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          to="/maintenance/tickets/$ticketId/{-$section}"
                          params={{ ticketId: h.case_id, section: undefined }}
                          className="inline-flex rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                        >
                          <ChevronRight className="h-4 w-4" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </>
        )}

        {tab === "property" && (
          <Card className="mt-4 p-5">
            {seedRefs.isLoading ? (
              <p className="text-xs text-muted-foreground">Loading property details…</p>
            ) : seedRefs.isError ? (
              <p className="text-xs text-destructive">Could not load property details.</p>
            ) : propertyDetails ? (
              <div className="divide-y divide-border">
                <PropertyDetailRow label="Address" value={propertyDetails.address_line} />
                <PropertyDetailRow label="Postcode" value={propertyDetails.postcode} />
                <PropertyDetailRow
                  label="Landlord reference"
                  value={propertyDetails.landlord_reference || "—"}
                />
                <PropertyDetailRow
                  label="Roof responsibility"
                  value={titleCase(propertyDetails.roof_responsibility)}
                />
                <PropertyDetailRow
                  label="Access notes"
                  value={propertyDetails.access_notes ?? "No access notes recorded."}
                />
                <PropertyDetailRow label="Tenant" value={propertyDetails.tenant_name} />
                <PropertyDetailRow
                  label="Tenant phone"
                  value={propertyDetails.tenant_phone ?? "No phone on file"}
                />
              </div>
            ) : (
              <div className="divide-y divide-border">
                <PropertyDetailRow label="Address" value={address ?? propertyId} />
                <PropertyDetailRow label="Postcode" value={postcode ?? "—"} />
                <p className="pt-3 text-xs text-muted-foreground">
                  Further property details aren't available from this view.
                </p>
              </div>
            )}
          </Card>
        )}

        {tab === "documents" && (
          <Card className="mt-4 flex flex-col items-center justify-center gap-2 p-10 text-center">
            <FileQuestion className="h-8 w-8 text-muted-foreground" />
            <p className="text-[13px] font-medium">No documents uploaded for this property yet.</p>
          </Card>
        )}

        {tab === "notes" && (
          <Card className="mt-4 flex flex-col items-center justify-center gap-2 p-10 text-center">
            <StickyNote className="h-8 w-8 text-muted-foreground" />
            <p className="text-[13px] font-medium">No notes recorded for this property yet.</p>
          </Card>
        )}
      </div>
    </AppShell>
  );
}

function PropertyDetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-[13px]">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}
