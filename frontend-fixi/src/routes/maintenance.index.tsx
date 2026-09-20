import * as Dialog from "@radix-ui/react-dialog";
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
import { Button } from "@/components/ui/button";
import { useCancelCase } from "@/hooks/use-case-actions";
import { useCaseList } from "@/hooks/use-case-list";
import { useDashboardMetrics } from "@/hooks/use-dashboard-metrics";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { usePropertyOptions } from "@/hooks/use-new-ticket";
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
  const properties = usePropertyOptions();
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
              options={(properties.data?.items ?? []).map((p) => ({
                value: p.id,
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
                      <RowActions
                        caseId={t.id}
                        caseNumber={t.case_number}
                        status={t.status}
                        version={t.version}
                      />
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

/** Row-level "…" menu.
 *
 * Offers only the actions the legal transition graph permits from this
 * row's status. Hard delete is deliberately absent: it existed to reset a
 * rehearsed demo, and permanently destroying a case -- with its events,
 * calls and work orders -- is not something a list row should offer.
 * Cancel closes a case without a repair outcome and keeps the record.
 *
 * Each row needs its own mutation instance (they are keyed on caseId), so
 * this is a component rather than inline JSX inside the .map().
 */
function RowActions({
  caseId,
  caseNumber,
  status,
  version,
}: {
  caseId: string;
  caseNumber: number;
  status: CaseStatus;
  version: number;
}) {
  const cancel = useCancelCase(caseId);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const canCancel =
    status === "ACTIVE" || status === "AWAITING_CONFIRMATION" || status === "ESCALATED";

  async function submit() {
    if (!reason.trim()) return;
    setError(null);
    try {
      await cancel.mutateAsync({ version, reason: reason.trim() });
      setOpen(false);
      setReason("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "That case could not be cancelled.");
    }
  }

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            aria-label={`Actions for ticket #${caseNumber}`}
            disabled={cancel.isPending}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent disabled:opacity-50"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            className="z-50 min-w-[180px] rounded-lg border border-border bg-card p-1 shadow-panel"
          >
            <DropdownMenu.Item asChild>
              <Link
                to="/maintenance/tickets/$ticketId/{-$section}"
                params={{ ticketId: caseId, section: undefined }}
                className="block cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium outline-none hover:bg-accent data-[highlighted]:bg-accent"
              >
                Open ticket
              </Link>
            </DropdownMenu.Item>
            <DropdownMenu.Item asChild>
              <Link
                to="/messages/$caseId"
                params={{ caseId }}
                className="block cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium outline-none hover:bg-accent data-[highlighted]:bg-accent"
              >
                Open conversation
              </Link>
            </DropdownMenu.Item>
            {canCancel ? (
              <DropdownMenu.Item
                onSelect={() => {
                  setError(null);
                  setOpen(true);
                }}
                className="cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium text-destructive outline-none hover:bg-destructive/10 data-[highlighted]:bg-destructive/10"
              >
                Cancel case
              </DropdownMenu.Item>
            ) : (
              <div className="px-2.5 py-1.5 text-[11px] text-muted-foreground">
                This case is {STATUS_LABEL[status].toLowerCase()} — it cannot be cancelled.
              </div>
            )}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/25 backdrop-blur-[1px]" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(26rem,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-5 shadow-panel">
            <Dialog.Title className="text-sm font-semibold">Cancel ticket #{caseNumber}</Dialog.Title>
            <Dialog.Description className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Closes the case without a repair outcome. The case and its history stay readable —
              nothing is deleted.
            </Dialog.Description>
            <label className="mt-4 block">
              <span className="text-xs font-medium">
                Reason<span className="text-destructive"> *</span>
              </span>
              <textarea
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Recorded on the case timeline."
                className="mt-1 w-full resize-y rounded-lg border border-border bg-background px-2.5 py-2 text-xs outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <Dialog.Close asChild>
                <Button variant="ghost" size="sm" disabled={cancel.isPending}>
                  Keep open
                </Button>
              </Dialog.Close>
              <Button
                size="sm"
                variant="destructive"
                disabled={cancel.isPending || !reason.trim()}
                title={reason.trim() ? undefined : "A reason is required"}
                onClick={() => void submit()}
              >
                {cancel.isPending ? "Cancelling…" : "Cancel case"}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
