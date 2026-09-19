export function formatPence(pence: number | null | undefined): string {
  if (pence === null || pence === undefined) return "—";
  return `£${(pence / 100).toFixed(2)}`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
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
