import { cn } from "@/lib/utils";

/**
 * Loading placeholders shaped like the content they stand in for.
 *
 * Twelve screens in this app announced a load with the bare string
 * "Loading…". That reads as a stall: the layout is empty, then it is
 * full, and everything jumps. A placeholder the same shape and height as
 * the real thing means the page is laid out before the data lands, so
 * arrival is a fill rather than a reflow -- which matters most on the
 * polled surfaces, where a refetch would otherwise make the whole panel
 * collapse and spring back.
 *
 * The shimmer is a background sweep, not opacity pulsing: it survives
 * being placed inside a card without making the card's border breathe,
 * and `--animate-shimmer` is already clamped by the global
 * prefers-reduced-motion rule in styles.css.
 */
export function Skeleton({ className }: { className?: string | undefined }) {
  return (
    <div
      className={cn(
        "animate-shimmer rounded-md bg-[length:200%_100%]",
        // The highlight is --card (white), not a mix of --muted and
        // --background. Those two differ by 0.017 in oklch lightness, so
        // the mix produced a sweep of 0.008 -- measured in the browser and
        // invisible. Against --card the sweep is 0.035, which is the
        // conventional depth for a light-theme skeleton and actually reads.
        "bg-[linear-gradient(90deg,var(--muted)_0%,var(--card)_50%,var(--muted)_100%)]",
        className,
      )}
    />
  );
}

/** Screen-reader announcement plus a visual placeholder, as one unit. */
export function SkeletonBlock({
  label = "Loading",
  className,
  children,
}: {
  label?: string | undefined;
  className?: string | undefined;
  children: React.ReactNode;
}) {
  return (
    <div className={className} aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}…</span>
      {children}
    </div>
  );
}

/** Paragraph-shaped lines; the last is short, as real text is. */
export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number | undefined;
  className?: string | undefined;
}) {
  return (
    <SkeletonBlock className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn("h-3", i === lines - 1 ? "w-2/5" : "w-full")} />
      ))}
    </SkeletonBlock>
  );
}

/**
 * Table rows at the real row height, with per-column widths.
 *
 * `widths` are Tailwind width classes, one per cell; the caller passes
 * the same column rhythm its real table uses so nothing shifts sideways
 * when the data arrives.
 */
export function SkeletonRows({
  rows = 6,
  widths = ["w-10", "w-2/5", "w-24", "w-20", "w-16"],
  rowClassName,
  className,
}: {
  rows?: number | undefined;
  widths?: readonly string[] | undefined;
  rowClassName?: string | undefined;
  className?: string | undefined;
}) {
  return (
    <SkeletonBlock className={cn("divide-y divide-border", className)}>
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={r}
          className={cn("flex h-[45px] items-center gap-3 px-3", rowClassName)}
          // Each row fades a little later than the one above it, so a
          // long list reads top-to-bottom instead of strobing as a slab.
          style={{ animationDelay: `${r * 60}ms` }}
        >
          {widths.map((w, c) => (
            <Skeleton key={c} className={cn("h-3", w)} />
          ))}
        </div>
      ))}
    </SkeletonBlock>
  );
}

/** The KPI strip, at its real 72px card height so the page never jumps. */
export function SkeletonKpis({
  count = 6,
  className,
}: {
  count?: number | undefined;
  className?: string | undefined;
}) {
  return (
    <SkeletonBlock
      label="Loading figures"
      className={cn("grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6", className)}
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="flex min-h-[72px] items-center gap-3 rounded-xl border border-border bg-card px-4 py-3"
        >
          <Skeleton className="h-9 w-9 shrink-0 rounded-full" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-5 w-12" />
            <Skeleton className="h-2.5 w-4/5" />
          </div>
        </div>
      ))}
    </SkeletonBlock>
  );
}

/** A stack of message/list cards. */
export function SkeletonCards({
  count = 3,
  height = "h-16",
  className,
}: {
  count?: number | undefined;
  height?: string | undefined;
  className?: string | undefined;
}) {
  return (
    <SkeletonBlock className={cn("space-y-2", className)}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className={cn("w-full rounded-xl", height)} />
      ))}
    </SkeletonBlock>
  );
}
