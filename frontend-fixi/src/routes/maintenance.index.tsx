import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  AlertTriangle,
  BarChart3,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  FileText,
  MessageCircle,
  MoreHorizontal,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import houseExterior from "@/assets/house-exterior.jpg";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { StatusBadge, UrgencyBadge } from "@/components/fixi/Badge";
import { useCancelCase, useDeleteCase } from "@/hooks/use-case-actions";
import { useCaseList } from "@/hooks/use-case-list";
import { useDashboardMetrics } from "@/hooks/use-dashboard-metrics";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useSeedRefs } from "@/hooks/use-new-ticket";
import { useUpcomingAppointments } from "@/hooks/use-upcoming-appointments";
import { useCaseSearch } from "@/lib/case-search-context";
import {
  CASE_STATUSES,
  STATUS_LABEL,
  URGENCIES,
  URGENCY_LABEL,
  type CaseStatus,
  type Urgency,
} from "@/lib/fixi-data";
import { formatDateRange, formatDeltaPct, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/maintenance/")({
  head: () => ({
    meta: [
      { title: "Maintenance — Fixi" },
      {
        name: "description",
        content:
          "All property issues, from report to resolution. Track open, in-progress and resolved maintenance tickets.",
      },
      { property: "og:title", content: "Maintenance — Fixi" },
      { property: "og:description", content: "All property issues, from report to resolution." },
    ],
  }),
  component: MaintenancePage,
});

const statusFilters: Array<{ label: string; value: CaseStatus | "ALL" }> = [
  { label: "All", value: "ALL" },
  ...CASE_STATUSES.map((s) => ({ label: STATUS_LABEL[s], value: s })),
];

const KPI_TONE_CLASS = {
  red: "bg-status-red text-status-red-foreground",
  blue: "bg-status-blue text-status-blue-foreground",
  amber: "bg-status-amber text-status-amber-foreground",
  green: "bg-status-green text-status-green-foreground",
  gray: "bg-status-gray text-status-gray-foreground",
} as const;

type KpiTone = keyof typeof KPI_TONE_CLASS;

interface KpiCardDef {
  key: string;
  value: string;
  label: string;
  tone: KpiTone;
  Icon: LucideIcon;
  /** Pre-formatted "↑12%" or null -- null means the backend had nothing
   * honest to compare against (or this metric has no delta field at all),
   * and MUST render no arrow rather than a fabricated one. */
  delta: string | null;
}

function MaintenancePage() {
  const [statusFilter, setStatusFilter] = useState<CaseStatus | "ALL">("ALL");
  const [urgencyFilter, setUrgencyFilter] = useState<Urgency | "ALL">("ALL");
  const [propertyFilter, setPropertyFilter] = useState<string | "ALL">("ALL");
  const [contractorFilter, setContractorFilter] = useState<string | "ALL">("ALL");

  // Global search box lives in UtilityBar (rendered once, inside AppShell,
  // above every page) -- its value comes through CaseSearchContext rather
  // than local state so it can be set from outside this component.
  const { search } = useCaseSearch();
  const debouncedSearch = useDebouncedValue(search, 300);

  const metrics = useDashboardMetrics();
  const seedRefs = useSeedRefs();
  const upcoming = useUpcomingAppointments();
  const cases = useCaseList({
    status: statusFilter === "ALL" ? undefined : statusFilter,
    property_id: propertyFilter === "ALL" ? undefined : propertyFilter,
    q: debouncedSearch.trim() || undefined,
  });

  // Contractor filter has no honest server-side id to filter on: the case
  // list only carries assigned_contractor_name (no id), and the demo seed
  // refs only expose two specific contractor ids (roofer_id/scaffolder_id),
  // not a full roster -- there are >=3 seeded contractors. Rather than
  // build a filter that's silently wrong for the contractor(s) missing an
  // id, this filters client-side by name over whatever's on the current
  // page of results (same honesty tradeoff docs/26 would want recorded).
  const contractorOptions = useMemo(() => {
    const names = new Set<string>();
    for (const c of cases.data?.items ?? []) {
      if (c.assigned_contractor_name) names.add(c.assigned_contractor_name);
    }
    // Keep the active selection in the list even if a status/property
    // change makes it disappear from the current page -- otherwise the
    // <select> would show a blank value instead of the chosen contractor.
    if (contractorFilter !== "ALL") names.add(contractorFilter);
    return Array.from(names).sort();
  }, [cases.data, contractorFilter]);

  const items = useMemo(() => {
    return (cases.data?.items ?? []).filter((c) => {
      if (urgencyFilter !== "ALL" && c.urgency !== urgencyFilter) return false;
      if (contractorFilter !== "ALL" && c.assigned_contractor_name !== contractorFilter) {
        return false;
      }
      return true;
    });
  }, [cases.data, urgencyFilter, contractorFilter]);

  const kpis: KpiCardDef[] = metrics.data
    ? [
        {
          key: "total",
          value: String(metrics.data.total),
          label: "Total tickets",
          tone: "gray",
          Icon: FileText,
          delta: null,
        },
        {
          key: "active",
          value: String(metrics.data.active),
          label: "Active",
          tone: "blue",
          Icon: Clock3,
          delta: formatDeltaPct(metrics.data.active_delta_pct),
        },
        {
          key: "awaiting_confirmation",
          value: String(metrics.data.awaiting_confirmation),
          label: "Awaiting confirmation",
          tone: "amber",
          Icon: MessageCircle,
          delta: formatDeltaPct(metrics.data.awaiting_confirmation_delta_pct),
        },
        {
          key: "escalated",
          value: String(metrics.data.escalated),
          label: "Escalated",
          tone: "red",
          Icon: AlertTriangle,
          delta: formatDeltaPct(metrics.data.escalated_delta_pct),
        },
        {
          key: "resolved_this_week",
          value: String(metrics.data.resolved_this_week),
          label: "Resolved this week",
          tone: "green",
          Icon: CheckCircle2,
          delta: null,
        },
        {
          key: "avg_resolution_hours",
          value:
            metrics.data.avg_resolution_hours !== null
              ? `${metrics.data.avg_resolution_hours.toFixed(1)}h`
              : "—",
          label: "Avg time to resolve (30d)",
          tone: "gray",
          Icon: BarChart3,
          delta: null,
        },
      ]
    : [];

  // Real CONFIRMED visits across every case, soonest first (backend already
  // sorts); capped here so the sidebar card can't grow unbounded as more
  // demo cases get seeded.
  const visits = (upcoming.data?.items ?? []).slice(0, 5);

  return (
    <AppShell>
      <div className="mx-auto max-w-[1510px] px-6 py-4 xl:px-7">
        <header>
          <h1 className="text-2xl font-bold tracking-tight">Maintenance</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            All property issues, from report to resolution.
          </p>
        </header>

        <section className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {(kpis.length > 0 ? kpis : Array.from({ length: 6 }, () => null)).map((k, i) => (
            <Card key={k?.key ?? i} className="flex min-h-[92px] items-center gap-3 px-3.5 py-3">
              <span
                className={cn(
                  "flex h-11 w-11 shrink-0 items-center justify-center rounded-full",
                  k ? KPI_TONE_CLASS[k.tone] : "bg-muted text-muted-foreground",
                )}
              >
                {k ? <k.Icon className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
              </span>
              <div className="min-w-0">
                <div className="text-xl font-bold tracking-tight">{k?.value ?? "—"}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {k?.label ?? "Loading…"}
                </div>
                {k?.delta && (
                  <div
                    className={cn(
                      "mt-1.5 text-[10px] font-semibold",
                      k.tone === "red" ? "text-destructive" : "text-primary",
                    )}
                  >
                    {k.delta}
                    <span className="ml-1 font-normal text-muted-foreground">vs 7 days ago</span>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </section>

        <section className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {statusFilters.map((f) => (
              <button
                key={f.value}
                onClick={() => setStatusFilter(f.value)}
                className={cn(
                  "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
                  statusFilter === f.value
                    ? "border-foreground bg-foreground text-background"
                    : "border-border bg-card text-foreground hover:bg-accent",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <FilterDropdown
              value={urgencyFilter}
              onChange={setUrgencyFilter}
              allLabel="All urgencies"
              options={URGENCIES.map((u) => ({ value: u, label: URGENCY_LABEL[u] }))}
            />
            <FilterDropdown
              value={propertyFilter}
              onChange={setPropertyFilter}
              allLabel="All properties"
              options={(seedRefs.data?.properties ?? []).map((p) => ({
                value: p.property_id,
                label: p.address_line,
              }))}
            />
            <FilterDropdown
              value={contractorFilter}
              onChange={setContractorFilter}
              allLabel="All contractors"
              options={contractorOptions.map((name) => ({ value: name, label: name }))}
            />
          </div>
        </section>

        <div className="mt-4 grid items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_270px]">
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-[12px]">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="w-11 px-2 py-2" />
                  <th className="px-2 py-2 font-medium">#</th>
                  <th className="px-2 py-2 font-medium">Issue</th>
                  <th className="px-2 py-2 font-medium">Address</th>
                  <th className="px-2 py-2 font-medium">Urgency</th>
                  <th className="px-2 py-2 font-medium">Status</th>
                  <th className="px-2 py-2 font-medium">Assigned to</th>
                  <th className="px-2 py-2 font-medium">Updated ↓</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {cases.isLoading && (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-xs text-muted-foreground">
                      Loading tickets…
                    </td>
                  </tr>
                )}
                {cases.isError && (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-xs text-destructive">
                      Could not load tickets. Is the backend running?
                    </td>
                  </tr>
                )}
                {!cases.isLoading && !cases.isError && items.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-xs text-muted-foreground">
                      No tickets match the current filters.
                    </td>
                  </tr>
                )}
                {items.map((t) => (
                  <tr
                    key={t.id}
                    className="group border-b border-border last:border-0 transition-colors hover:bg-muted/60"
                  >
                    <td className="px-2 py-1.5">
                      {/* No property-photo field on the backend -- a
                       * neutral placeholder icon, not a fabricated photo
                       * per property. */}
                      <span className="flex h-8 w-8 items-center justify-center rounded-md bg-muted text-muted-foreground">
                        <Building2 className="h-4 w-4" />
                      </span>
                    </td>
                    <td className="px-2 py-2 text-muted-foreground">
                      <Link
                        to="/maintenance/tickets/$ticketId/{-$section}"
                        params={{ ticketId: t.id, section: undefined }}
                        className="block"
                      >
                        #{t.case_number}
                      </Link>
                    </td>
                    <td className="max-w-xs px-2 py-2 font-medium">
                      <Link
                        to="/maintenance/tickets/$ticketId/{-$section}"
                        params={{ ticketId: t.id, section: undefined }}
                        className="block truncate hover:underline"
                        title={t.title}
                      >
                        {t.title}
                      </Link>
                    </td>
                    <td className="px-2 py-2 text-muted-foreground">{t.property_address}</td>
                    <td className="px-2 py-2">
                      <UrgencyBadge urgency={t.urgency} />
                    </td>
                    <td className="px-2 py-2">
                      <StatusBadge status={t.status} />
                    </td>
                    <td className="px-2 py-2 text-muted-foreground">
                      {t.assigned_contractor_name ?? "—"}
                    </td>
                    <td className="px-2 py-2 text-muted-foreground">
                      {formatRelative(t.updated_at)}
                    </td>
                    <td className="px-2 py-2 text-right">
                      <RowActions caseId={t.id} status={t.status} version={t.version} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <aside className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-1">
            <Card className="p-3.5">
              <h2 className="text-sm font-semibold">Upcoming visits</h2>
              {upcoming.isLoading && <p className="mt-3 text-xs text-muted-foreground">Loading…</p>}
              {upcoming.isError && (
                <p className="mt-3 text-xs text-destructive">Could not load visits.</p>
              )}
              {!upcoming.isLoading && !upcoming.isError && visits.length === 0 && (
                <p className="mt-3 text-xs text-muted-foreground">No upcoming visits scheduled.</p>
              )}
              <div className="mt-2 divide-y divide-border">
                {visits.map((v) => {
                  const start = new Date(v.start_at);
                  const month = start
                    .toLocaleDateString(undefined, { month: "short" })
                    .toUpperCase();
                  const day = start.toLocaleDateString(undefined, { day: "2-digit" });
                  return (
                    <Link
                      key={v.appointment_id}
                      to="/maintenance/tickets/$ticketId/{-$section}"
                      params={{ ticketId: v.case_id, section: undefined }}
                      className="-mx-1 flex items-center gap-2 rounded-md px-1 py-2 hover:bg-accent/60"
                    >
                      <div className="flex h-12 w-10 shrink-0 flex-col items-center justify-center rounded-lg border border-border bg-muted">
                        <span className="text-[8px] font-semibold">{month}</span>
                        <span className="text-base font-bold">{day}</span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs font-semibold">{v.contractor_name}</div>
                        <div className="truncate text-[10px] text-muted-foreground">
                          {v.property_address}
                        </div>
                        <div className="text-[10px] text-muted-foreground">
                          {formatDateRange(v.start_at, v.end_at).time}
                        </div>
                      </div>
                      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                    </Link>
                  );
                })}
              </div>
            </Card>

            {/* Static marketing tile (not data-backed, deliberately -- see
             * report) linking to the real Properties list. */}
            <div className="relative min-h-36 overflow-hidden rounded-xl shadow-card">
              <img
                src={houseExterior}
                alt=""
                width={912}
                height={736}
                className="absolute inset-0 h-full w-full object-cover"
              />
              <div className="absolute inset-0 bg-foreground/65" />
              <div className="relative flex h-full flex-col justify-end p-4 text-primary-foreground">
                <h2 className="text-base font-semibold">
                  Keep properties
                  <br />
                  in better shape
                </h2>
                <p className="mt-1 text-[10px] opacity-90">
                  Track history, spot recurring
                  <br />
                  issues and plan ahead.
                </p>
                <Link
                  to="/properties"
                  className="mt-3 inline-flex w-fit items-center gap-1 rounded-lg bg-background/90 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-background"
                >
                  View properties <ChevronRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}

/** Row-level "..." menu -- used to be a button with no onClick at all.
 * Wired to the same Cancel/Delete mutations CaseLifecycleActions uses on
 * the ticket detail page (window.confirm/prompt + mutateAsync + the
 * hooks' own onError toast), just reachable without opening the ticket
 * first. Each row needs its own hook instances since they're keyed on
 * caseId, so this has to be a component rather than inline JSX inside
 * the .map(). */
function RowActions({
  caseId,
  status,
  version,
}: {
  caseId: string;
  status: CaseStatus;
  version: number;
}) {
  const cancel = useCancelCase(caseId);
  const deleteTicket = useDeleteCase(caseId);
  const busy = cancel.isPending || deleteTicket.isPending;
  const canCancel =
    status === "ACTIVE" || status === "AWAITING_CONFIRMATION" || status === "ESCALATED";

  async function handleCancel() {
    const reason = window.prompt("Reason for cancelling this case?");
    if (!reason) return;
    try {
      await cancel.mutateAsync({ version, reason });
    } catch {
      // handled by onError toast (see use-case-actions.ts)
    }
  }

  async function handleDelete() {
    if (
      !window.confirm(
        "Permanently delete this ticket? This removes it and everything on it (events, calls, work orders) -- unlike Cancel, this can't be undone.",
      )
    ) {
      return;
    }
    try {
      await deleteTicket.mutateAsync();
    } catch {
      // handled by onError toast
    }
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          disabled={busy}
          className="rounded-md p-1 text-muted-foreground hover:bg-accent disabled:opacity-50"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          className="z-50 min-w-[160px] rounded-lg border border-border bg-card p-1 shadow-panel"
        >
          {canCancel && (
            <DropdownMenu.Item
              onSelect={() => void handleCancel()}
              className="cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium text-destructive outline-none hover:bg-destructive/10"
            >
              Cancel case
            </DropdownMenu.Item>
          )}
          <DropdownMenu.Item
            onSelect={() => void handleDelete()}
            className="cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium text-destructive outline-none hover:bg-destructive/10"
          >
            Delete ticket
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

/** Generic status/urgency/property/contractor filter select, replacing the
 * old one-off UrgencyDropdown now that the filter row has three of these. */
function FilterDropdown<T extends string>({
  value,
  onChange,
  allLabel,
  options,
}: {
  value: T | "ALL";
  onChange: (v: T | "ALL") => void;
  allLabel: string;
  options: Array<{ value: T; label: string }>;
}) {
  return (
    <label className="flex h-8 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-medium text-foreground hover:bg-accent">
      {/* appearance-none drops the browser's own arrow so only the
       * ChevronDown below renders -- without it the native select arrow
       * and this icon would both show. */}
      <select
        className="max-w-[160px] truncate appearance-none bg-transparent outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value as T | "ALL")}
      >
        <option value="ALL">{allLabel}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
    </label>
  );
}
