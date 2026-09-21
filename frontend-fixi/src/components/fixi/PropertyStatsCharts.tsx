import { Wrench } from "lucide-react";
import type { CSSProperties } from "react";
import { Card } from "@/components/fixi/AppShell";
import type { RecurringIssue, Trade, TradeQuoteBreakdown, YearlyQuoteTotal } from "@/api/types";
import type { StatusTone } from "@/lib/fixi-data";
import { formatDate, formatPence, titleCase } from "@/lib/format";
import { largestRemainderPercentages } from "@/lib/percentages";
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

/* Bar geometry and the mount animation, duplicated from Charts.tsx for
 * the same reason the trade maps above are: that file doesn't export
 * them, and these two files own independent charts that happen to share
 * a visual language. The rules themselves are explained there in full --
 * in short, `--fill` carries the length, `@starting-style` gives the
 * element a zero length on its *first* render only, and the transition
 * covers both that and any later change in the value. The 5s poll behind
 * these props re-renders the component without replaying anything,
 * because the element is not new; nothing keys off `isFetching`. */
const GROW_WIDTH =
  "w-[var(--fill)] transition-[width] duration-slow ease-fixi-out motion-safe:starting:w-0";
const GROW_HEIGHT =
  "h-[var(--fill)] transition-[height] duration-slow ease-fixi-out motion-safe:starting:h-0";

function fillVar(length: string): CSSProperties {
  return { "--fill": length } as CSSProperties;
}

/** Below this many years the bars are drawn horizontally: three columns
 * in a ~440px plot are hairlines surrounded by dead space, and the width
 * is the one dimension these cards have to spare. */
const HORIZONTAL_AT_OR_BELOW = 3;

/** A bar's length as a share of the largest value in the series; a real
 * but tiny value is floored so it stays visible, a true zero stays at
 * zero. Same rule as Charts.tsx. */
function barPercent(value: number, max: number): number {
  if (value <= 0 || max <= 0) return 0;
  return Math.max(1.5, (value / max) * 100);
}

/** The same rule in pixels, where `plot` is the usable column height
 * (the container less the axis label and its gap). */
function barPixels(value: number, max: number, plot: number): number {
  if (value <= 0 || max <= 0) return 0;
  return Math.max(3, Math.round((value / max) * plot));
}

function CardHead({ title }: { title: string }) {
  // text-section rather than the old text-xs -- see Charts.tsx's
  // CardHead; these are card titles, not captions.
  return <h2 className="text-section font-semibold">{title}</h2>;
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
  const displayPercentages = largestRemainderPercentages(data.map((d) => d.percentage));

  return (
    <Card className="p-4">
      <CardHead title="Quoted by trade" />
      {data.length === 0 ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">No quoted work yet.</p>
      ) : (
        <div className="mt-3 flex items-center gap-5">
          {/* 160px, up from 96px: the segment angles are what this mark
           * exists to compare, and they were being compared at favicon
           * size in a ~440px card. The hub total stays at text-section
           * rather than the text-metric used for a plain count in
           * Charts.tsx -- "£12,345.00" is three times as wide as "37"
           * and would not fit the ~112px well at 26px. */}
          <div
            className="relative h-40 w-40 shrink-0 rounded-full motion-safe:animate-in motion-safe:fade-in motion-safe:duration-slow"
            style={{ background: `conic-gradient(${stops.join(", ")})` }}
          >
            <div className="absolute inset-6 flex flex-col items-center justify-center rounded-full bg-card px-2 text-center">
              <b className="text-section font-bold leading-tight tabular-nums">
                {formatPence(total)}
              </b>
              <span className="text-micro text-muted-foreground">Total quoted</span>
            </div>
          </div>
          <ul className="flex-1 space-y-1.5 text-micro">
            {data.map((d, index) => (
              <li key={d.trade} className="flex items-center">
                <span
                  className={cn(
                    "mr-2 h-2 w-2 shrink-0 rounded-full",
                    TRADE_DOT_CLASS[TRADE_TONE[d.trade]],
                  )}
                />
                <span>{titleCase(d.trade)}</span>
                <b className="ml-auto shrink-0 tabular-nums">{displayPercentages[index]}%</b>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

/** Quoted totals per year. Labelled "Quoted total" (not "Spend"/"Cost")
 * to match this app's Costs-tab convention -- these are quoted amounts,
 * not money actually paid.
 *
 * Three shapes, by how many years there are to compare:
 *
 *  - One year is not a chart. The old code drew it as a bar whose height
 *    was `(quoted / max) * 46` -- with a single data point `quoted ===
 *    max`, so the bar was always exactly 46px tall no matter what the
 *    number was. It encoded nothing, and it printed a figure that was
 *    already the card's headline and already in the donut hub beside it:
 *    the same number three times in one row. It is now one sentence.
 *  - Two or three years go horizontal, where the width is.
 *  - Four or more earn columns.
 */
export function QuotedByYearBars({ data }: { data: YearlyQuoteTotal[] }) {
  const total = data.reduce((sum, d) => sum + d.quoted_pence, 0);
  const max = Math.max(1, ...data.map((d) => d.quoted_pence));
  const only = data.length === 1 ? data[0] : undefined;

  return (
    <Card className="p-4">
      <CardHead title="Quoted by year" />
      {data.length === 0 ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">No quoted work yet.</p>
      ) : only ? (
        <p className="mt-3 text-strong text-muted-foreground">
          <b className="text-section font-bold tracking-tight tabular-nums text-foreground">
            {formatPence(only.quoted_pence)}
          </b>{" "}
          quoted in {only.year}. There is nothing to compare it against yet.
        </p>
      ) : (
        <>
          {/* The sum across years, which is a different number from any
           * one bar -- unlike the single-year case above, where it was
           * the same number wearing a headline. */}
          <div className="mt-1 text-metric font-bold tracking-tight tabular-nums">
            {formatPence(total)}
          </div>
          <div className="text-micro text-muted-foreground">Quoted total</div>
          <ul className="sr-only">
            {data.map((d) => (
              <li key={d.year}>
                {d.year}: {formatPence(d.quoted_pence)} quoted
              </li>
            ))}
          </ul>
          {data.length <= HORIZONTAL_AT_OR_BELOW ? (
            <div className="mt-3 grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2">
              {data.map((d) => (
                <div
                  key={d.year}
                  className="col-span-2 grid grid-cols-subgrid items-center gap-x-3"
                >
                  <span className="text-micro tabular-nums text-muted-foreground">{d.year}</span>
                  <span className="flex items-center gap-2">
                    <span className="h-3 min-w-0 flex-1 overflow-hidden rounded-sm bg-muted">
                      <span
                        className={cn("block h-full rounded-sm bg-primary/45", GROW_WIDTH)}
                        style={fillVar(`${barPercent(d.quoted_pence, max)}%`)}
                      />
                    </span>
                    <span className="w-20 shrink-0 text-right text-micro tabular-nums text-muted-foreground">
                      {formatPence(d.quoted_pence)}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          ) : (
            /* Bars scale to 148px inside an h-44 box, leaving the ~20px
             * the year label and its gap need below them -- so the
             * tallest column lands on the top of the plot rather than
             * overflowing into "Quoted total" above it. 176px against a
             * ~524px plot is a 3:1 card; the old h-16 box was 8:1. */
            <div className="mt-3 flex h-44 items-end justify-start gap-3 border-b border-border px-1 pb-1">
              {data.map((d) => (
                <div
                  key={d.year}
                  className="flex min-w-[56px] max-w-[96px] flex-1 flex-col items-center gap-1"
                >
                  <div
                    className={cn("w-full max-w-12 rounded-t-sm bg-primary/35", GROW_HEIGHT)}
                    style={fillVar(`${barPixels(d.quoted_pence, max, 148)}px`)}
                    title={formatPence(d.quoted_pence) ?? undefined}
                  />
                  <span className="h-4 text-micro leading-4 tabular-nums text-muted-foreground">
                    {d.year}
                  </span>
                </div>
              ))}
            </div>
          )}
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
                <div className="text-strong font-semibold">{titleCase(issue.trade)}</div>
                <div className="text-micro text-muted-foreground">
                  {issue.occurrence_count}{" "}
                  {issue.occurrence_count === 1 ? "occurrence" : "occurrences"}
                </div>
              </div>
              <span className="ml-auto shrink-0 text-micro text-muted-foreground">
                Last: {formatDate(issue.last_occurred_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
