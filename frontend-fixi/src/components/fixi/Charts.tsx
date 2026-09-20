// Charts for the Insights page ("/insights"). Same visual language as
// PropertyStatsCharts.tsx -- a conic-gradient donut and CSS bar charts, no
// charting library -- extended so every mark is a real, keyboard-reachable
// <button> that drills into the matching case rows (see
// routes/insights.index.tsx, which owns the drill-down selection state and
// the /insights/cases fetch behind the resulting inline panel).
//
// Each chart also carries a screen-reader-only list of its own data points
// (the "text alternative" the task calls for) in addition to the visible
// labels/callouts already on the chart -- see the `sr-only` <ul> in each
// component.

import { format, parse } from "date-fns";
import { Wrench } from "lucide-react";
import { Card } from "@/components/fixi/AppShell";
import type {
  CaseVolumeMonth,
  CategoryBreakdownItem,
  RecurringIssueRow,
  ResolutionBucket,
  SpendByYearItem,
} from "@/hooks/use-analytics";
import type { Trade } from "@/api/types";
import type { StatusTone } from "@/lib/fixi-data";
import { formatDate, formatPence, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// Duplicated from PropertyStatsCharts.tsx rather than imported -- that file
// doesn't export these maps, and this component owns a second, independent
// donut (category breakdown by case count, not quoted-by-trade). Same
// values, same rationale: one tone per trade so a trade reads the same
// colour everywhere in the app.
const TRADE_TONE: Record<Trade, StatusTone> = {
  ROOFING: "blue",
  PLUMBING: "purple",
  ELECTRICAL: "amber",
  SCAFFOLDING: "orange",
  OTHER: "gray",
};

const TRADE_DOT_CLASS: Record<StatusTone, string> = {
  red: "bg-status-red-foreground",
  orange: "bg-status-orange-foreground",
  green: "bg-status-green-foreground",
  blue: "bg-status-blue-foreground",
  amber: "bg-status-amber-foreground",
  purple: "bg-status-purple-foreground",
  gray: "bg-status-gray-foreground",
};

const TRADE_BADGE_CLASS: Record<StatusTone, string> = {
  red: "bg-status-red text-status-red-foreground",
  orange: "bg-status-orange text-status-orange-foreground",
  green: "bg-status-green text-status-green-foreground",
  blue: "bg-status-blue text-status-blue-foreground",
  amber: "bg-status-amber text-status-amber-foreground",
  purple: "bg-status-purple text-status-purple-foreground",
  gray: "bg-status-gray text-status-gray-foreground",
};

const TRADE_CSS_VAR: Record<StatusTone, string> = {
  red: "var(--status-red-foreground)",
  orange: "var(--status-orange-foreground)",
  green: "var(--status-green-foreground)",
  blue: "var(--status-blue-foreground)",
  amber: "var(--status-amber-foreground)",
  purple: "var(--status-purple-foreground)",
  gray: "var(--status-gray-foreground)",
};

/** Same largest-remainder rounding as PropertyStatsCharts.tsx's donut, so a
 * displayed percentage column always sums to exactly 100 rather than
 * 99/101 from independently-rounded shares. */
function largestRemainderPercentages(values: number[]): number[] {
  const floors = values.map((v) => Math.floor(v));
  let leftover = Math.round(values.reduce((a, b) => a + b, 0)) - floors.reduce((a, b) => a + b, 0);
  const order = values
    .map((v, index) => ({ index, remainder: v - Math.floor(v) }))
    .sort((a, b) => b.remainder - a.remainder);
  const result = [...floors];
  for (const { index } of order) {
    if (leftover <= 0) break;
    result[index] = (result[index] ?? 0) + 1;
    leftover -= 1;
  }
  return result;
}

function formatMonthLabel(month: string): string {
  const parsed = parse(month, "yyyy-MM", new Date());
  if (Number.isNaN(parsed.getTime())) return month;
  return format(parsed, "MMM yyyy");
}

/** Short axis label: just "Jan", or "Jan '26" for the first bar of each
 * year -- a full "MMM yyyy" under every one of up to 24 narrow bars
 * overflows its column, so the year is only spelled out where it changes
 * (the full month + year is always in the button's title/aria-label and
 * the sr-only list above). */
function formatMonthAxisLabel(month: string, showYear: boolean): string {
  const parsed = parse(month, "yyyy-MM", new Date());
  if (Number.isNaN(parsed.getTime())) return month;
  return showYear ? format(parsed, "MMM ''yy") : format(parsed, "MMM");
}

function CardHead({ title, description }: { title: string; description?: string }) {
  return (
    <div>
      <h2 className="text-xs font-semibold">{title}</h2>
      {description ? (
        <p className="mt-0.5 text-[10.5px] text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

// --- Case volume by month --------------------------------------------------

export function CaseVolumeChart({
  data,
  selectedMonth,
  onSelectMonth,
}: {
  data: CaseVolumeMonth[];
  selectedMonth: string | null;
  onSelectMonth: (month: string) => void;
}) {
  const max = Math.max(1, ...data.map((d) => d.count));

  return (
    <Card className="p-4">
      <CardHead title="Case volume by month" description="Click a month to see its cases." />
      {data.length === 0 ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">
          No cases in the selected range.
        </p>
      ) : (
        <>
          <ul className="sr-only">
            {data.map((d) => (
              <li key={d.month}>
                {formatMonthLabel(d.month)}: {d.count} case{d.count === 1 ? "" : "s"}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex h-32 items-end gap-1.5 overflow-x-auto border-b border-border px-1 pb-1">
            {data.map((d, index) => {
              const active = selectedMonth === d.month;
              const showYear =
                index === 0 || d.month.slice(0, 4) !== data[index - 1]?.month.slice(0, 4);
              return (
                <button
                  key={d.month}
                  type="button"
                  onClick={() => onSelectMonth(d.month)}
                  aria-pressed={active}
                  aria-label={`${formatMonthLabel(d.month)}: ${d.count} case${d.count === 1 ? "" : "s"}. View cases.`}
                  title={`${formatMonthLabel(d.month)}: ${d.count}`}
                  className="flex min-w-[22px] flex-1 flex-col items-center gap-1 rounded-t-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span
                    className={cn(
                      "w-full max-w-6 rounded-t-sm transition-colors",
                      active ? "bg-primary" : "bg-primary/35 hover:bg-primary/55",
                    )}
                    style={{ height: `${Math.max(4, Math.round((d.count / max) * 96))}px` }}
                  />
                  <span
                    className={cn(
                      "text-[8px] whitespace-nowrap",
                      active ? "font-semibold text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {formatMonthAxisLabel(d.month, showYear)}
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </Card>
  );
}

// --- Category breakdown donut -----------------------------------------------

export function CategoryBreakdownDonut({
  data,
  selectedTrade,
  onSelectTrade,
}: {
  data: CategoryBreakdownItem[];
  selectedTrade: Trade | null;
  onSelectTrade: (trade: Trade) => void;
}) {
  let cursor = 0;
  const stops = data.map((d) => {
    const color = TRADE_CSS_VAR[TRADE_TONE[d.trade] ?? "gray"];
    const from = cursor;
    const to = cursor + d.percentage;
    cursor = to;
    return `${color} ${from}% ${to}%`;
  });
  const displayPercentages = largestRemainderPercentages(data.map((d) => d.percentage));
  const totalCount = data.reduce((sum, d) => sum + d.count, 0);

  return (
    <Card className="p-4">
      <CardHead title="Category breakdown" description="Click a trade to see its cases." />
      {data.length === 0 ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">
          No categorised cases in the selected range.
        </p>
      ) : (
        <div className="mt-3 flex items-center gap-5">
          <div
            className="relative h-24 w-24 shrink-0 rounded-full"
            style={{ background: `conic-gradient(${stops.join(", ")})` }}
            aria-hidden="true"
          >
            <div className="absolute inset-4 flex flex-col items-center justify-center rounded-full bg-card text-center">
              <b className="text-sm font-bold leading-tight">{totalCount}</b>
              <span className="text-[9px] text-muted-foreground">Cases</span>
            </div>
          </div>
          {/* The legend rows ARE the interactive/accessible surface -- a
           * clickable conic-gradient wedge can't carry a keyboard-reachable
           * accessible name, these buttons can. */}
          <ul className="flex-1 space-y-1 text-[11px]">
            {data.map((d, index) => {
              const active = selectedTrade === d.trade;
              return (
                <li key={d.trade}>
                  <button
                    type="button"
                    onClick={() => onSelectTrade(d.trade)}
                    aria-pressed={active}
                    // The visible row is three separate spans (dot, name,
                    // percentage, count); an explicit label reads as one
                    // sentence rather than four fragments.
                    aria-label={`${titleCase(d.trade)}: ${d.count} case${
                      d.count === 1 ? "" : "s"
                    }, ${displayPercentages[index]}% of the total. View cases.`}
                    className={cn(
                      "flex w-full items-center rounded-md px-1.5 py-1 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                      active ? "bg-accent" : "hover:bg-accent/60",
                    )}
                  >
                    <span
                      className={cn(
                        "mr-2 h-2 w-2 shrink-0 rounded-full",
                        TRADE_DOT_CLASS[TRADE_TONE[d.trade]],
                      )}
                    />
                    <span className={active ? "font-semibold" : undefined}>
                      {titleCase(d.trade)}
                    </span>
                    <b className="ml-auto shrink-0">{displayPercentages[index]}%</b>
                    <span className="ml-2 shrink-0 text-muted-foreground">({d.count})</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}

// --- Spend by year (quoted vs actual, two distinct series) -----------------

export function SpendByYearChart({
  data,
  selectedYear,
  onSelectYear,
}: {
  data: SpendByYearItem[];
  selectedYear: number | null;
  onSelectYear: (year: number) => void;
}) {
  const max = Math.max(1, ...data.flatMap((d) => [d.quoted_pence, d.actual_pence]));

  return (
    <Card className="p-4">
      <CardHead
        title="Spend by year"
        description="Quoted vs. actual. Click a year to see its cases."
      />
      {data.length === 0 ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">
          No quoted or actual spend in the selected range.
        </p>
      ) : (
        <>
          <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-primary/70" /> Quoted
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-chart-4" /> Actual
            </span>
          </div>
          <ul className="sr-only">
            {data.map((d) => (
              <li key={d.year}>
                {d.year}: quoted {formatPence(d.quoted_pence)}, actual {formatPence(d.actual_pence)}
              </li>
            ))}
          </ul>
          <div className="mt-2 flex h-24 items-end gap-3 overflow-x-auto border-b border-border px-1 pb-1">
            {data.map((d) => {
              const active = selectedYear === d.year;
              return (
                <button
                  key={d.year}
                  type="button"
                  onClick={() => onSelectYear(d.year)}
                  aria-pressed={active}
                  aria-label={`${d.year}: quoted ${formatPence(d.quoted_pence) ?? "not recorded"}, actual ${formatPence(d.actual_pence) ?? "not recorded"}. View cases.`}
                  className={cn(
                    "flex min-w-[64px] flex-1 flex-col items-center gap-1 rounded-t-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active && "bg-accent/60",
                  )}
                >
                  <div className="flex h-16 items-end gap-1">
                    <span
                      className="w-3.5 rounded-t-sm bg-primary/70"
                      style={{
                        height: `${Math.max(3, Math.round((d.quoted_pence / max) * 64))}px`,
                      }}
                    />
                    <span
                      className="w-3.5 rounded-t-sm bg-chart-4"
                      style={{
                        height: `${Math.max(3, Math.round((d.actual_pence / max) * 64))}px`,
                      }}
                    />
                  </div>
                  <span
                    className={cn(
                      "text-[9px]",
                      active ? "font-semibold text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {d.year}
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </Card>
  );
}

// --- Resolution time distribution -------------------------------------------

export function ResolutionTimeChart({
  data,
  averageHours,
  medianHours,
  selectedBucket,
  onSelectBucket,
}: {
  data: ResolutionBucket[];
  averageHours: number | null | undefined;
  medianHours: number | null | undefined;
  selectedBucket: string | null;
  onSelectBucket: (bucket: ResolutionBucket) => void;
}) {
  const max = Math.max(1, ...data.map((d) => d.count));

  return (
    <Card className="p-4">
      <CardHead title="Resolution time" description="Click a bucket to see its cases." />
      <div className="mt-2 flex gap-4">
        <div>
          <div className="text-lg font-bold tracking-tight">
            {averageHours != null ? `${averageHours.toFixed(1)}h` : "—"}
          </div>
          <div className="text-[10px] text-muted-foreground">Average</div>
        </div>
        <div>
          <div className="text-lg font-bold tracking-tight">
            {medianHours != null ? `${medianHours.toFixed(1)}h` : "—"}
          </div>
          <div className="text-[10px] text-muted-foreground">Median</div>
        </div>
      </div>
      {data.length === 0 ? (
        <p className="mt-4 py-6 text-center text-xs text-muted-foreground">
          No resolved cases in the selected range.
        </p>
      ) : (
        <>
          <ul className="sr-only">
            {data.map((d) => (
              <li key={d.bucket}>
                {d.bucket}: {d.count} case{d.count === 1 ? "" : "s"}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex h-20 items-end gap-2 overflow-x-auto border-b border-border px-1 pb-1">
            {data.map((d) => {
              const active = selectedBucket === d.bucket;
              return (
                <button
                  key={d.bucket}
                  type="button"
                  onClick={() => onSelectBucket(d)}
                  aria-pressed={active}
                  aria-label={`${d.bucket}: ${d.count} case${d.count === 1 ? "" : "s"}. View cases.`}
                  title={`${d.bucket}: ${d.count}`}
                  className="flex min-w-[40px] flex-1 flex-col items-center gap-1 rounded-t-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span
                    className={cn(
                      "w-full max-w-8 rounded-t-sm transition-colors",
                      active ? "bg-primary" : "bg-primary/35 hover:bg-primary/55",
                    )}
                    style={{ height: `${Math.max(4, Math.round((d.count / max) * 56))}px` }}
                  />
                  <span
                    className={cn(
                      "text-center text-[8px] leading-tight whitespace-nowrap",
                      active ? "font-semibold text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {d.bucket}
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </Card>
  );
}

// --- Recurring issues --------------------------------------------------------

export function recurringIssueKey(issue: RecurringIssueRow): string {
  return `${issue.property_id}:${issue.trade}`;
}

export function RecurringIssuesTable({
  data,
  selectedKey,
  onSelectIssue,
}: {
  data: RecurringIssueRow[];
  selectedKey: string | null;
  onSelectIssue: (issue: RecurringIssueRow) => void;
}) {
  return (
    <Card className="p-4">
      <CardHead
        title="Recurring issues"
        description="Same trade, same property, more than once. Click a row to see its cases."
      />
      {data.length === 0 ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">
          No recurring issues in the selected range.
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-border">
          {data.map((issue) => {
            const key = recurringIssueKey(issue);
            const active = selectedKey === key;
            return (
              <li key={key}>
                <button
                  type="button"
                  onClick={() => onSelectIssue(issue)}
                  aria-pressed={active}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-md py-2 pl-1 pr-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                    active ? "bg-accent" : "hover:bg-accent/60",
                  )}
                >
                  <span
                    className={cn(
                      "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                      TRADE_BADGE_CLASS[TRADE_TONE[issue.trade]],
                    )}
                  >
                    <Wrench className="h-4 w-4" />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-xs font-semibold">
                      {titleCase(issue.trade)} — {issue.property_address}
                    </div>
                    <div className="text-[10px] text-muted-foreground">
                      {issue.count} occurrence{issue.count === 1 ? "" : "s"}
                    </div>
                  </div>
                  <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                    Last: {formatDate(issue.last_occurred_at)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
