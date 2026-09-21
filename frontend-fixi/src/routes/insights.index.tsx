import { createFileRoute, useNavigate, useRouterState, Link } from "@tanstack/react-router";
import { format, subMonths } from "date-fns";
import { ChevronRight, X } from "lucide-react";
import { useMemo, useState } from "react";
import { readFlag, readParam } from "@/lib/search-params";
import { AppShell, Card, PageContainer } from "@/components/fixi/AppShell";
import { StatusBadge } from "@/components/fixi/Badge";
import {
  CaseVolumeChart,
  CategoryBreakdownDonut,
  RecurringIssuesTable,
  ResolutionTimeChart,
  SpendByYearChart,
  recurringIssueKey,
} from "@/components/fixi/Charts";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import {
  useAnalyticsProperties,
  useInsights,
  useInsightsCases,
  type InsightsCaseRow,
  type InsightsFilters,
  type RecurringIssueRow,
  type ResolutionBucket,
} from "@/hooks/use-analytics";
import type { Trade } from "@/api/types";
import { formatDate, formatPence, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// No zod validateSearch here -- verified elsewhere in this app
// (properties.$propertyId.history.tsx) that validateSearch reproducibly
// freezes the renderer on a hard navigation to a non-prerendered route
// (only "/" is prerendered; every other route hits the SPA fallback shell
// during hydration). Unlike that route, this one DOES navigate (every
// filter change pushes a new query string), so search is read reactively
// off router state (useRouterState) rather than a one-off window.location
// read, and written with a plain, unvalidated object through useNavigate.
export const Route = createFileRoute("/insights/")({
  head: () => ({
    meta: [
      { title: "Insights — Fixi" },
      {
        name: "description",
        content:
          "Case volume, category breakdown, spend and recurring issues across the portfolio.",
      },
      { property: "og:title", content: "Insights — Fixi" },
    ],
  }),
  component: InsightsPage,
});

const TRADES: Trade[] = ["ROOFING", "SCAFFOLDING", "PLUMBING", "ELECTRICAL", "OTHER"];

function todayStr(): string {
  return format(new Date(), "yyyy-MM-dd");
}

function monthsAgoStr(months: number): string {
  return format(subMonths(new Date(), months), "yyyy-MM-dd");
}

const DEFAULT_MONTHS = 24;

const PRESETS: Array<{ label: string; months: number | null }> = [
  { label: "3 months", months: 3 },
  { label: "6 months", months: 6 },
  { label: "12 months", months: 12 },
  { label: "24 months", months: 24 },
  { label: "All time", months: null },
];

function formatMonthLabel(month: string): string {
  const parsed = new Date(`${month}-01T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return month;
  return format(parsed, "MMM yyyy");
}

/** Everything needed to drive the inline drill-down panel: the human label
 * shown in its header, and the exact filters passed to GET
 * /insights/cases. `bucket` is only set for a resolution-time drill-down,
 * where the API gives no per-bucket filter param (see use-analytics.ts) --
 * when its hour bounds are known, matching rows are narrowed client-side
 * from real created_at/resolved_at timestamps; when they aren't, the panel
 * says plainly that it's showing the whole current filter set. */
interface Drilldown {
  key: string;
  label: string;
  filters: InsightsFilters;
  bucket?: { label: string; minHours: number | null; maxHours: number | null };
}

function InsightsPage() {
  const searchStr = useRouterState({ select: (s) => s.location.searchStr });
  const navigate = useNavigate({ from: Route.fullPath });

  const params = useMemo(() => new URLSearchParams(searchStr), [searchStr]);
  const filters: InsightsFilters = useMemo(
    () => ({
      date_from: readParam(params, "date_from") ?? monthsAgoStr(DEFAULT_MONTHS),
      date_to: readParam(params, "date_to") ?? todayStr(),
      property_id: readParam(params, "property_id"),
      category: readParam(params, "category") as Trade | undefined,
      include_archived: readFlag(params, "include_archived"),
    }),
    [params],
  );

  function patchSearch(patch: Record<string, string | undefined>) {
    void navigate({
      // Route has no validateSearch (see comment above), so TanStack
      // Router treats its search schema as unvalidated/untyped -- this app
      // has no existing precedent for a navigating route's search updater,
      // so this is a plain updater function (a standard NavigateOptions
      // pattern: (prevSearch) => nextSearch) built and verified against
      // `npx tsc --noEmit` rather than a typed route helper.
      search: (prev: Record<string, string>) => {
        const next: Record<string, string> = { ...prev };
        for (const [key, value] of Object.entries(patch)) {
          if (value === undefined || value === "") delete next[key];
          else next[key] = value;
        }
        return next;
      },
      replace: true,
    });
  }

  function applyPreset(months: number | null) {
    patchSearch({
      date_from: months === null ? "1970-01-01" : monthsAgoStr(months),
      date_to: todayStr(),
    });
  }

  const activePresetMonths = useMemo(() => {
    if (filters.date_to !== todayStr()) return undefined;
    for (const preset of PRESETS) {
      if (preset.months === null) {
        if (filters.date_from === "1970-01-01") return preset.months;
        continue;
      }
      if (filters.date_from === monthsAgoStr(preset.months)) return preset.months;
    }
    return undefined;
  }, [filters.date_from, filters.date_to]);

  const properties = useAnalyticsProperties();
  const insights = useInsights(filters);

  function retryInsights() {
    void insights.refetch();
  }

  const [drilldown, setDrilldown] = useState<Drilldown | null>(null);

  function toggleDrilldown(next: Drilldown) {
    setDrilldown((prev) => (prev?.key === next.key ? null : next));
  }

  function handleSelectMonth(month: string) {
    const [y, m] = month.split("-").map(Number);
    if (!y || !m) return;
    const from = `${month}-01`;
    const lastDay = new Date(y, m, 0).getDate();
    const to = `${month}-${String(lastDay).padStart(2, "0")}`;
    toggleDrilldown({
      key: `month:${month}`,
      label: `Cases opened in ${formatMonthLabel(month)}`,
      filters: { ...filters, date_from: from, date_to: to },
    });
  }

  function handleSelectTrade(trade: Trade) {
    toggleDrilldown({
      key: `trade:${trade}`,
      label: `${titleCase(trade)} cases`,
      filters: { ...filters, category: trade },
    });
  }

  function handleSelectYear(year: number) {
    toggleDrilldown({
      key: `year:${year}`,
      label: `Cases in ${year}`,
      filters: { ...filters, date_from: `${year}-01-01`, date_to: `${year}-12-31` },
    });
  }

  function handleSelectIssue(issue: RecurringIssueRow) {
    toggleDrilldown({
      key: `issue:${recurringIssueKey(issue)}`,
      label: `${titleCase(issue.trade)} at ${issue.property_address}`,
      filters: { ...filters, property_id: issue.property_id, category: issue.trade },
    });
  }

  function handleSelectBucket(bucket: ResolutionBucket) {
    toggleDrilldown({
      key: `bucket:${bucket.bucket}`,
      label: `Resolution time: ${bucket.bucket}`,
      filters: { ...filters },
      bucket: {
        label: bucket.bucket,
        minHours: bucket.min_hours,
        maxHours: bucket.max_hours,
      },
    });
  }

  const data = insights.data;
  const includesArchived = data?.includes_archived_history ?? false;

  return (
    <AppShell>
      <PageContainer
        title="Insights"
        description="Case volume, category breakdown, spend and recurring issues across the portfolio."
      >
        {/* --- Filters -------------------------------------------------- */}
        <Card className="flex flex-wrap items-end gap-4 p-4">
          <div className="flex flex-wrap items-center gap-1.5">
            {PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => applyPreset(preset.months)}
                aria-pressed={activePresetMonths === preset.months}
                className={cn(
                  "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
                  activePresetMonths === preset.months
                    ? "border-foreground bg-foreground text-background"
                    : "border-border bg-card text-foreground hover:bg-accent",
                )}
              >
                {preset.label}
              </button>
            ))}
          </div>

          <label className="flex flex-col gap-1 text-micro font-medium text-muted-foreground">
            From
            <input
              type="date"
              value={filters.date_from}
              max={filters.date_to}
              onChange={(e) => patchSearch({ date_from: e.target.value })}
              className="h-8 rounded-lg border border-border bg-card px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="flex flex-col gap-1 text-micro font-medium text-muted-foreground">
            To
            <input
              type="date"
              value={filters.date_to}
              min={filters.date_from}
              onChange={(e) => patchSearch({ date_to: e.target.value })}
              className="h-8 rounded-lg border border-border bg-card px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
            />
          </label>

          <label className="flex flex-col gap-1 text-micro font-medium text-muted-foreground">
            Property
            <select
              value={filters.property_id ?? ""}
              onChange={(e) => patchSearch({ property_id: e.target.value || undefined })}
              className="h-8 min-w-[160px] max-w-[220px] rounded-lg border border-border bg-card px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">All properties</option>
              {(properties.data?.items ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.address_line}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-micro font-medium text-muted-foreground">
            Category
            <select
              value={filters.category ?? ""}
              onChange={(e) => patchSearch({ category: e.target.value || undefined })}
              className="h-8 rounded-lg border border-border bg-card px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">All categories</option>
              {TRADES.map((t) => (
                <option key={t} value={t}>
                  {titleCase(t)}
                </option>
              ))}
            </select>
          </label>

          <label className="flex h-8 items-center gap-1.5 text-xs font-medium text-foreground">
            <input
              type="checkbox"
              checked={filters.include_archived}
              onChange={(e) =>
                patchSearch({ include_archived: e.target.checked ? "true" : "false" })
              }
              className="h-3.5 w-3.5 rounded border-border"
            />
            Include archival sample history
          </label>
        </Card>

        {includesArchived && (
          <p className="mt-2 text-micro font-medium text-status-amber-foreground">
            Includes {data?.archived_case_count ?? "an unknown number of"} archival sample case
            {data?.archived_case_count === 1 ? "" : "s"} alongside real operational cases.
          </p>
        )}

        {/* --- Charts ----------------------------------------------------- */}
        {insights.isLoading ? (
          <div className="mt-4">
            <LoadingRows rows={5} />
          </div>
        ) : insights.isError ? (
          <ErrorState
            className="mt-4"
            {...(insights.error instanceof Error ? { detail: insights.error.message } : {})}
            onRetry={retryInsights}
          />
        ) : !data ||
          ((data.case_volume_by_month ?? []).length === 0 &&
            (data.category_breakdown ?? []).length === 0 &&
            (data.spend_by_year ?? []).length === 0 &&
            (data.recurring_issues ?? []).length === 0) ? (
          <EmptyState
            className="mt-4"
            icon={ChevronRight}
            title="Nothing in this range yet"
            description="No cases fall inside the selected date range and filters. Widen the range or clear a filter."
          />
        ) : (
          /* Three columns from 2xl, not two. Measured at a 2552px
           * viewport: two columns made every card 719px wide and every
           * plot inside one 5.6:1 to 8.6:1, which is a strip, not a
           * chart. Three columns put the cards at ~556px and the plots
           * at 2.5:1 to 3:1. Five cards do not divide by three, so the
           * layout is two rows: the three plots, then resolution time
           * beside the recurring-issues list at its existing
           * xl:col-span-2 -- which fills the second row exactly. (Case
           * volume was tried at 2xl:col-span-2 for its 24 columns; at
           * 1097px its own plot went back to 5.3:1, so the width goes
           * to the bar spacing inside the card instead.)
           */
          <div className="mt-4 grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
            <CaseVolumeChart
              data={data.case_volume_by_month ?? []}
              selectedMonth={drilldown?.key.startsWith("month:") ? drilldown.key.slice(6) : null}
              onSelectMonth={handleSelectMonth}
            />
            <CategoryBreakdownDonut
              data={data.category_breakdown ?? []}
              selectedTrade={
                drilldown?.key.startsWith("trade:") ? (drilldown.key.slice(6) as Trade) : null
              }
              onSelectTrade={handleSelectTrade}
            />
            <SpendByYearChart
              data={data.spend_by_year ?? []}
              selectedYear={
                drilldown?.key.startsWith("year:") ? Number(drilldown.key.slice(5)) : null
              }
              onSelectYear={handleSelectYear}
            />
            <ResolutionTimeChart
              data={data.resolution_time_distribution ?? []}
              averageHours={data.average_hours}
              medianHours={data.median_hours}
              selectedBucket={drilldown?.key.startsWith("bucket:") ? drilldown.key.slice(7) : null}
              onSelectBucket={handleSelectBucket}
            />
            <div className="xl:col-span-2">
              <RecurringIssuesTable
                data={data.recurring_issues ?? []}
                selectedKey={drilldown?.key.startsWith("issue:") ? drilldown.key.slice(6) : null}
                onSelectIssue={handleSelectIssue}
              />
            </div>
          </div>
        )}

        {/* --- Drill-down panel --------------------------------------------- */}
        {drilldown && <DrilldownPanel drilldown={drilldown} onClose={() => setDrilldown(null)} />}
      </PageContainer>
    </AppShell>
  );
}

function resolutionHours(row: InsightsCaseRow): number | null {
  if (!row.resolved_at) return null;
  const created = new Date(row.created_at).getTime();
  const resolved = new Date(row.resolved_at).getTime();
  if (Number.isNaN(created) || Number.isNaN(resolved)) return null;
  return (resolved - created) / 3_600_000;
}

function DrilldownPanel({ drilldown, onClose }: { drilldown: Drilldown; onClose: () => void }) {
  const cases = useInsightsCases(drilldown.filters);
  const allItems = cases.data?.items ?? [];

  function retryCases() {
    void cases.refetch();
  }

  const bucketKnown =
    drilldown.bucket !== undefined &&
    drilldown.bucket.minHours !== null &&
    drilldown.bucket.maxHours !== null;

  const items = useMemo(() => {
    if (!drilldown.bucket || !bucketKnown) return allItems;
    const { minHours, maxHours } = drilldown.bucket;
    return allItems.filter((row) => {
      const hours = resolutionHours(row);
      if (hours === null) return false;
      return hours >= (minHours ?? 0) && hours <= (maxHours ?? Infinity);
    });
  }, [allItems, drilldown.bucket, bucketKnown]);

  return (
    <Card className="mt-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-section font-semibold">{drilldown.label}</h2>
          {/* The API serves each bucket's real hour bounds, so this narrows
           * to the bucket exactly. The fallback below still exists for a
           * bucket whose bounds are somehow absent -- and says so, rather
           * than quietly showing a wider set than the heading claims. */}
          {drilldown.bucket && !bucketKnown && (
            <p className="mt-0.5 text-micro text-muted-foreground">
              Hour bounds are missing for this bucket, so this shows every case in the current
              filters rather than only this bucket.
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close drill-down"
          className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {cases.isLoading ? (
        <div className="mt-3">
          <LoadingRows rows={3} />
        </div>
      ) : cases.isError ? (
        <ErrorState
          className="mt-3"
          {...(cases.error instanceof Error ? { detail: cases.error.message } : {})}
          onRetry={retryCases}
        />
      ) : items.length === 0 ? (
        <EmptyState
          className="mt-3"
          icon={ChevronRight}
          title="No cases match"
          description="Nothing fits this specific slice of the data."
        />
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-body">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-2 py-2 font-medium">#</th>
                <th className="px-2 py-2 font-medium">Title</th>
                <th className="px-2 py-2 font-medium">Address</th>
                <th className="px-2 py-2 font-medium">Status</th>
                <th className="px-2 py-2 font-medium">Created</th>
                <th className="px-2 py-2 font-medium">Quoted</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-border last:border-0 transition-colors hover:bg-muted/60"
                >
                  <td className="px-2 py-2 text-muted-foreground">#{row.case_number}</td>
                  <td className="max-w-xs truncate px-2 py-2 font-medium" title={row.title}>
                    {row.title}
                  </td>
                  <td className="px-2 py-2 text-muted-foreground">{row.property_address ?? "—"}</td>
                  <td className="px-2 py-2">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="px-2 py-2 text-muted-foreground">{formatDate(row.created_at)}</td>
                  <td className="px-2 py-2 font-medium">{formatPence(row.quoted_pence) ?? "—"}</td>
                  <td className="px-2 py-2 text-right">
                    <Link
                      to="/maintenance/tickets/$ticketId/{-$section}"
                      params={{ ticketId: row.id, section: undefined }}
                      className="inline-flex rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
