import { cn } from "@/lib/utils";
import type { CaseStatus, StatusTone, Urgency } from "@/lib/fixi-data";
import { STATUS_LABEL, URGENCY_LABEL, statusTone, urgencyTone } from "@/lib/fixi-data";

const toneClasses: Record<StatusTone, string> = {
  red: "bg-status-red text-status-red-foreground",
  orange: "bg-status-orange text-status-orange-foreground",
  green: "bg-status-green text-status-green-foreground",
  blue: "bg-status-blue text-status-blue-foreground",
  amber: "bg-status-amber text-status-amber-foreground",
  purple: "bg-status-purple text-status-purple-foreground",
  gray: "bg-status-gray text-status-gray-foreground",
};

export function Pill({
  tone,
  children,
  className,
  title,
}: {
  tone: keyof typeof toneClasses;
  children: React.ReactNode;
  className?: string | undefined;
  /** Hover/long-press explanation. Supplementary only -- a pill whose
   * meaning is not obvious from its text needs visible words nearby, not
   * a tooltip doing the real work. */
  title?: string | undefined;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Urgency badge -- a separate axis from case status (see fixi-data.ts).
 * Replaces the old fictional High/Medium/Low "priority" concept. */
export function UrgencyBadge({
  urgency,
  className,
}: {
  urgency: Urgency;
  className?: string | undefined;
}) {
  return (
    <Pill tone={urgencyTone(urgency)} className={className}>
      {URGENCY_LABEL[urgency]}
    </Pill>
  );
}

export function StatusBadge({
  status,
  className,
}: {
  status: CaseStatus;
  className?: string | undefined;
}) {
  return (
    <Pill tone={statusTone(status)} className={className}>
      {STATUS_LABEL[status]}
    </Pill>
  );
}
