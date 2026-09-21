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
import type { CSSProperties, ReactNode } from "react";
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
import { largestRemainderPercentages } from "@/lib/percentages";
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

/* --- Bar geometry ---------------------------------------------------------
 *
 * Two or three vertical bars in a 440-690px plot are hairlines with a
 * field of empty space either side: the chart spends all of the width it
 * has on nothing, and all of its scarcity on the one axis (height) it is
 * short of. At or below this many series the same numbers are drawn as
 * horizontal bars, which use the width that actually exists and give
 * every label a full line to sit on. Above it, columns earn their keep.
 */
const HORIZONTAL_AT_OR_BELOW = 3;

/** A bar's length as a share of the largest value in its series. A real
 * but tiny value is floored at 1.5% so it stays visible; a true zero
 * stays at zero, because drawing a stub for "nothing happened" is the
 * same kind of lie as the full-height single bar this rewrite removed. */
function barPercent(value: number, max: number): number {
  if (value <= 0 || max <= 0) return 0;
  return Math.max(1.5, (value / max) * 100);
}

/** The same rule in pixels, for the vertical plots. `plot` is the usable
 * height of the column area -- the container height less the axis label
 * and its gap -- so the tallest bar lands on the top of the plot rather
 * than overflowing into the heading above it. */
function barPixels(value: number, max: number, plot: number): number {
  if (value <= 0 || max <= 0) return 0;
  return Math.max(3, Math.round((value / max) * plot));
}

/* Mount animation, in CSS, with no JavaScript and no timers.
 *
 * The bar's length lives in a `--fill` custom property and the length
 * utility reads it, so a re-render only ever changes that variable.
 * `@starting-style` supplies a zero length for the element's *first*
 * render and the transition carries it to the real value. Two
 * consequences, both wanted: the 5s background refetch that re-renders
 * these components does not replay the animation (the element is not
 * new), and a value that genuinely changed animates to its new length
 * instead of jumping. Nothing here keys off `isFetching`.
 *
 * `transition-[width,background-color]` rather than that plus a separate
 * `transition-colors`: both compile to the same `transition-property`
 * declaration, so tailwind-merge would keep whichever it saw last and
 * silently drop the other.
 */
const GROW_WIDTH =
  "w-[var(--fill)] transition-[width,background-color] duration-slow ease-fixi-out motion-safe:starting:w-0";
const GROW_HEIGHT =
  "h-[var(--fill)] transition-[height,background-color] duration-slow ease-fixi-out motion-safe:starting:h-0";

/** `--fill` is not a known CSSProperties key, so the cast is the standard
 * React idiom for handing a custom property to the style attribute. */
function fillVar(length: string): CSSProperties {
  return { "--fill": length } as CSSProperties;
}

function formatMonthLabel(month: string): string {
  const parsed = parse(month, "yyyy-MM", new Date());
  if (Number.isNaN(parsed.getTime())) return month;
  return format(parsed, "MMM yyyy");
}

/** Short axis label: just "Jan", or "Jan '26" for the first labelled bar
 * of each year -- a full "MMM yyyy" under every one of up to 24 narrow
 * bars overflows its column, so the year is only spelled out where it
 * changes (the full month + year is always in the button's
 * title/aria-label and the sr-only list above). */
function formatMonthAxisLabel(month: string, showYear: boolean): string {
  const parsed = parse(month, "yyyy-MM", new Date());
  if (Number.isNaN(parsed.getTime())) return month;
  return showYear ? format(parsed, "MMM ''yy") : format(parsed, "MMM");
}

/** How many columns share one axis label. The old chart solved crowding
 * by shrinking the label to 8px; 11px is now a hard floor, so crowding
 * is solved the way print does it instead -- label every second or third
 * column and let the rest be read from the tooltip, the button's
 * accessible name and the sr-only list, each of which still names every
 * single month. */
function axisLabelStride(count: number): number {
  if (count > 16) return 3;
  if (count > 10) return 2;
  return 1;
}

function CardHead({ title, description }: { title: string; description?: string }) {
  return (
    <div>
      {/* text-section, not the old text-xs: these cards are 440-690px
       * wide, and a 12px heading on a card that size reads as a caption
       * under the chart rather than the title of it. */}
      <h2 className="text-section font-semibold">{title}</h2>
      {description ? (
        <p className="mt-0.5 text-micro text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

// --- Horizontal bar primitives ----------------------------------------------

/** One row of a horizontal bar chart. The parent is a
 * `grid-cols-[auto_1fr]`; the row is a single button spanning both of its
 * columns via `grid-cols-subgrid`, so every label stays in one column and
 * every track starts at the same x -- without the label column having to
 * be guessed at some fixed width that the longest label then breaks. */
function HBarRow({
  label,
  active,
  ariaLabel,
  title,
  onClick,
  children,
}: {
  label: string;
  active: boolean;
  ariaLabel: string;
  title: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={ariaLabel}
      title={title}
      className={cn(
        "col-span-2 grid grid-cols-subgrid items-center gap-x-3 rounded-md px-1.5 py-1.5 text-left outline-none transition-colors duration-fast ease-fixi focus-visible:ring-2 focus-visible:ring-ring",
        active ? "bg-accent" : "hover:bg-accent/60",
      )}
    >
      <span
        className={cn(
          "text-micro whitespace-nowrap",
          active ? "font-semibold text-foreground" : "text-muted-foreground",
        )}
      >
        {label}
      </span>
      <span className="flex min-w-0 flex-col gap-1">{children}</span>
    </button>
  );
}

/** The track, fill and right-aligned value of one horizontal bar. The
 * track is drawn even where the fill is short, so a reader can see what
 * the bar is a fraction *of*; the value sits in a fixed-width column so
 * the numbers line up instead of forming a ragged edge. */
function HBarTrack({ percent, tone, value }: { percent: number; tone: string; value: string }) {
  return (
    <span className="flex items-center gap-2">
      <span className="h-3 min-w-0 flex-1 overflow-hidden rounded-sm bg-muted">
        <span
          className={cn("block h-full rounded-sm", tone, GROW_WIDTH)}
          style={fillVar(`${percent}%`)}
        />
      </span>
      <span className="w-20 shrink-0 text-right text-micro tabular-nums text-muted-foreground">
        {value}
      </span>
    </span>
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
  const horizontal = data.length > 0 && data.length <= HORIZONTAL_AT_OR_BELOW;
  const stride = axisLabelStride(data.length);

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
          {horizontal ? (
            <div className="mt-3 grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-1">
              {data.map((d) => {
                const active = selectedMonth === d.month;
                return (
                  <HBarRow
                    key={d.month}
                    label={formatMonthLabel(d.month)}
                    active={active}
                    ariaLabel={`${formatMonthLabel(d.month)}: ${d.count} case${d.count === 1 ? "" : "s"}. View cases.`}
                    title={`${formatMonthLabel(d.month)}: ${d.count}`}
                    onClick={() => onSelectMonth(d.month)}
                  >
                    <HBarTrack
                      percent={barPercent(d.count, max)}
                      tone={active ? "bg-primary" : "bg-primary/45"}
                      value={`${d.count} case${d.count === 1 ? "" : "s"}`}
                    />
                  </HBarRow>
                );
              })}
            </div>
          ) : (
            /* justify-start, and a max width on the column as well as on
             * the bar: `flex-1` on its own stretched four months across
             * the entire plot, which reads as "these months are adjacent
             * and evenly spaced" when they are neither.
             *
             * The 16px column minimum and the 4px gap are what let the
             * default 24-month range sit inside a 516px plot without
             * turning the card into a horizontal scroller: 24x16 + 23x4
             * = 476. Anything shorter than ~13 months is capped at 56px
             * a column instead, so a 3-6 month range stays a set of bars
             * rather than a row of banners. */
            <div className="mt-3 flex h-52 items-end justify-start gap-1 overflow-x-auto border-b border-border px-1 pb-1">
              {data.map((d, index) => {
                const active = selectedMonth === d.month;
                const labelled = index % stride === 0;
                const showYear =
                  index === 0 || data[index - stride]?.month.slice(0, 4) !== d.month.slice(0, 4);
                return (
                  <button
                    key={d.month}
                    type="button"
                    onClick={() => onSelectMonth(d.month)}
                    aria-pressed={active}
                    aria-label={`${formatMonthLabel(d.month)}: ${d.count} case${d.count === 1 ? "" : "s"}. View cases.`}
                    title={`${formatMonthLabel(d.month)}: ${d.count}`}
                    className="flex min-w-[16px] max-w-[56px] flex-1 flex-col items-center gap-1 rounded-t-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span
                      className={cn(
                        "w-full max-w-10 rounded-t-sm",
                        active ? "bg-primary" : "bg-primary/35 hover:bg-primary/55",
                        GROW_HEIGHT,
                      )}
                      style={fillVar(`${barPixels(d.count, max, 180)}px`)}
                    />
                    {/* Fixed height, so a column whose label the stride
                     * skipped still sits on the same baseline as one
                     * that kept it. */}
                    <span
                      className={cn(
                        "h-4 text-micro leading-4 whitespace-nowrap",
                        active ? "font-semibold text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {labelled ? formatMonthAxisLabel(d.month, showYear) : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

// --- Category breakdown donut -----------------------------------------------

/** Label for a breakdown row. A null category is a real, useful fact --
 * "these cases have not been triaged yet" -- so it is named rather than
 * hidden or left blank. */
function categoryLabel(trade: Trade | null): string {
  return trade === null ? "Uncategorised" : titleCase(trade);
}

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
    const color = TRADE_CSS_VAR[(d.trade && TRADE_TONE[d.trade]) || "gray"];
    const from = cursor;
    const to = cursor + d.percentage;
    cursor = to;
    return `${color} ${from}% ${to}%`;
  });
  const displayPercentages = largestRemainderPercentages(data.map((d) => d.percentage));
  const totalCount = data.reduce((sum, d) => sum + d.count, 0);

  // A donut of one slice conveys nothing, and when that slice is the
  // uncategorised group it is actively misleading -- it reads as "100% of
  // work is <blank>". Say what is actually true instead.
  const onlyUncategorised = data.length > 0 && data.every((d) => d.trade === null);

  return (
    <Card className="p-4">
      <CardHead title="Category breakdown" description="Click a trade to see its cases." />
      {data.length === 0 || onlyUncategorised ? (
        <p className="mt-6 py-6 text-center text-xs text-muted-foreground">
          {onlyUncategorised
            ? `None of the ${totalCount} case${totalCount === 1 ? "" : "s"} in this range has a category yet, so there is nothing to break down.`
            : "No categorised cases in the selected range."}
        </p>
      ) : (
        <div className="mt-3 flex items-center gap-5">
          {/* 160px, not the old 96px. The wedge angles are the entire
           * point of a donut and they were being compared at the size of
           * a favicon inside a 440-690px card; the hub scales with it
           * (inset-6 leaves a ~112px well for the total). The mount
           * animation here is a plain fade rather than a sweep: a
           * conic-gradient cannot be transitioned without an @property
           * registration, and that would have to live in styles.css. */}
          <div
            className="relative h-40 w-40 shrink-0 rounded-full motion-safe:animate-in motion-safe:fade-in motion-safe:duration-slow"
            style={{ background: `conic-gradient(${stops.join(", ")})` }}
            aria-hidden="true"
          >
            <div className="absolute inset-6 flex flex-col items-center justify-center rounded-full bg-card text-center">
              <b className="text-metric font-bold tracking-tight tabular-nums">{totalCount}</b>
              <span className="text-micro text-muted-foreground">Cases</span>
            </div>
          </div>
          {/* The legend rows ARE the interactive/accessible surface -- a
           * clickable conic-gradient wedge can't carry a keyboard-reachable
           * accessible name, these buttons can. */}
          <ul className="flex-1 space-y-1 text-micro">
            {data.map((d, index) => {
              const active = selectedTrade === d.trade;
              return (
                <li key={d.trade ?? "__uncategorised"}>
                  <button
                    type="button"
                    // An uncategorised group has no trade to filter by, so
                    // the row is inert rather than pretending to drill
                    // down into a category that does not exist.
                    disabled={d.trade === null}
                    title={
                      d.trade === null
                        ? "These cases have no category yet, so there is nothing to filter by."
                        : undefined
                    }
                    onClick={() => d.trade !== null && onSelectTrade(d.trade)}
                    aria-pressed={active}
                    // The visible row is three separate spans (dot, name,
                    // percentage, count); an explicit label reads as one
                    // sentence rather than four fragments.
                    aria-label={`${categoryLabel(d.trade)}: ${d.count} case${
                      d.count === 1 ? "" : "s"
                    }, ${displayPercentages[index]}% of the total.${
                      d.trade === null
                        ? " No category, so there is nothing to filter by."
                        : " View cases."
                    }`}
                    className={cn(
                      "flex w-full items-center rounded-md px-1.5 py-1 text-left outline-none transition-colors duration-fast ease-fixi focus-visible:ring-2 focus-visible:ring-ring",
                      active ? "bg-accent" : "hover:bg-accent/60",
                      d.trade === null &&
                        "cursor-default text-muted-foreground hover:bg-transparent",
                    )}
                  >
                    <span
                      className={cn(
                        "mr-2 h-2 w-2 shrink-0 rounded-full",
                        TRADE_DOT_CLASS[(d.trade && TRADE_TONE[d.trade]) || "gray"],
                      )}
                    />
                    <span className={active ? "font-semibold" : undefined}>
                      {categoryLabel(d.trade)}
                      {/* Visible, not a hover-only title: a tooltip does
                       * not exist on touch, and a greyed row with no
                       * stated reason just reads as broken. */}
                      {d.trade === null && (
                        <span className="ml-1 text-micro">(not triaged yet)</span>
                      )}
                    </span>
                    <b className="ml-auto shrink-0 tabular-nums">{displayPercentages[index]}%</b>
                    <span className="ml-2 shrink-0 tabular-nums text-muted-foreground">
                      ({d.count})
                    </span>
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
  // Two years is the ordinary case here, and two 14px columns adrift in
  // a 690px plot was the worst offender on the page.
  const horizontal = data.length > 0 && data.length <= HORIZONTAL_AT_OR_BELOW;

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
          <div className="mt-1 flex items-center gap-3 text-micro text-muted-foreground">
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
          {horizontal ? (
            <div className="mt-3 grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2">
              {data.map((d) => (
                <HBarRow
                  key={d.year}
                  label={String(d.year)}
                  active={selectedYear === d.year}
                  ariaLabel={`${d.year}: quoted ${formatPence(d.quoted_pence) ?? "not recorded"}, actual ${formatPence(d.actual_pence) ?? "not recorded"}. View cases.`}
                  title={`${d.year}: quoted ${formatPence(d.quoted_pence) ?? "—"}, actual ${
                    formatPence(d.actual_pence) ?? "—"
                  }`}
                  onClick={() => onSelectYear(d.year)}
                >
                  {/* Two tracks per year, same scale, stacked -- the pair
                   * is the comparison the card exists to make, and
                   * stacking keeps both against the same baseline x. */}
                  <HBarTrack
                    percent={barPercent(d.quoted_pence, max)}
                    tone="bg-primary/70"
                    value={formatPence(d.quoted_pence) ?? "—"}
                  />
                  <HBarTrack
                    percent={barPercent(d.actual_pence, max)}
                    tone="bg-chart-4"
                    value={formatPence(d.actual_pence) ?? "—"}
                  />
                </HBarRow>
              ))}
            </div>
          ) : (
            <div className="mt-2 flex h-44 items-end justify-start gap-3 overflow-x-auto border-b border-border px-1 pb-1">
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
                      "flex min-w-[72px] max-w-[112px] flex-1 flex-col items-center gap-1 rounded-t-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active && "bg-accent/60",
                    )}
                  >
                    <div className="flex h-36 items-end gap-1.5">
                      <span
                        className={cn("w-5 rounded-t-sm bg-primary/70", GROW_HEIGHT)}
                        style={fillVar(`${barPixels(d.quoted_pence, max, 144)}px`)}
                      />
                      <span
                        className={cn("w-5 rounded-t-sm bg-chart-4", GROW_HEIGHT)}
                        style={fillVar(`${barPixels(d.actual_pence, max, 144)}px`)}
                      />
                    </div>
                    <span
                      className={cn(
                        "text-micro",
                        active ? "font-semibold text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {d.year}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
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
  const horizontal = data.length > 0 && data.length <= HORIZONTAL_AT_OR_BELOW;

  return (
    <Card className="p-4">
      <CardHead title="Resolution time" description="Click a bucket to see its cases." />
      <div className="mt-2 flex gap-6">
        <div>
          <div className="text-metric font-bold tracking-tight tabular-nums">
            {averageHours != null ? `${averageHours.toFixed(1)}h` : "—"}
          </div>
          <div className="text-micro text-muted-foreground">Average</div>
        </div>
        <div>
          <div className="text-metric font-bold tracking-tight tabular-nums">
            {medianHours != null ? `${medianHours.toFixed(1)}h` : "—"}
          </div>
          <div className="text-micro text-muted-foreground">Median</div>
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
          {horizontal ? (
            <div className="mt-3 grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-1">
              {data.map((d) => {
                const active = selectedBucket === d.bucket;
                return (
                  <HBarRow
                    key={d.bucket}
                    label={d.bucket}
                    active={active}
                    ariaLabel={`${d.bucket}: ${d.count} case${d.count === 1 ? "" : "s"}. View cases.`}
                    title={`${d.bucket}: ${d.count}`}
                    onClick={() => onSelectBucket(d)}
                  >
                    <HBarTrack
                      percent={barPercent(d.count, max)}
                      tone={active ? "bg-primary" : "bg-primary/45"}
                      value={`${d.count} case${d.count === 1 ? "" : "s"}`}
                    />
                  </HBarRow>
                );
              })}
            </div>
          ) : (
            <div className="mt-3 flex h-44 items-end justify-start gap-2 overflow-x-auto border-b border-border px-1 pb-1">
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
                    className="flex min-w-[56px] max-w-[96px] flex-1 flex-col items-center gap-1 rounded-t-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span
                      className={cn(
                        "w-full max-w-12 rounded-t-sm",
                        active ? "bg-primary" : "bg-primary/35 hover:bg-primary/55",
                        GROW_HEIGHT,
                      )}
                      style={fillVar(`${barPixels(d.count, max, 148)}px`)}
                    />
                    <span
                      className={cn(
                        "h-4 text-center text-micro leading-4 whitespace-nowrap",
                        active ? "font-semibold text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {d.bucket}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
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
                    "flex w-full items-center gap-3 rounded-md py-2 pl-1 pr-2 text-left outline-none transition-colors duration-fast ease-fixi focus-visible:ring-2 focus-visible:ring-ring",
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
                    <div className="truncate text-strong font-semibold">
                      {titleCase(issue.trade)} — {issue.property_address}
                    </div>
                    <div className="text-micro text-muted-foreground">
                      {issue.count} occurrence{issue.count === 1 ? "" : "s"}
                    </div>
                  </div>
                  <span className="ml-auto shrink-0 text-micro text-muted-foreground">
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
