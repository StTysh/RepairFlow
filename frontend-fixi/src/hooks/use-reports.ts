import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, authHeader, BASE_URL, request } from "@/api/client";
import { useAuthedCreds } from "@/lib/auth-context";

// Same deviation as use-messaging.ts: GET /api/v1/reports/summary,
// /api/v1/reports/export.csv and /api/v1/properties are being built by
// another agent in this same tree right now and aren't on disk yet (no
// backend/app/api/reports.py or plain GET /properties at the time this was
// written -- see NEEDS_FROM_ROOT_messaging.md). The contract handed to this
// slice only fixes the top-level section names ("maintenance, spend,
// resolution and recurring-issue sections, each with the row-level detail
// backing its totals") -- it does not fix per-row column names. Rather than
// hardcode a guessed schema that would silently break the moment the real
// response differs, ReportSection below is a generic totals+rows adapter
// and the UI renders whatever columns/keys actually come back.

export interface ReportsFilters {
  dateFrom: string;
  dateTo: string;
  propertyId: string;
  category: string;
  includeArchived: boolean;
}

export interface ReportSection {
  totals: Record<string, number>;
  rows: Array<Record<string, unknown>>;
}

export interface ReportsSummary {
  includesArchived: boolean;
  archivedCaseCount: number;
  maintenance: ReportSection | null;
  spend: ReportSection | null;
  resolution: ReportSection | null;
  recurringIssues: ReportSection | null;
  /** The case-level detail every other section aggregates, and exactly
   * what `export.csv` writes. Shown as its own table so the export is
   * never a set of rows nobody can see on screen. */
  cases: ReportSection | null;
}

function buildReportsQuery(filters: ReportsFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.propertyId) params.set("property_id", filters.propertyId);
  if (filters.category) params.set("category", filters.category);
  if (filters.includeArchived) params.set("include_archived", "true");
  return params;
}

/** Numeric fields of an object, ignoring the nested arrays. */
function numericTotals(raw: unknown): Record<string, number> {
  const totals: Record<string, number> = {};
  if (!raw || typeof raw !== "object") return totals;
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === "number") totals[key] = value;
  }
  return totals;
}

function arrayAt(raw: unknown, key: string): Array<Record<string, unknown>> {
  if (!raw || typeof raw !== "object") return [];
  const value = (raw as Record<string, unknown>)[key];
  return Array.isArray(value) ? (value as Array<Record<string, unknown>>) : [];
}

function section(raw: unknown, rowsKey: string): ReportSection | null {
  if (!raw || typeof raw !== "object") return null;
  return { totals: numericTotals(raw), rows: arrayAt(raw, rowsKey) };
}

export function useReportsSummary(filters: ReportsFilters) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["reports-summary", filters],
    queryFn: async () => {
      const params = buildReportsQuery(filters);
      const raw = await request<Record<string, unknown>>(
        creds,
        `/api/v1/reports/summary?${params.toString()}`,
      );
      // Each section names its detail array differently, and the
      // case-level rows live once at the top level rather than being
      // repeated per section. An earlier generic adapter looked for
      // `rows` inside each section, found nothing, and rendered "No rows
      // for the selected filters" on all four -- permanently, whatever
      // the data.
      const caseRows = arrayAt(raw, "rows");
      const summary: ReportsSummary = {
        includesArchived: Boolean(
          raw["includes_archived_history"] ?? raw["include_archived"] ?? filters.includeArchived,
        ),
        archivedCaseCount:
          typeof raw["archived_case_count"] === "number" ? raw["archived_case_count"] : 0,
        maintenance: section(raw["maintenance"], "category_breakdown"),
        spend: section(raw["spend"], "by_year"),
        resolution: section(raw["resolution"], "buckets"),
        recurringIssues: section(raw["recurring"] ?? raw["recurring_issues"], "groups"),
        cases: caseRows.length
          ? { totals: { case_count: caseRows.length }, rows: caseRows }
          : { totals: { case_count: 0 }, rows: [] },
      };
      return summary;
    },
  });
}

export interface PropertyOption {
  id: string;
  address_line: string;
}

/** GET /api/v1/properties?limit=200 -- distinct from the demo-only
 * /api/v1/demo/seed-refs list use-new-ticket.ts's useSeedRefs reads (that
 * endpoint's own docstring calls it demo glue, not a general property
 * list). Field names degrade defensively (id/property_id,
 * address_line/address) since the exact response shape isn't fixed by the
 * contract this slice was given. */
export function useReportProperties() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["reports-properties"],
    staleTime: 60_000,
    queryFn: async () => {
      const raw = await request<{ items?: Array<Record<string, unknown>> }>(
        creds,
        "/api/v1/properties?limit=200",
      );
      const items = Array.isArray(raw.items) ? raw.items : [];
      const options: PropertyOption[] = [];
      for (const p of items) {
        const id = String(p["id"] ?? p["property_id"] ?? "");
        if (!id) continue;
        const address = String(p["address_line"] ?? p["address"] ?? "Unknown address");
        options.push({ id, address_line: address });
      }
      return options;
    },
  });
}

function reportsWindowLabel(filters: ReportsFilters): string {
  return `${filters.dateFrom || "all-time"}_to_${filters.dateTo || "now"}`;
}

/** GET /api/v1/reports/export.csv through authHeader() (a plain <a href>
 * can't carry HTTP Basic) -- fetch+blob+download, same house pattern as
 * RecordingPlayer in maintenance.tickets.$ticketId.{-$section}.tsx, but
 * that one never revokes its object URL; this one does. Prefers a
 * server-supplied filename (Content-Disposition) and falls back to one
 * built from the active date window otherwise. */
export function useExportReportsCsv() {
  const creds = useAuthedCreds();
  return useMutation({
    mutationFn: async (filters: ReportsFilters) => {
      const params = buildReportsQuery(filters);
      const res = await fetch(`${BASE_URL}/api/v1/reports/export.csv?${params.toString()}`, {
        headers: { Authorization: authHeader(creds) },
      });
      if (!res.ok) {
        throw new ApiError(res.status, res.statusText || "Export failed");
      }
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition");
      const match = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      const filename = match?.[1]
        ? decodeURIComponent(match[1])
        : `repairflow-report_${reportsWindowLabel(filters)}.csv`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      return { filename };
    },
    onError: (error: Error) => toast.error(`Could not export report: ${error.message}`),
  });
}
