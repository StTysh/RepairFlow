// Data layer for the Contractors and Tenants directories (GET/POST/PATCH
// /api/v1/contractors* and /api/v1/tenants*, plus GET /api/v1/properties
// for the tenant form's property picker).
//
// These routes are being built by another agent in parallel (see
// CLAUDE.md's per-agent ownership split), so nothing here is generated from
// a live OpenAPI schema yet -- everything is hand-typed against the
// documented contract and defensively normalized: a missing/malformed
// optional field degrades to a safe default (empty array, null, 0, false)
// rather than throwing, so a field-name drift on the backend shows up as a
// dash in the UI instead of a crashed screen. Any drift actually observed
// is recorded in routes/NEEDS_FROM_ROOT_directories.md.
//
// Not wired through src/api/endpoints.ts or src/api/types.ts (both owned by
// another agent this session) -- this file is self-contained, following the
// same request()/ApiError plumbing those files use.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, request, type OperatorCredentials } from "@/api/client";
import { useAuthedCreds } from "@/lib/auth-context";
import type { StatusTone } from "@/lib/fixi-data";

// --------------------------------------------------------------------------
// Enums (mirrored from backend/app/schemas.py -- Trade, ContractorApprovalStatus)
// --------------------------------------------------------------------------

export type Trade = "ROOFING" | "SCAFFOLDING" | "PLUMBING" | "ELECTRICAL" | "OTHER";
export const TRADES: Trade[] = ["ROOFING", "SCAFFOLDING", "PLUMBING", "ELECTRICAL", "OTHER"];

export type ContractorApprovalStatus = "APPROVED" | "PENDING" | "REJECTED";
export const CONTRACTOR_APPROVAL_STATUSES: ContractorApprovalStatus[] = [
  "APPROVED",
  "PENDING",
  "REJECTED",
];

export function approvalTone(status: ContractorApprovalStatus): StatusTone {
  switch (status) {
    case "APPROVED":
      return "green";
    case "PENDING":
      return "amber";
    case "REJECTED":
      return "gray";
    default:
      return "gray";
  }
}

/** Explains what each approval status actually means for assignment --
 * an unapproved contractor is a research candidate, not someone bookable
 * (CLAUDE.md: "A candidate from the web is not an approved contractor"). */
export function approvalExplanation(status: ContractorApprovalStatus): string {
  switch (status) {
    case "APPROVED":
      return "Verified and can be assigned to work.";
    case "PENDING":
      return "Research candidate only -- not yet verified, cannot be assigned.";
    case "REJECTED":
      return "Rejected -- excluded from assignment.";
    default:
      return "";
  }
}

function isTrade(value: unknown): value is Trade {
  return typeof value === "string" && (TRADES as string[]).includes(value);
}

function isApprovalStatus(value: unknown): value is ContractorApprovalStatus {
  return typeof value === "string" && (CONTRACTOR_APPROVAL_STATUSES as string[]).includes(value);
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function asTradeArray(value: unknown): Trade[] {
  return Array.isArray(value) ? value.filter(isTrade) : [];
}

// --------------------------------------------------------------------------
// Contractors
// --------------------------------------------------------------------------

export interface ContractorListItem {
  id: string;
  display_name: string;
  trades: Trade[];
  service_postcodes: string[];
  approval_status: ContractorApprovalStatus;
  connector: string | null;
  contact_reference: string | null;
  verification_note: string | null;
  provenance: string | null;
  assigned_work_order_count: number;
  completed_work_order_count: number;
  is_archived: boolean;
}

/** Matches contractors.py's ContractorWorkHistoryItem exactly: the work
 * order's id is `id` (not `work_order_id`), and archival status is
 * `case_is_archived` (not `is_archived`) -- both renamed here rather than
 * read from the wrong wire key, since the old names silently shipped
 * `""`/`false` for every row (docs/audit/07 Finding 4). */
export interface ContractorWorkHistoryItem {
  id: string;
  case_id: string;
  case_number: number | null;
  case_title: string;
  trade: Trade | null;
  status: string;
  scope: string;
  quote_pence: number | null;
  created_at: string | null;
  case_is_archived: boolean;
}

export interface ContractorProfile extends ContractorListItem {
  work_history: ContractorWorkHistoryItem[];
  appointment_count: number;
}

function normalizeContractorListItem(raw: unknown): ContractorListItem {
  const r = (raw ?? {}) as Record<string, unknown>;
  return {
    id: asString(r["id"]) ?? "",
    display_name: asString(r["display_name"]) ?? "Unnamed contractor",
    trades: asTradeArray(r["trades"]),
    service_postcodes: asStringArray(r["service_postcodes"]),
    approval_status: isApprovalStatus(r["approval_status"]) ? r["approval_status"] : "PENDING",
    connector: asString(r["connector"]),
    contact_reference: asString(r["contact_reference"]),
    verification_note: asString(r["verification_note"]),
    provenance: asString(r["provenance"]),
    assigned_work_order_count: asNumber(r["assigned_work_order_count"]),
    completed_work_order_count: asNumber(r["completed_work_order_count"]),
    is_archived: Boolean(r["is_archived"]),
  };
}

function normalizeWorkHistoryItem(raw: unknown): ContractorWorkHistoryItem {
  const r = (raw ?? {}) as Record<string, unknown>;
  return {
    id: asString(r["id"]) ?? "",
    case_id: asString(r["case_id"]) ?? "",
    case_number: typeof r["case_number"] === "number" ? r["case_number"] : null,
    case_title: asString(r["case_title"]) ?? "Untitled case",
    trade: isTrade(r["trade"]) ? r["trade"] : null,
    status: asString(r["status"]) ?? "UNKNOWN",
    scope: asString(r["scope"]) ?? "",
    quote_pence: typeof r["quote_pence"] === "number" ? r["quote_pence"] : null,
    created_at: asString(r["created_at"]),
    case_is_archived: Boolean(r["case_is_archived"]),
  };
}

function normalizeContractorProfile(raw: unknown): ContractorProfile {
  const r = (raw ?? {}) as Record<string, unknown>;
  return {
    ...normalizeContractorListItem(r),
    work_history: Array.isArray(r["work_history"])
      ? r["work_history"].map(normalizeWorkHistoryItem)
      : [],
    appointment_count: asNumber(r["appointment_count"]),
  };
}

export interface ContractorListParams {
  q?: string | undefined;
  trade?: Trade | "ALL" | undefined;
  approval_status?: ContractorApprovalStatus | "ALL" | undefined;
  limit?: number | undefined;
  offset?: number | undefined;
  include_archived?: boolean | undefined;
}

export interface DirectoryPage<T> {
  items: T[];
  total: number;
  has_more: boolean;
}

async function listContractors(
  creds: OperatorCredentials,
  params: ContractorListParams,
): Promise<DirectoryPage<ContractorListItem>> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.trade && params.trade !== "ALL") search.set("trade", params.trade);
  if (params.approval_status && params.approval_status !== "ALL") {
    search.set("approval_status", params.approval_status);
  }
  search.set("limit", String(params.limit ?? 50));
  search.set("offset", String(params.offset ?? 0));
  if (params.include_archived) search.set("include_archived", "true");
  const raw = await request<Record<string, unknown>>(
    creds,
    `/api/v1/contractors?${search.toString()}`,
  );
  return {
    items: Array.isArray(raw["items"]) ? raw["items"].map(normalizeContractorListItem) : [],
    total: asNumber(raw["total"]),
    has_more: Boolean(raw["has_more"]),
  };
}

async function getContractor(creds: OperatorCredentials, id: string): Promise<ContractorProfile> {
  const raw = await request<Record<string, unknown>>(creds, `/api/v1/contractors/${id}`);
  return normalizeContractorProfile(raw);
}

export interface ContractorCreateInput {
  display_name: string;
  trades: Trade[];
  service_postcodes: string[];
  contact_reference: string | null;
  verification_note: string | null;
}

export interface ContractorPatchInput {
  display_name?: string;
  trades?: Trade[];
  service_postcodes?: string[];
  contact_reference?: string | null;
  verification_note?: string | null;
  approval_status?: ContractorApprovalStatus;
}

async function createContractor(
  creds: OperatorCredentials,
  body: ContractorCreateInput,
): Promise<ContractorListItem> {
  const raw = await request<Record<string, unknown>>(creds, "/api/v1/contractors", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return normalizeContractorListItem(raw);
}

async function patchContractor(
  creds: OperatorCredentials,
  id: string,
  body: ContractorPatchInput,
): Promise<ContractorListItem> {
  const raw = await request<Record<string, unknown>>(creds, `/api/v1/contractors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return normalizeContractorListItem(raw);
}

export const contractorsQueryKey = (params: ContractorListParams) =>
  ["contractors", params] as const;
export const contractorQueryKey = (id: string) => ["contractor", id] as const;

export function useContractors(params: ContractorListParams) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: contractorsQueryKey(params),
    queryFn: () => listContractors(creds, params),
    placeholderData: keepPreviousData,
  });
}

export function useContractor(id: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: contractorQueryKey(id ?? ""),
    queryFn: () => getContractor(creds, id!),
    enabled: id !== null,
    retry: (failureCount, error) =>
      error instanceof ApiError && error.status === 404 ? false : failureCount < 2,
  });
}

function useInvalidateContractors() {
  const queryClient = useQueryClient();
  return (id?: string) => {
    void queryClient.invalidateQueries({ queryKey: ["contractors"] });
    if (id) void queryClient.invalidateQueries({ queryKey: contractorQueryKey(id) });
  };
}

export function useCreateContractor() {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateContractors();
  return useMutation({
    mutationFn: (body: ContractorCreateInput) => createContractor(creds, body),
    onSuccess: () => {
      invalidate();
      toast.success("Contractor added -- pending verification before it can be assigned");
    },
  });
}

export function useUpdateContractor(id: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateContractors();
  return useMutation({
    mutationFn: (body: ContractorPatchInput) => patchContractor(creds, id, body),
    onSuccess: () => {
      invalidate(id);
      toast.success("Contractor updated");
    },
  });
}

/** Dedicated approve action -- separate mutation from the general edit form
 * so the profile page can show a 409 ("needs a verification note first")
 * inline near the Approve button rather than folded into a generic form
 * error. */
export function useApproveContractor(id: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateContractors();
  return useMutation({
    mutationFn: () => patchContractor(creds, id, { approval_status: "APPROVED" }),
    onSuccess: () => {
      invalidate(id);
      toast.success("Contractor approved");
    },
  });
}

// --------------------------------------------------------------------------
// Tenants
// --------------------------------------------------------------------------

export interface TenantListItem {
  id: string;
  display_name: string;
  property_id: string;
  property_address: string;
  phone_e164: string | null;
  email: string | null;
  preferred_channel: string | null;
  contact_allowed: boolean;
  accessibility_notes: string | null;
  open_case_count: number;
  total_case_count: number;
  is_archived: boolean;
}

export interface TenantCaseItem {
  id: string;
  case_number: number | null;
  title: string;
  status: string;
  /** TenantCaseSummary (tenants.py) has no per-case updated_at -- created_at
   * is the honest field here. */
  created_at: string | null;
}

export interface TenantProfile extends TenantListItem {
  property_postcode: string | null;
  cases: TenantCaseItem[];
}

function normalizeTenantListItem(raw: unknown): TenantListItem {
  const r = (raw ?? {}) as Record<string, unknown>;
  return {
    id: asString(r["id"]) ?? "",
    display_name: asString(r["display_name"]) ?? "Unnamed tenant",
    property_id: asString(r["property_id"]) ?? "",
    property_address: asString(r["property_address"]) ?? "—",
    phone_e164: asString(r["phone_e164"]),
    email: asString(r["email"]),
    preferred_channel: asString(r["preferred_channel"]),
    contact_allowed: Boolean(r["contact_allowed"]),
    accessibility_notes: asString(r["accessibility_notes"]),
    open_case_count: asNumber(r["open_case_count"]),
    total_case_count: asNumber(r["total_case_count"]),
    is_archived: Boolean(r["is_archived"]),
  };
}

/** Tenant detail bundles a nested property summary and case list whose
 * exact key names aren't pinned down by the contract ("profile + property
 * summary + cases[]") -- this checks a couple of plausible key spellings
 * for each nested field so a reasonable backend shape still renders,
 * degrading to a dash rather than throwing on the rest. */
function normalizeTenantProfile(raw: unknown): TenantProfile {
  const r = (raw ?? {}) as Record<string, unknown>;
  const property = (r["property"] ?? {}) as Record<string, unknown>;
  const rawCases = Array.isArray(r["cases"]) ? r["cases"] : [];
  return {
    ...normalizeTenantListItem(r),
    property_address: asString(r["property_address"]) ?? asString(property["address_line"]) ?? "—",
    property_postcode: asString(property["postcode"]),
    cases: rawCases.map((c) => {
      const cr = (c ?? {}) as Record<string, unknown>;
      return {
        id: asString(cr["id"]) ?? asString(cr["case_id"]) ?? "",
        case_number: typeof cr["case_number"] === "number" ? cr["case_number"] : null,
        title: asString(cr["title"]) ?? asString(cr["case_title"]) ?? "Untitled case",
        status: asString(cr["status"]) ?? "UNKNOWN",
        created_at: asString(cr["created_at"]),
      };
    }),
  };
}

export interface TenantListParams {
  q?: string | undefined;
  property_id?: string | "ALL" | undefined;
  limit?: number | undefined;
  offset?: number | undefined;
  include_archived?: boolean | undefined;
}

async function listTenants(
  creds: OperatorCredentials,
  params: TenantListParams,
): Promise<DirectoryPage<TenantListItem>> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.property_id && params.property_id !== "ALL") {
    search.set("property_id", params.property_id);
  }
  search.set("limit", String(params.limit ?? 50));
  search.set("offset", String(params.offset ?? 0));
  if (params.include_archived) search.set("include_archived", "true");
  const raw = await request<Record<string, unknown>>(creds, `/api/v1/tenants?${search.toString()}`);
  return {
    items: Array.isArray(raw["items"]) ? raw["items"].map(normalizeTenantListItem) : [],
    total: asNumber(raw["total"]),
    has_more: Boolean(raw["has_more"]),
  };
}

async function getTenant(creds: OperatorCredentials, id: string): Promise<TenantProfile> {
  const raw = await request<Record<string, unknown>>(creds, `/api/v1/tenants/${id}`);
  return normalizeTenantProfile(raw);
}

export interface TenantCreateInput {
  display_name: string;
  property_id: string;
  phone_e164: string | null;
  email: string | null;
  preferred_channel: string;
  contact_allowed: boolean;
  accessibility_notes: string | null;
}

export interface TenantPatchInput {
  display_name?: string;
  property_id?: string;
  phone_e164?: string | null;
  email?: string | null;
  preferred_channel?: string;
  contact_allowed?: boolean;
  accessibility_notes?: string | null;
}

async function createTenant(
  creds: OperatorCredentials,
  body: TenantCreateInput,
): Promise<TenantListItem> {
  const raw = await request<Record<string, unknown>>(creds, "/api/v1/tenants", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return normalizeTenantListItem(raw);
}

async function patchTenant(
  creds: OperatorCredentials,
  id: string,
  body: TenantPatchInput,
): Promise<TenantListItem> {
  const raw = await request<Record<string, unknown>>(creds, `/api/v1/tenants/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return normalizeTenantListItem(raw);
}

export const tenantsQueryKey = (params: TenantListParams) => ["tenants", params] as const;
export const tenantQueryKey = (id: string) => ["tenant", id] as const;

export function useTenants(params: TenantListParams) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: tenantsQueryKey(params),
    queryFn: () => listTenants(creds, params),
    placeholderData: keepPreviousData,
  });
}

export function useTenant(id: string | null) {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: tenantQueryKey(id ?? ""),
    queryFn: () => getTenant(creds, id!),
    enabled: id !== null,
    retry: (failureCount, error) =>
      error instanceof ApiError && error.status === 404 ? false : failureCount < 2,
  });
}

function useInvalidateTenants() {
  const queryClient = useQueryClient();
  return (id?: string) => {
    void queryClient.invalidateQueries({ queryKey: ["tenants"] });
    if (id) void queryClient.invalidateQueries({ queryKey: tenantQueryKey(id) });
  };
}

export function useCreateTenant() {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateTenants();
  return useMutation({
    mutationFn: (body: TenantCreateInput) => createTenant(creds, body),
    onSuccess: () => {
      invalidate();
      toast.success("Tenant added");
    },
  });
}

export function useUpdateTenant(id: string) {
  const creds = useAuthedCreds();
  const invalidate = useInvalidateTenants();
  return useMutation({
    mutationFn: (body: TenantPatchInput) => patchTenant(creds, id, body),
    onSuccess: () => {
      invalidate(id);
      toast.success("Tenant updated");
    },
  });
}

// --------------------------------------------------------------------------
// Properties (picker for the tenant form)
// --------------------------------------------------------------------------

export interface PropertyOption {
  id: string;
  address_line: string;
  postcode: string;
}

function normalizePropertyOption(raw: unknown): PropertyOption {
  const r = (raw ?? {}) as Record<string, unknown>;
  return {
    id: asString(r["id"]) ?? "",
    address_line: asString(r["address_line"]) ?? "Unknown address",
    postcode: asString(r["postcode"]) ?? "",
  };
}

async function listProperties(creds: OperatorCredentials): Promise<PropertyOption[]> {
  const raw = await request<Record<string, unknown>>(creds, "/api/v1/properties?limit=200");
  return Array.isArray(raw["items"]) ? raw["items"].map(normalizePropertyOption) : [];
}

export const propertyOptionsQueryKey = ["properties-directory"] as const;

export function useDirectoryProperties() {
  const creds = useAuthedCreds();
  return useQuery({
    queryKey: propertyOptionsQueryKey,
    queryFn: () => listProperties(creds),
    staleTime: 60_000,
  });
}
