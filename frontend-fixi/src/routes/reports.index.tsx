import { createFileRoute, useNavigate, useRouterState } from "@tanstack/react-router";
import { format, startOfMonth, startOfYear, subDays } from "date-fns";
import { Download, FileQuestion, Printer } from "lucide-react";
import { useMemo } from "react";
import type { Trade } from "@/api/types";
import { AppShell, Card, PageContainer } from "@/components/fixi/AppShell";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import {
  useExportReportsCsv,
  useReportProperties,
  useReportsSummary,
  type ReportSection,
  type ReportsFilters,
} from "@/hooks/use-reports";
import { formatDate, formatPence, titleCase } from "@/lib/format";
import { readFlag, readParam } from "@/lib/search-params";
import { cn } from "@/lib/utils";

// No zod validateSearch here -- same app-wide reasoning as
// contractors.index.tsx / tenants.index.tsx / insights.index.tsx (see
// properties.$propertyId.history.tsx's Route comment for the original
// finding: validateSearch reproducibly froze the renderer on a hard
// navigation to a non-prerendered route). This route DOES navigate on
// every filter change, so -- like insights.index.tsx, whose date-range +
// property + category + archived-flag filters this page mirrors almost
// exactly -- search is read reactively off router state (useRouterState)
// rather than a one-off window.location read, and written with a plain,
// unvalidated updater through useNavigate. Filters live in the URL so a
// filtered report is linkable and survives a reload; see search-params.ts
// for why raw URLSearchParams reads go through readParam/readFlag rather
// than a naive `=== "true"` check.
export const Route = createFileRoute("/reports/")({
  head: () => ({
    meta: [
      { title: "Reports — Fixi" },
      {
        name: "description",
        content: "Maintenance, spend, resolution-time and recurring-issue reporting.",
      },
    ],
  }),
  component: ReportsPage,
});

const TRADES: Trade[] = ["ROOFING", "SCAFFOLDING", "PLUMBING", "ELECTRICAL", "OTHER"];

type Preset = "7d" | "30d" | "90d" | "month" | "year" | "all" | "custom";

const PRESET_LABEL: Record<Preset, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 90 days",
  month: "This month",
  year: "This year",
  all: "All time",
  custom: "Custom",
};

const PRESET_VALUES: Preset[] = ["7d", "30d", "90d", "month", "year", "all", "custom"];

// The default a bare, unfiltered "/reports" URL must render -- matches
// this page's previous `useState<Preset>("30d")` initial value exactly,
// so an unfiltered URL keeps rendering what it always did.
const DEFAULT_PRESET: Preset = "30d";

function isPreset(value: string | undefined): value is Preset {
  return value !== undefined && (PRESET_VALUES as string[]).includes(value);
}

function presetRange(preset: Preset): { from: string; to: string } {
  const today = new Date();
  const to = format(today, "yyyy-MM-dd");
  switch (preset) {
    case "7d":
      return { from: format(subDays(today, 6), "yyyy-MM-dd"), to };
    case "30d":
      return { from: format(subDays(today, 29), "yyyy-MM-dd"), to };
    case "90d":
      return { from: format(subDays(today, 89), "yyyy-MM-dd"), to };
    case "month":
      return { from: format(startOfMonth(today), "yyyy-MM-dd"), to };
    case "year":
      return { from: format(startOfYear(today), "yyyy-MM-dd"), to };
    default:
      return { from: "", to: "" };
  }
}

function formatCell(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (/pence/i.test(key)) return formatPence(value) ?? "—";
    return value.toLocaleString();
  }
  if (typeof value === "string") {
    if (/(_at|date)$/i.test(key) && !Number.isNaN(Date.parse(value))) return formatDate(value);
    return value;
  }
  return JSON.stringify(value);
}

function formatStat(key: string, value: number): string {
  if (/pence/i.test(key)) return formatPence(value) ?? "—";
  if (/hours/i.test(key)) return `${value.toFixed(1)}h`;
  if (/(pct|percent)/i.test(key)) return `${value.toFixed(0)}%`;
  return value.toLocaleString();
}

function ReportsPage() {
  const searchStr = useRouterState({ select: (s) => s.location.searchStr });
  const navigate = useNavigate({ from: Route.fullPath });
  const params = useMemo(() => new URLSearchParams(searchStr), [searchStr]);

  const presetParam = readParam(params, "preset");
  const preset: Preset = isPreset(presetParam) ? presetParam : DEFAULT_PRESET;
  const customFrom = readParam(params, "from") ?? "";
  const customTo = readParam(params, "to") ?? "";
  const propertyId = readParam(params, "property_id") ?? "";
  const category = readParam(params, "category") ?? "";
  const includeArchived = readFlag(params, "archived");

  function patchSearch(patch: Record<string, string | undefined>) {
    void navigate({
      // Route has no validateSearch (see the comment above), so this is a
      // plain updater function over an unvalidated search object -- same
      // shape as insights.index.tsx's patchSearch.
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

  function selectPreset(next: Preset) {
    patchSearch({
      preset: next === DEFAULT_PRESET ? undefined : next,
      // Custom keeps whatever from/to are already in the URL; any other
      // preset computes its own range from today, so stale custom dates
      // are cleared instead of left dangling in the query string.
      ...(next === "custom" ? {} : { from: undefined, to: undefined }),
    });
  }

  const range = preset === "custom" ? { from: customFrom, to: customTo } : presetRange(preset);
  const filters: ReportsFilters = {
    dateFrom: range.from,
    dateTo: range.to,
    propertyId,
    category,
    includeArchived,
  };

  const summary = useReportsSummary(filters);
  const properties = useReportProperties();
  const exportCsv = useExportReportsCsv();

  const windowLabel = range.from && range.to ? `${range.from} to ${range.to}` : "All time";

  const allSectionsEmpty =
    !!summary.data &&
    [
      summary.data.maintenance,
      summary.data.spend,
      summary.data.resolution,
      summary.data.recurringIssues,
      summary.data.cases,
    ].every((s) => !s || (s.rows.length === 0 && Object.keys(s.totals).length === 0));

  return (
    <>
      <AppShell>
        <PageContainer
          title="Reports"
          description="Database-derived maintenance, spend, resolution-time and recurring-issue reporting."
          actions={
            <div className="flex items-center gap-2 print:hidden">
              <button
                type="button"
                onClick={() => window.print()}
                className="flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3.5 text-sm font-medium shadow-card transition-colors hover:bg-accent"
              >
                <Printer className="h-4 w-4" /> Print / Save as PDF
              </button>
              <button
                type="button"
                onClick={() => void exportCsv.mutateAsync(filters)}
                disabled={exportCsv.isPending}
                className="flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-sm font-medium text-primary-foreground shadow-card transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                <Download className="h-4 w-4" /> {exportCsv.isPending ? "Exporting…" : "Export CSV"}
              </button>
            </div>
          }
        >
          <div className="print:hidden">
            <FilterBar
              preset={preset}
              setPreset={selectPreset}
              customFrom={customFrom}
              customTo={customTo}
              setCustomFrom={(v) => patchSearch({ from: v || undefined })}
              setCustomTo={(v) => patchSearch({ to: v || undefined })}
              propertyId={propertyId}
              setPropertyId={(v) => patchSearch({ property_id: v || undefined })}
              category={category}
              setCategory={(v) => patchSearch({ category: v || undefined })}
              includeArchived={includeArchived}
              setIncludeArchived={(v) => patchSearch({ archived: v ? "true" : undefined })}
              propertyOptions={properties.data ?? []}
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted/40 px-4 py-2.5 text-xs text-muted-foreground">
            <span>
              Report window: <span className="font-medium text-foreground">{windowLabel}</span>
              {propertyId && (
                <>
                  {" "}
                  · Property:{" "}
                  <span className="font-medium text-foreground">
                    {properties.data?.find((p) => p.id === propertyId)?.address_line ?? propertyId}
                  </span>
                </>
              )}
              {category && (
                <>
                  {" "}
                  · Category:{" "}
                  <span className="font-medium text-foreground">{titleCase(category)}</span>
                </>
              )}
            </span>
            <span>Generated on {new Date().toLocaleString()}</span>
          </div>

          {includeArchived && (
            <p className="mt-2 text-xs text-muted-foreground">
              Includes archived / sample-history records alongside live ones (each row's{" "}
              <code className="rounded bg-muted px-1 py-0.5">record_source</code> column, where
              present, says which). The CSV export carries the same column.
            </p>
          )}

          {summary.isLoading && (
            <div className="mt-4">
              <LoadingRows rows={4} />
            </div>
          )}
          {summary.isError && (
            <ErrorState
              className="mt-4"
              detail={summary.error instanceof Error ? summary.error.message : "Unknown error"}
              onRetry={() => void summary.refetch()}
            />
          )}

          {summary.data && allSectionsEmpty && (
            <EmptyState
              className="mt-4"
              icon={FileQuestion}
              title="No data for this report window"
              description="Nothing matches the current filters. Try widening the date range, clearing the property/category filter, or including archived history."
            />
          )}

          {summary.data && !allSectionsEmpty && (
            <div className="mt-4 grid gap-4">
              <SectionPanel
                title="Maintenance summary"
                subtitle="Ticket volume and status mix for the selected window."
                section={summary.data.maintenance}
              />
              <SectionPanel
                title="Spend"
                subtitle="Quoted and actual money, kept separate -- they are never summed together."
                section={summary.data.spend}
              />
              <SectionPanel
                title="Resolution times"
                subtitle="How long cases took to reach a verified resolution."
                section={summary.data.resolution}
              />
              <SectionPanel
                title="Recurring issues"
                subtitle="Trades/issues that keep coming back at the same properties."
                section={summary.data.recurringIssues}
              />
              {/* The case-level rows every section above aggregates, and
               * exactly what Export CSV writes -- shown so the export is
               * never a set of rows nobody can see on screen first. */}
              <SectionPanel
                title="Case detail"
                subtitle="Every case behind the figures above. This is what Export CSV contains."
                section={summary.data.cases}
              />
            </div>
          )}
        </PageContainer>
      </AppShell>
    </>
  );
}

function FilterBar({
  preset,
  setPreset,
  customFrom,
  customTo,
  setCustomFrom,
  setCustomTo,
  propertyId,
  setPropertyId,
  category,
  setCategory,
  includeArchived,
  setIncludeArchived,
  propertyOptions,
}: {
  preset: Preset;
  setPreset: (p: Preset) => void;
  customFrom: string;
  customTo: string;
  setCustomFrom: (v: string) => void;
  setCustomTo: (v: string) => void;
  propertyId: string;
  setPropertyId: (v: string) => void;
  category: string;
  setCategory: (v: string) => void;
  includeArchived: boolean;
  setIncludeArchived: (v: boolean) => void;
  propertyOptions: Array<{ id: string; address_line: string }>;
}) {
  return (
    <Card className="p-3.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {(Object.keys(PRESET_LABEL) as Preset[]).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPreset(p)}
            className={cn(
              "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
              preset === p
                ? "border-foreground bg-foreground text-background"
                : "border-border bg-card text-foreground hover:bg-accent",
            )}
          >
            {PRESET_LABEL[p]}
          </button>
        ))}
      </div>

      {preset === "custom" && (
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            From
            <input
              type="date"
              value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
              className="h-8 rounded-lg border border-input bg-background px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            To
            <input
              type="date"
              value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
              className="h-8 rounded-lg border border-input bg-background px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
        </div>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <select
          aria-label="Filter by property"
          value={propertyId}
          onChange={(e) => setPropertyId(e.target.value)}
          className="h-8 rounded-lg border border-border bg-card px-2.5 text-xs font-medium text-foreground outline-none hover:bg-accent"
        >
          <option value="">All properties</option>
          {propertyOptions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.address_line}
            </option>
          ))}
        </select>

        <select
          aria-label="Filter by category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="h-8 rounded-lg border border-border bg-card px-2.5 text-xs font-medium text-foreground outline-none hover:bg-accent"
        >
          <option value="">All categories</option>
          {TRADES.map((t) => (
            <option key={t} value={t}>
              {titleCase(t)}
            </option>
          ))}
        </select>

        <label className="flex h-8 items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 text-xs font-medium text-foreground hover:bg-accent">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
            className="h-3.5 w-3.5 accent-primary"
          />
          Include archived / sample history
        </label>
      </div>
    </Card>
  );
}

function SectionPanel({
  title,
  subtitle,
  section,
}: {
  title: string;
  subtitle: string;
  section: ReportSection | null;
}) {
  const totalsEntries = section ? Object.entries(section.totals) : [];
  const rows = section?.rows ?? [];
  const columns = rows.length > 0 ? Object.keys(rows[0]!) : [];

  return (
    <Card className="break-inside-avoid p-5 print:border print:shadow-none">
      <h2 className="text-[15px] font-semibold">{title}</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>

      {totalsEntries.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {totalsEntries.map(([key, value]) => (
            <div key={key} className="rounded-lg border border-border bg-muted/40 px-3 py-2.5">
              <div className="text-lg font-bold tracking-tight">{formatStat(key, value)}</div>
              <div className="text-[11px] text-muted-foreground">{titleCase(key)}</div>
            </div>
          ))}
        </div>
      )}

      {rows.length === 0 ? (
        <p className="mt-4 text-xs text-muted-foreground">No rows for the selected filters.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[560px] text-[12px]">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                {columns.map((c) => (
                  <th key={c} className="px-2 py-2 font-medium">
                    {titleCase(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-border last:border-0">
                  {columns.map((c) => (
                    <td key={c} className="px-2 py-2">
                      {formatCell(c, row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-muted-foreground">
            {rows.length} row{rows.length === 1 ? "" : "s"} back the totals above.
          </p>
        </div>
      )}
    </Card>
  );
}
