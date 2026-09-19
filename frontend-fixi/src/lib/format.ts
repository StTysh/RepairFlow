// Ported from frontend/src/lib/format.ts (old Fixi UI) -- keeping the
// same formatting conventions so the two frontends read consistently while
// both exist side by side.

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** "Tomorrow, 14 Sep 2026" / "15:00 – 17:00"-style range, split as two
 * strings so callers can lay the date and time out separately (matches the
 * ticket detail "Next appointment" block). */
export function formatDateRange(startIso: string, endIso: string): { date: string; time: string } {
  return {
    date: formatDate(startIso),
    time: `${formatTime(startIso)} – ${formatTime(endIso)}`,
  };
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const deltaMs = Date.now() - new Date(iso).getTime();
  const deltaMin = Math.round(deltaMs / 60000);
  if (Math.abs(deltaMin) < 1) return "just now";
  if (Math.abs(deltaMin) < 60) return `${deltaMin}m ago`;
  const deltaHr = Math.round(deltaMin / 60);
  if (Math.abs(deltaHr) < 24) return `${deltaHr}h ago`;
  return `${Math.round(deltaHr / 24)}d ago`;
}

export function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** GBP display for a pence-denominated amount from the API (WorkOrder
 * quote_pence/approved_limit_pence). null stays null -- callers decide the
 * "not recorded" copy rather than this silently rendering "£0.00". */
export function formatPence(pence: number | null | undefined): string | null {
  if (pence === null || pence === undefined) return null;
  return (pence / 100).toLocaleString(undefined, {
    style: "currency",
    currency: "GBP",
  });
}

/** KPI trend arrow for a `*_delta_pct` field off DashboardMetrics (backend:
 * services.reconstructed_status_counts -- "vs 7 days ago", a documented
 * simplified replay of the CaseEvent log, not a literal historical audit).
 * `null` means the backend had nothing to compare against and MUST render
 * as no delta at all, never a fabricated "0%". */
export function formatDeltaPct(pct: number | null | undefined): string | null {
  if (pct === null || pct === undefined) return null;
  const rounded = Math.round(Math.abs(pct));
  if (pct > 0) return `↑${rounded}%`;
  if (pct < 0) return `↓${rounded}%`;
  return `→${rounded}%`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase();
}
