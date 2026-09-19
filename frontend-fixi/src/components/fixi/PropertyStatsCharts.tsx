import { Wrench } from "lucide-react";
import { Card } from "@/components/fixi/AppShell";
import type { RecurringIssue, Trade, TradeQuoteBreakdown, YearlyQuoteTotal } from "@/api/types";
import type { StatusTone } from "@/lib/fixi-data";
import { formatDate, formatPence, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// Adapted from Liza's liza.UI2 prototype (properties/14-king-street/history
// -- IssueBreakdown/AnnualSpend/RecurringIssues): same conic-gradient donut
// and CSS bar-chart approach, but driven entirely by the real
// GET /properties/{id}/stats response instead of her four hardcoded
// percentages/six hardcoded bar heights for one specific property.

// One tone per trade so the same trade always reads as the same colour
// across the donut segment, its legend dot and the recurring-issues badge.
// Reuses the app's existing StatusTone palette (fixi-data.ts) rather than
// inventing new colours -- Badge.tsx/WorkGraph.tsx already reuse that same
// 7-tone set for unrelated axes (case status, work order status).
const TRADE_TONE: Record<Trade, StatusTone> = {
  ROOFING: "blue",
  PLUMBING: "purple",
  ELECTRICAL: "amber",
  SCAFFOLDING: "orange",
  OTHER: "gray",
};

// Literal strings (not built from a template) so Tailwind's source scanner
// can see and generate every variant at build time -- mirrors
// Badge.tsx's toneClasses / WorkGraph.tsx's nodeBorderClasses.
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

// CSS custom-property equivalents of the classes above, for the
// conic-gradient (which needs an actual colour value, not a Tailwind
// class) -- same var names, same values, just consumed as inline style.
const TRADE_CSS_VAR: Record<StatusTone, string> = {
  red: "var(--status-red-foreground)",
  orange: "var(--status-orange-foreground)",
  green: "var(--status-green-foreground)",
  blue: "var(--status-blue-foreground)",
  amber: "var(--status-amber-foreground)",
  purple: "var(--status-purple-foreground)",
  gray: "var(--status-gray-foreground)",
};

function CardHead({ title }: { title: string }) {
  return <h2 className="text-xs font-semibold">{title}</h2>;
}

/** Donut breakdown of quoted work by trade. Every segment's angle comes
 * from that trade's real `percentage` -- no fixed stops. Empty
 * (`quoted_by_trade: []`, a property with no quoted work yet) renders an
 * honest text state rather than a blank/NaN circle. */
export function QuotedByTradeDonut({ data }: { data: TradeQuoteBreakdown[] }) {
  const total = data.reduce((sum, d) => sum + d.quoted_pence, 0);

  let cursor = 0;
  const stops = data.map((d) => {
    const color = TRADE_CSS_VAR[TRADE_TONE[d.trade] ?? "gray"];
    const from = cursor;
    const to = cursor + d.percentage;
    cursor = to;
    return `${color} ${from}% ${to}%`;
  });

  // Rounding each share independently can print a legend that doesn't add
  // up (51.5 + 48.5 -> "52% + 49%" = 101%). Largest-remainder instead: keep
  // every floor, then hand the leftover whole points to whichever shares
  // were rounded down hardest, so the column always totals exactly 100%.
  const displayPercentages = (() => {
    const floors = data.map((d) => Math.floor(d.percentage));
    let leftover =
      Math.round(data.reduce((sum, d) => sum + d.percentage, 0)) -
      floors.reduce((a, b) => a + b, 0);
    const order = data
      .map((d, index) => ({ index, remainder: d.percentage - Math.floor(d.percentage) }))
      .sort((a, b) => b.remainder - a.remainder);
    const result = [...floors];
    for (const { index } of order) {
      if (leftover <= 0) break;
      result[index] = (result[index] ?? 0) + 1;
      leftover -= 1;
    }
    return result;
  })();

  return (
    <Card className="p-4">
      <CardHead title="Quoted by trade" />
      {data.length === 0 ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">No quoted work yet.</p>
      ) : (
        <div className="mt-3 flex items-center gap-5">
          <div
            className="relative h-24 w-24 shrink-0 rounded-full"
            style={{ background: `conic-gradient(${stops.join(", ")})` }}
          >
            <div className="absolute inset-4 flex flex-col items-center justify-center rounded-full bg-card text-center">
              <b className="text-sm font-bold leading-tight">{formatPence(total)}</b>
              <span className="text-[9px] text-muted-foreground">Total quoted</span>
            </div>
          </div>
          <ul className="flex-1 space-y-1.5 text-[11px]">
            {data.map((d, index) => (
              <li key={d.trade} className="flex items-center">
                <span
                  className={cn(
                    "mr-2 h-2 w-2 shrink-0 rounded-full",
                    TRADE_DOT_CLASS[TRADE_TONE[d.trade]],
                  )}
                />
                <span>{titleCase(d.trade)}</span>
                <b className="ml-auto shrink-0">{displayPercentages[index]}%</b>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

/** Simple CSS bar chart of quoted totals per year. Labelled "Quoted total"
 * (not "Spend"/"Cost") to match this app's Costs-tab convention -- these
 * are quoted amounts, not money actually paid. */
export function QuotedByYearBars({ data }: { data: YearlyQuoteTotal[] }) {
  const total = data.reduce((sum, d) => sum + d.quoted_pence, 0);
  const max = Math.max(1, ...data.map((d) => d.quoted_pence));

  return (
    <Card className="p-4">
      <CardHead title="Quoted by year" />
      {data.length === 0 ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">No quoted work yet.</p>
      ) : (
        <>
          <div className="mt-1 text-xl font-bold tracking-tight">{formatPence(total)}</div>
          <div className="text-[10px] text-muted-foreground">Quoted total</div>
          {/* Bars scale to a 46px max, not the container's full 64px --
           * leaves room for the year label below each bar (~13px with its
           * margin) so the tallest column still sits inside the h-16 box
           * instead of overflowing past its top edge into "Quoted total"
           * above. */}
          <div className="mt-3 flex h-16 items-end gap-3 border-b border-border px-1">
            {data.map((d) => (
              <div key={d.year} className="flex flex-1 flex-col items-center">
                <div
                  className="w-full max-w-7 rounded-t-sm bg-primary/35"
                  style={{ height: `${Math.max(4, Math.round((d.quoted_pence / max) * 46))}px` }}
                  title={formatPence(d.quoted_pence) ?? undefined}
                />
                <span className="mt-1 text-[8px] text-muted-foreground">{d.year}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

/** List of trades with more than one occurrence on this property. Most
 * properties won't have any -- an empty list is the correct, common state,
 * not a loading/error placeholder. */
export function RecurringIssuesList({ data }: { data: RecurringIssue[] }) {
  return (
    <Card className="p-4">
      <CardHead title="Recurring issues" />
      {data.length === 0 ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">
          No recurring issues on this property.
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-border">
          {data.map((issue) => (
            <li key={issue.trade} className="flex items-center gap-3 py-2">
              <span
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                  TRADE_BADGE_CLASS[TRADE_TONE[issue.trade]],
                )}
              >
                <Wrench className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <div className="text-xs font-semibold">{titleCase(issue.trade)}</div>
                <div className="text-[10px] text-muted-foreground">
                  {issue.occurrence_count}{" "}
                  {issue.occurrence_count === 1 ? "occurrence" : "occurrences"}
                </div>
              </div>
              <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                Last: {formatDate(issue.last_occurred_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
