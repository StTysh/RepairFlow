import { cn } from "@/lib/utils";
import type { Priority, StatusTone } from "@/lib/fixi-data";
import { statusTone } from "@/lib/fixi-data";

const toneClasses: Record<StatusTone | "red" | "orange", string> = {
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
}: {
  tone: keyof typeof toneClasses;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
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

export function PriorityBadge({ priority }: { priority: Priority }) {
  const tone = priority === "High" ? "red" : priority === "Medium" ? "orange" : "green";
  return <Pill tone={tone}>{priority}</Pill>;
}

export function StatusBadge({ status }: { status: string }) {
  return <Pill tone={statusTone(status)}>{status}</Pill>;
}
