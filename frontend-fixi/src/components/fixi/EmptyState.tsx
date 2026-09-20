import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Card } from "@/components/fixi/AppShell";
import { cn } from "@/lib/utils";

/**
 * The shared "there is genuinely nothing here" panel.
 *
 * An empty operational workspace is a correct state, not a failure: this
 * application seeds no fictional workload, so a fresh install legitimately
 * has zero cases, zero messages and zero spend. Every list therefore needs
 * to say *why* it is empty and what the operator can do next, rather than
 * rendering a blank rectangle that reads as a broken screen.
 *
 * Deliberately distinct from `ErrorState` below: "nothing yet" and "we
 * could not load this" must never look the same, because the first is
 * normal and the second needs action.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode | undefined;
  className?: string | undefined;
}) {
  return (
    <Card className={cn("flex flex-col items-center px-6 py-12 text-center", className)}>
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-accent text-muted-foreground">
        <Icon className="h-5 w-5" strokeWidth={1.8} />
      </span>
      <h3 className="mt-3 text-sm font-semibold">{title}</h3>
      <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </Card>
  );
}

/** A load that failed, with the reason and a way to try again. */
export function ErrorState({
  title = "This didn't load",
  detail,
  onRetry,
  className,
}: {
  title?: string | undefined;
  // `| undefined` is deliberate: tsconfig has exactOptionalPropertyTypes,
  // and every caller derives this from an `unknown` error, so the value
  // genuinely may be undefined at the call site rather than simply absent.
  detail?: string | undefined;
  onRetry?: (() => void) | undefined;
  className?: string | undefined;
}) {
  return (
    <Card className={cn("px-6 py-10 text-center", className)}>
      <h3 className="text-sm font-semibold text-destructive">{title}</h3>
      {detail ? (
        <p className="mx-auto mt-1 max-w-md break-words text-xs text-muted-foreground">{detail}</p>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold transition-colors hover:bg-accent"
        >
          Try again
        </button>
      ) : null}
    </Card>
  );
}

/** Skeleton rows, sized to the list they stand in for. */
export function LoadingRows({
  rows = 4,
  className,
}: {
  rows?: number | undefined;
  className?: string | undefined;
}) {
  return (
    <div className={cn("space-y-2", className)} aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="h-12 animate-pulse rounded-xl bg-muted/60" />
      ))}
    </div>
  );
}
