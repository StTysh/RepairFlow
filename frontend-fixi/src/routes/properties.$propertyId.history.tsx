import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, Download, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { PropertyTabs } from "@/components/fixi/PropertyTabs";
import {
  QuotedByTradeDonut,
  QuotedByYearBars,
  RecurringIssuesList,
} from "@/components/fixi/PropertyStatsCharts";
import { usePropertyHistory, usePropertyStats } from "@/hooks/use-property-history";
import type { PropertyHistoryItem, Trade } from "@/api/types";
import { CASE_STATUSES, statusTone, type CaseStatus } from "@/lib/fixi-data";
import { formatDate, formatPence, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// `address`/`postcode` search params + the "no validateSearch" rule below
// are unchanged from the previous version of this file -- see that
// docstring, reproduced here because it's still exactly why this route reads
// search params by hand instead of through Route.useSearch().
//
// GET /api/v1/properties/{id}/history and .../stats are real, already-wired
// endpoints (backend/app/api/cases.py get_property_history /
// get_property_stats) -- unchanged by this rewrite. Everything new here
// (sorting, selection, export, drill-down filters) operates client-side on
// the same `items`/`statsData` these two hooks already return; no new
// backend route is needed for any of it.
export const Route = createFileRoute("/properties/$propertyId/history")({
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

type SortField = "date" | "category" | "cost" | "status";
type SortDir = "asc" | "desc";
interface SortState {
  field: SortField;
  dir: SortDir;
}

interface TableUrlState {
  sort: SortState;
  trade: Trade | null;
  year: number | null;
}

function readTableStateFromUrl(): TableUrlState {
  const fallback: TableUrlState = { sort: { field: "date", dir: "desc" }, trade: null, year: null };
  if (typeof window === "undefined") return fallback;
  const params = new URLSearchParams(window.location.search);
  const field = params.get("sort");
  const dir = params.get("dir");
  const trade = params.get("trade");
  const yearRaw = params.get("year");
  const year = yearRaw ? Number.parseInt(yearRaw, 10) : null;
  return {
    sort: {
      field: field === "category" || field === "cost" || field === "status" ? field : "date",
      dir: dir === "asc" ? "asc" : "desc",
    },
    trade: (trade as Trade | null) ?? null,
    year: year && Number.isFinite(year) ? year : null,
  };
}

function writeTableStateToUrl(state: TableUrlState) {
  if (typeof window === "undefined") return;
  // Preserves address/postcode (the fallback the header reads -- see
  // PropertyTabs) and everything else already in the query string; only
  // sort/trade/year are ever added, changed or removed here.
  const params = new URLSearchParams(window.location.search);
  params.set("sort", state.sort.field);
  params.set("dir", state.sort.dir);
  if (state.trade) params.set("trade", state.trade);
  else params.delete("trade");
  if (state.year) params.set("year", String(state.year));
  else params.delete("year");
  const qs = params.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${qs ? `?${qs}` : ""}`);
}

const STATUS_RANK: Record<CaseStatus, number> = Object.fromEntries(
  CASE_STATUSES.map((s, i) => [s, i]),
) as Record<CaseStatus, number>;

function csvEscape(value: string): string {
  if (/[",\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
}

function HistoryPage() {
  const { propertyId } = Route.useParams();
  const searchParams =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const address = searchParams?.get("address") ?? undefined;
  const postcode = searchParams?.get("postcode") ?? undefined;

  const history = usePropertyHistory(propertyId);
  const items = history.data?.items ?? [];
  const propertyStats = usePropertyStats(propertyId);
  const statsData = propertyStats.data;

  const [tableState, setTableState] = useState<TableUrlState>(() => readTableStateFromUrl());
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    writeTableStateToUrl(tableState);
  }, [tableState]);

  const filtered = useMemo(() => {
    return items.filter((h) => {
      if (tableState.trade && h.trade !== tableState.trade) return false;
      if (tableState.year && new Date(h.created_at).getFullYear() !== tableState.year) return false;
      return true;
    });
  }, [items, tableState.trade, tableState.year]);

  const sorted = useMemo(() => {
    const dirMul = tableState.sort.dir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      switch (tableState.sort.field) {
        case "date":
          return dirMul * a.created_at.localeCompare(b.created_at);
        case "category":
          return dirMul * (a.trade ?? "").localeCompare(b.trade ?? "");
        case "cost":
          return dirMul * ((a.quoted_pence ?? -1) - (b.quoted_pence ?? -1));
        case "status":
          return dirMul * (STATUS_RANK[a.status] - STATUS_RANK[b.status]);
        default:
          return 0;
      }
    });
  }, [filtered, tableState.sort]);

  // Selection tracks case ids; ids that fall out of the current filter stay
  // selected in state but simply aren't shown/counted here -- switching a
  // filter off restores them rather than silently discarding a choice.
  const visibleSelected = sorted.filter((h) => selected.has(h.case_id));
  const allVisibleSelected = sorted.length > 0 && visibleSelected.length === sorted.length;

  function toggleSort(field: SortField) {
    setTableState((s) =>
      s.sort.field === field
        ? { ...s, sort: { field, dir: s.sort.dir === "asc" ? "desc" : "asc" } }
        : { ...s, sort: { field, dir: "asc" } },
    );
  }

  function toggleTradeFilter(trade: Trade) {
    setTableState((s) => ({ ...s, trade: s.trade === trade ? null : trade }));
  }

  function toggleYearFilter(year: number) {
    setTableState((s) => ({ ...s, year: s.year === year ? null : year }));
  }

  function clearFilters() {
    setTableState((s) => ({ ...s, trade: null, year: null }));
  }

  function toggleRow(caseId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(caseId)) next.delete(caseId);
      else next.add(caseId);
      return next;
    });
  }

  function toggleSelectAllVisible() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        for (const h of sorted) next.delete(h.case_id);
      } else {
        for (const h of sorted) next.add(h.case_id);
      }
      return next;
    });
  }

  function exportSelectedCsv() {
    const rows = sorted.filter((h) => selected.has(h.case_id));
    if (rows.length === 0 || typeof window === "undefined") return;
    const header = ["Date", "Issue", "Trade", "Status", "Outcome", "Contractor", "Quoted"];
    const lines = [header.join(",")];
    for (const h of rows) {
      lines.push(
        [
          formatDate(h.created_at),
          h.title,
          h.trade ? titleCase(h.trade) : "",
          h.status,
          h.outcome ?? "",
          h.contractor_name ?? "",
          formatPence(h.quoted_pence) ?? "",
        ]
          .map(csvEscape)
          .join(","),
      );
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `property-${propertyId}-history-export.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const filteredQuotedTotal = filtered.reduce((sum, h) => sum + (h.quoted_pence ?? 0), 0);
  const hasActiveFilter = tableState.trade !== null || tableState.year !== null;

  const stats = [
    {
      value: propertyStats.isLoading
        ? "…"
        : propertyStats.isError
          ? "—"
          : String(statsData?.active_count ?? 0),
      label: "Active tickets",
    },
    {
      value: propertyStats.isLoading
        ? "…"
        : propertyStats.isError
          ? "—"
          : String(statsData?.total_count ?? 0),
      label: "Total tickets",
    },
    {
      value: propertyStats.isLoading
        ? "…"
        : propertyStats.isError
          ? "—"
          : String(statsData?.recurring_issues.length ?? 0),
      label: "Repeat issues",
    },
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
      <PropertyTabs
        propertyId={propertyId}
        active="history"
        fallbackAddress={address}
        fallbackPostcode={postcode}
      >
        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {stats.map((s) => (
            <Card key={s.label} className="px-4 py-3">
              <div className="text-lg font-bold tracking-tight">{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </Card>
          ))}
        </section>

        <section className="mt-3 grid gap-3 xl:grid-cols-3">
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
              <div className="flex flex-col gap-2">
                <QuotedByTradeDonut data={statsData?.quoted_by_trade ?? []} />
                {(statsData?.quoted_by_trade.length ?? 0) > 0 && (
                  <TradeChipRow
                    trades={statsData!.quoted_by_trade.map((d) => d.trade)}
                    active={tableState.trade}
                    onToggle={toggleTradeFilter}
                  />
                )}
              </div>
              <div className="flex flex-col gap-2">
                <QuotedByYearBars data={statsData?.quoted_by_year ?? []} />
                {(statsData?.quoted_by_year.length ?? 0) > 0 && (
                  <YearChipRow
                    years={statsData!.quoted_by_year.map((d) => d.year)}
                    active={tableState.year}
                    onToggle={toggleYearFilter}
                  />
                )}
              </div>
              <div className="flex flex-col gap-2">
                <RecurringIssuesList data={statsData?.recurring_issues ?? []} />
                {(statsData?.recurring_issues.length ?? 0) > 0 && (
                  <TradeChipRow
                    trades={statsData!.recurring_issues.map((d) => d.trade)}
                    active={tableState.trade}
                    onToggle={toggleTradeFilter}
                  />
                )}
              </div>
            </>
          )}
        </section>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="text-muted-foreground">
            Showing <b className="text-foreground">{sorted.length}</b> of {items.length} case
            {items.length === 1 ? "" : "s"}
            {" · "}
            <b className="text-foreground">{formatPence(filteredQuotedTotal) ?? "£0.00"}</b> quoted
            on these
            {hasActiveFilter && (
              <button
                type="button"
                onClick={clearFilters}
                className="ml-2 inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11px] font-medium hover:bg-accent"
              >
                <X className="h-3 w-3" /> Clear filter
              </button>
            )}
          </div>
          {visibleSelected.length > 0 && (
            <button
              type="button"
              onClick={exportSelectedCsv}
              className="flex h-8 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-medium shadow-card hover:bg-accent"
            >
              <Download className="h-3.5 w-3.5" /> Export selected ({visibleSelected.length})
            </button>
          )}
        </div>

        <Card className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[950px] text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="w-10 px-4 py-2.5">
                  <input
                    aria-label="Select all visible history rows"
                    type="checkbox"
                    className="accent-primary"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    disabled={sorted.length === 0}
                  />
                </th>
                <SortableTh field="date" label="Date" state={tableState.sort} onSort={toggleSort} />
                <th className="px-4 py-2.5 font-medium">Issue</th>
                <SortableTh
                  field="category"
                  label="Trade"
                  state={tableState.sort}
                  onSort={toggleSort}
                />
                <SortableTh
                  field="status"
                  label="Status"
                  state={tableState.sort}
                  onSort={toggleSort}
                />
                <th className="px-4 py-2.5 font-medium">Outcome</th>
                <th className="px-4 py-2.5 font-medium">Contractor</th>
                <SortableTh
                  field="cost"
                  label="Quoted"
                  state={tableState.sort}
                  onSort={toggleSort}
                />
                <th className="w-12 px-4 py-2.5 text-center font-medium">View</th>
              </tr>
            </thead>
            <tbody>
              {history.isLoading && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-xs text-muted-foreground">
                    Loading history…
                  </td>
                </tr>
              )}
              {history.isError && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-xs text-destructive">
                    Could not load property history.
                  </td>
                </tr>
              )}
              {!history.isLoading && !history.isError && items.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-xs text-muted-foreground">
                    No recorded cases for this property yet.
                  </td>
                </tr>
              )}
              {!history.isLoading &&
                !history.isError &&
                items.length > 0 &&
                sorted.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-xs text-muted-foreground">
                      No cases match the current filter.
                    </td>
                  </tr>
                )}
              {sorted.map((h) => (
                <HistoryRow
                  key={h.case_id}
                  item={h}
                  selected={selected.has(h.case_id)}
                  onToggle={() => toggleRow(h.case_id)}
                />
              ))}
            </tbody>
          </table>
        </Card>
      </PropertyTabs>
    </AppShell>
  );
}

function SortableTh({
  field,
  label,
  state,
  onSort,
}: {
  field: SortField;
  label: string;
  state: SortState;
  onSort: (field: SortField) => void;
}) {
  const active = state.field === field;
  return (
    <th className="px-4 py-2.5 font-medium">
      <button
        type="button"
        onClick={() => onSort(field)}
        className={cn("flex items-center gap-1 hover:text-foreground", active && "text-foreground")}
      >
        {label}
        {active ? (
          state.dir === "asc" ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-40" />
        )}
      </button>
    </th>
  );
}

function HistoryRow({
  item: h,
  selected,
  onToggle,
}: {
  item: PropertyHistoryItem;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <tr className="border-b border-border last:border-0 transition-colors hover:bg-muted/60">
      <td className="px-4 py-3">
        <input
          aria-label={`Select ${h.title}, ${formatDate(h.created_at)}`}
          type="checkbox"
          className="accent-primary"
          checked={selected}
          onChange={onToggle}
        />
      </td>
      <td className="px-4 py-3 text-muted-foreground">{formatDate(h.created_at)}</td>
      <td className="max-w-sm truncate px-4 py-3 font-medium" title={h.title}>
        {h.title}
      </td>
      <td className="px-4 py-3 text-muted-foreground">{h.trade ? titleCase(h.trade) : "—"}</td>
      <td className="px-4 py-3">
        <Pill tone={statusTone(h.status)}>{h.status}</Pill>
      </td>
      <td className="px-4 py-3 text-muted-foreground">{h.outcome ?? "—"}</td>
      <td className="px-4 py-3 text-muted-foreground">{h.contractor_name ?? "—"}</td>
      <td className="px-4 py-3 font-medium">{formatPence(h.quoted_pence) ?? "—"}</td>
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
  );
}

// Same trade -> tone mapping PropertyStatsCharts.tsx uses internally (not
// exported from there, so re-declared here) -- keeps these chip rows
// colour-matched to the donut segments/recurring-issue badges they sit
// under. PropertyStatsCharts.tsx is reused unmodified per the task brief, so
// this drill-down control lives directly beneath each chart card rather
// than inside it.
const TRADE_TONE: Record<Trade, "blue" | "purple" | "amber" | "orange" | "gray"> = {
  ROOFING: "blue",
  PLUMBING: "purple",
  ELECTRICAL: "amber",
  SCAFFOLDING: "orange",
  OTHER: "gray",
};

/** Clickable legend chips mirroring a chart's trade segments -- clicking one
 * filters the table below to that trade; clicking the active one clears it.
 * De-duplicates trades (recurring-issues and quoted-by-trade both list one
 * chip per trade). */
function TradeChipRow({
  trades,
  active,
  onToggle,
}: {
  trades: Trade[];
  active: Trade | null;
  onToggle: (trade: Trade) => void;
}) {
  const unique = Array.from(new Set(trades));
  return (
    <div className="flex flex-wrap gap-1.5 px-1">
      {unique.map((trade) => (
        <button
          key={trade}
          type="button"
          onClick={() => onToggle(trade)}
          aria-pressed={active === trade}
          className={cn(
            "rounded-md transition-opacity",
            active !== null && active !== trade && "opacity-40",
          )}
        >
          <Pill tone={TRADE_TONE[trade]}>{titleCase(trade)}</Pill>
        </button>
      ))}
    </div>
  );
}

function YearChipRow({
  years,
  active,
  onToggle,
}: {
  years: number[];
  active: number | null;
  onToggle: (year: number) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5 px-1">
      {years.map((year) => (
        <button
          key={year}
          type="button"
          onClick={() => onToggle(year)}
          aria-pressed={active === year}
          className={cn(
            "rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors",
            active === year
              ? "border-primary bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:bg-accent",
          )}
        >
          {year}
        </button>
      ))}
    </div>
  );
}
