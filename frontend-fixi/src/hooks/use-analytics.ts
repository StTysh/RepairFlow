// Data source for the Overview ("/") and Insights ("/insights") pages.
//
// The backend routes this calls (GET /api/v1/overview, /api/v1/insights,
// /api/v1/insights/cases, /api/v1/properties) are being built by another
// agent in parallel -- this file is written against the contract in
// NEEDS_FROM_ROOT_analytics.md's originating task, not a verified
// openapi.json. Every response field is therefore optional here and every
// read in the consuming components goes through a fallback ("--" / 0 /
// empty list), never a value invented client-side. See
// frontend-fixi/src/routes/NEEDS_FROM_ROOT_analytics.md for the exact
// assumptions and any mismatch discovered while building this.
//
// Deliberately does NOT add to src/api/endpoints.ts or src/api/types.ts --
// both are owned/being edited by other agents in this same session. Fetch
// functions and response types for these four endpoints live here instead,
// built directly on the shared `request()` helper those other files also
// use.

import { useQuery } from "@tanstack/react-query";
import { request, type OperatorCredentials } from "@/api/client";
import type { Trade } from "@/api/types";
import type { CaseStatus } from "@/lib/fixi-data";
import { useAuthedCreds } from "@/lib/auth-context";

const OVERVIEW_POLL_MS = 15000;

// --- Overview ("/") ----------------------------------------------------

export type NeedsAttentionKind = "AWAITING_APPROVAL" | "ESCALATED" | "OVERDUE_FOLLOW_UP";

export interface NeedsAttentionItem {
  id: string;
  kind: NeedsAttentionKind;
  case_id: string;
  case_number: number;
  case_title: string;
  message: string;
  occurred_at: string;
}

export interface OverviewAppointmentItem {
  appointment_id: string;
  case_id: string;
  case_number: number;
  case_title?: string | null;
  start_at: string;
  end_at: string;
  property_address: string;
  contractor_name: string;
}

export interface OverviewActivityItem {
  id: string;
  case_id: string;
  case_number: number;
  case_title: string;
  type?: string;
  display_title: string;
  display_description?: string | null;
  occurred_at: string;
}

/** Every field optional/absent-tolerant: this is built against a contract
 * description, not a verified schema (see file header). Consumers must
 * treat every field as possibly missing. */
export interface OverviewResponse {
  property_count?: number;
  tenant_count?: number;
  approved_contractor_count?: number;
  /** Assumed shape: counts keyed by the 5 real CaseStatus values. A
   * top-level `open_case_count` is read first if the backend provides one
   * directly; this is the fallback used to derive it otherwise (see
   * routes/index.tsx). */
  case_counts_by_status?: Partial<Record<CaseStatus, number>>;
  open_case_count?: number;
  needs_attention?: NeedsAttentionItem[];
  upcoming_appointments?: OverviewAppointmentItem[];
  recent_activity?: OverviewActivityItem[];
}

export function useOverview() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["overview"],
    queryFn: () => request<OverviewResponse>(creds, "/api/v1/overview"),
    refetchInterval: OVERVIEW_POLL_MS,
  });
}

// --- Insights ("/insights") ---------------------------------------------

export interface InsightsFilters {
  date_from: string;
  date_to: string;
  property_id?: string | undefined;
  category?: Trade | undefined;
  include_archived: boolean;
}

function baseInsightsSearch(filters: InsightsFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.property_id) params.set("property_id", filters.property_id);
  if (filters.category) params.set("category", filters.category);
  params.set("include_archived", String(filters.include_archived));
  return params;
}

export interface CaseVolumeMonth {
  /** "YYYY-MM" -- normalised from the API's separate year/month integers. */
  month: string;
  count: number;
}

export interface CategoryBreakdownItem {
  /** Null for cases triage has not classified yet. The API deliberately
   * keeps those as their own group so the percentages describe the whole
   * matched set rather than a silently filtered subset -- see
   * `analytics.category_breakdown`. Casting that null to a Trade is what
   * produced a blank, unlabelled 100% wedge. */
  trade: Trade | null;
  count: number;
  percentage: number;
}

export interface SpendByYearItem {
  year: number;
  quoted_pence: number;
  actual_pence: number;
}

export interface ResolutionBucket {
  bucket: string;
  count: number;
  /** Real edges in hours, served by the API (`analytics.resolution_bucket_bounds`)
   * rather than re-derived from the label here -- a second copy of that
   * table in the UI would go stale the first time the buckets change.
   * `max_hours` is null on the open-ended top bucket. */
  min_hours: number;
  max_hours: number | null;
}

export interface RecurringIssueRow {
  property_id: string;
  property_address: string;
  trade: Trade;
  count: number;
  last_occurred_at: string;
  case_ids?: string[];
}

export interface ComparisonMetric {
  current: number;
  previous: number;
  /** null when there is no baseline to compare against -- the API returns
   * `is_new` alongside it so the UI can render "new" rather than a
   * fabricated percentage or an infinity. */
  pct_change: number | null;
  is_new: boolean;
}

export type InsightsComparison = Record<string, ComparisonMetric | undefined>;

export interface InsightsResponse {
  case_volume_by_month: CaseVolumeMonth[];
  category_breakdown: CategoryBreakdownItem[];
  spend_by_year: SpendByYearItem[];
  resolution_time_distribution: ResolutionBucket[];
  average_hours: number | null;
  median_hours: number | null;
  recurring_issues: RecurringIssueRow[];
  comparison: InsightsComparison;
  includes_archived_history: boolean;
  archived_case_count: number;
}

/** The API's actual `GET /insights` body.
 *
 * Five fields are named differently from what this screen was written
 * against: month arrives as separate `year`/`month` integers rather than a
 * "YYYY-MM" key, the trade axis is called `category`, the resolution
 * figures are nested under `resolution` with `label` rather than `bucket`,
 * the comparison block is `case_volume_comparison` with `change_pct`, and
 * `recurring_issues` also uses `category`.
 *
 * Adapting here rather than renaming either side: the backend shape is
 * what `backend/tests/test_analytics_api.py` asserts and what
 * `/reports/summary` and the CSV export already share, and moving the
 * translation into the screen would spread it across a dozen call sites.
 * One normaliser, one place to look when the contract next moves.
 */
interface RawInsightsResponse {
  case_volume_by_month?: Array<{ year: number; month: number; count: number }>;
  category_breakdown?: Array<{ category: string; count: number; percentage: number }>;
  spend_by_year?: SpendByYearItem[];
  resolution?: {
    buckets?: Array<{
      label: string;
      count: number;
      min_hours: number;
      max_hours: number | null;
    }>;
    average_hours?: number | null;
    median_hours?: number | null;
  };
  recurring_issues?: Array<{
    property_id: string;
    property_address: string;
    category: string;
    count: number;
    last_occurred_at: string;
    case_ids?: string[];
  }>;
  case_volume_comparison?: {
    current: number;
    previous: number;
    change_pct: number | null;
    is_new: boolean;
  };
  includes_archived_history?: boolean;
  archived_case_count?: number;
}

function normalizeInsights(raw: RawInsightsResponse): InsightsResponse {
  const comparison: InsightsComparison = {};
  if (raw.case_volume_comparison) {
    comparison["case_volume"] = {
      current: raw.case_volume_comparison.current,
      previous: raw.case_volume_comparison.previous,
      pct_change: raw.case_volume_comparison.change_pct,
      is_new: raw.case_volume_comparison.is_new,
    };
  }
  return {
    case_volume_by_month: (raw.case_volume_by_month ?? []).map((row) => ({
      month: `${String(row.year).padStart(4, "0")}-${String(row.month).padStart(2, "0")}`,
      count: row.count,
    })),
    category_breakdown: (raw.category_breakdown ?? []).map((row) => ({
      trade: (row.category ?? null) as Trade | null,
      count: row.count,
      percentage: row.percentage,
    })),
    spend_by_year: raw.spend_by_year ?? [],
    resolution_time_distribution: (raw.resolution?.buckets ?? []).map((b) => ({
      bucket: b.label,
      count: b.count,
      min_hours: b.min_hours,
      max_hours: b.max_hours,
    })),
    average_hours: raw.resolution?.average_hours ?? null,
    median_hours: raw.resolution?.median_hours ?? null,
    recurring_issues: (raw.recurring_issues ?? []).map((row) => ({
      property_id: row.property_id,
      property_address: row.property_address,
      // Never null in practice -- `analytics.recurring_issues` excludes
      // `category IS NULL` because a "recurring category" is meaningless
      // without one -- but the cast is narrowed anyway rather than
      // asserting a shape this file cannot enforce.
      trade: (row.category ?? "OTHER") as Trade,
      count: row.count,
      last_occurred_at: row.last_occurred_at,
      ...(row.case_ids ? { case_ids: row.case_ids } : {}),
    })),
    comparison,
    includes_archived_history: raw.includes_archived_history ?? false,
    archived_case_count: raw.archived_case_count ?? 0,
  };
}

export function useInsights(filters: InsightsFilters) {
  const creds = useAuthedCreds();
  const qs = baseInsightsSearch(filters).toString();
  return useQuery({
    queryKey: ["insights", qs],
    queryFn: async () =>
      normalizeInsights(await request<RawInsightsResponse>(creds, `/api/v1/insights?${qs}`)),
    enabled: Boolean(filters.date_from && filters.date_to),
  });
}

export interface InsightsCaseRow {
  id: string;
  case_number: number;
  title: string;
  status: CaseStatus;
  property_address?: string | null;
  trade?: Trade | null;
  quoted_pence?: number | null;
  created_at: string;
  resolved_at?: string | null;
  is_archived?: boolean;
}

export interface InsightsCasesResponse {
  items?: InsightsCaseRow[];
}

/** Same naming drift as `normalizeInsights` above: the API row calls the
 * id `case_id`, the trade `category`, and the close timestamp
 * `closed_at`. */
interface RawInsightsCaseRow {
  case_id: string;
  case_number: number;
  title: string;
  status: CaseStatus;
  category?: string | null;
  property_address?: string | null;
  created_at: string;
  closed_at?: string | null;
  quoted_pence?: number | null;
  invoiced_pence?: number | null;
  is_archived?: boolean;
}

export function useInsightsCases(filters: InsightsFilters | null) {
  const creds = useAuthedCreds();
  const qs = filters ? baseInsightsSearch(filters).toString() : "";
  return useQuery({
    queryKey: ["insights-cases", qs],
    queryFn: async () => {
      const raw = await request<{ items?: RawInsightsCaseRow[] }>(
        creds,
        `/api/v1/insights/cases?${qs}`,
      );
      const items: InsightsCaseRow[] = (raw.items ?? []).map((row) => ({
        id: row.case_id,
        case_number: row.case_number,
        title: row.title,
        status: row.status,
        property_address: row.property_address ?? null,
        trade: (row.category ?? null) as Trade | null,
        // The detail panel shows what the work was expected to cost;
        // `invoiced_pence` is actual money and belongs on the Costs and
        // Reports surfaces, not mixed into a quote column.
        quoted_pence: row.quoted_pence ?? null,
        created_at: row.created_at,
        resolved_at: row.closed_at ?? null,
        is_archived: row.is_archived ?? false,
      }));
      return { items } satisfies InsightsCasesResponse;
    },
    enabled: filters !== null,
  });
}

// --- Properties (filter picker) ------------------------------------------

export interface PropertyOption {
  id: string;
  address_line: string;
  postcode: string;
}

export interface PropertiesResponse {
  items?: PropertyOption[];
}

export function useAnalyticsProperties() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: ["properties", "picker"],
    queryFn: () => fetchProperties(creds),
    staleTime: 5 * 60 * 1000,
  });
}

function fetchProperties(creds: OperatorCredentials): Promise<PropertiesResponse> {
  return request<PropertiesResponse>(creds, "/api/v1/properties?limit=200");
}
