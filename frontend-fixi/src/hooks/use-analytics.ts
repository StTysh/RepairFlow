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
  month: string;
  count: number;
}

export interface CategoryBreakdownItem {
  trade: Trade;
  count: number;
  percentage: number;
}

export interface SpendByYearItem {
  year: number;
  quoted_pence: number;
  actual_pence: number;
}

/** `min_hours`/`max_hours` are NOT confirmed on the contract -- read
 * defensively if present (lets the resolution-time drill-down filter
 * precisely); when absent the drill-down degrades to "everything in the
 * current filters" rather than guessing bucket boundaries. See
 * NEEDS_FROM_ROOT_analytics.md. */
export interface ResolutionBucket {
  bucket: string;
  count: number;
  min_hours?: number | null;
  max_hours?: number | null;
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
  pct_change: number | null;
  is_new: boolean;
}

export type InsightsComparison = Record<string, ComparisonMetric | undefined>;

export interface InsightsResponse {
  case_volume_by_month?: CaseVolumeMonth[];
  category_breakdown?: CategoryBreakdownItem[];
  spend_by_year?: SpendByYearItem[];
  resolution_time_distribution?: ResolutionBucket[];
  average_hours?: number | null;
  median_hours?: number | null;
  recurring_issues?: RecurringIssueRow[];
  comparison?: InsightsComparison;
  includes_archived_history?: boolean;
  archived_case_count?: number;
}

export function useInsights(filters: InsightsFilters) {
  const creds = useAuthedCreds();
  const qs = baseInsightsSearch(filters).toString();
  return useQuery({
    queryKey: ["insights", qs],
    queryFn: () => request<InsightsResponse>(creds, `/api/v1/insights?${qs}`),
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
}

export interface InsightsCasesResponse {
  items?: InsightsCaseRow[];
}

export function useInsightsCases(filters: InsightsFilters | null) {
  const creds = useAuthedCreds();
  const qs = filters ? baseInsightsSearch(filters).toString() : "";
  return useQuery({
    queryKey: ["insights-cases", qs],
    queryFn: () => request<InsightsCasesResponse>(creds, `/api/v1/insights/cases?${qs}`),
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
