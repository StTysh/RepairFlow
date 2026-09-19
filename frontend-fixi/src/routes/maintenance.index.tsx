import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronDown, MoreHorizontal, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { StatusBadge, UrgencyBadge } from "@/components/fixi/Badge";
import { NewTicketDialog } from "@/components/fixi/NewTicketDialog";
import { useCancelCase, useDeleteCase } from "@/hooks/use-case-actions";
import { useCaseList } from "@/hooks/use-case-list";
import { useDashboardMetrics } from "@/hooks/use-dashboard-metrics";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import {
  CASE_STATUSES,
  STATUS_LABEL,
  URGENCIES,
  URGENCY_LABEL,
  type CaseStatus,
  type Urgency,
} from "@/lib/fixi-data";
import { formatRelative } from "@/lib/format";
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

function MaintenancePage() {
  const [statusFilter, setStatusFilter] = useState<CaseStatus | "ALL">("ALL");
  const [urgencyFilter, setUrgencyFilter] = useState<Urgency | "ALL">("ALL");
  const [search, setSearch] = useState("");

  const debouncedSearch = useDebouncedValue(search, 300);

  const metrics = useDashboardMetrics();
  const cases = useCaseList({
    status: statusFilter === "ALL" ? undefined : statusFilter,
    q: debouncedSearch.trim() || undefined,
  });

  const items = useMemo(() => {
    const all = cases.data?.items ?? [];
    if (urgencyFilter === "ALL") return all;
    return all.filter((c) => c.urgency === urgencyFilter);
  }, [cases.data, urgencyFilter]);

  const kpis = metrics.data
    ? [
        { value: String(metrics.data.total), label: "Total tickets" },
        { value: String(metrics.data.active), label: "Active" },
        { value: String(metrics.data.awaiting_confirmation), label: "Awaiting confirmation" },
        { value: String(metrics.data.escalated), label: "Escalated" },
        { value: String(metrics.data.resolved_this_week), label: "Resolved this week" },
      ]
    : [];

  return (
    <AppShell>
      <div className="px-8 py-6">
        <header className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Maintenance</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              All property issues, from report to resolution.
            </p>
          </div>
          <div className="flex items-center gap-2.5">
            <label className="flex h-9 w-72 items-center gap-2 rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground shadow-card">
              <Search className="h-4 w-4" />
              <input
                className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
                placeholder="Search tickets, addresses, tenants..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <NewTicketDialog />
          </div>
        </header>

        <section className="mt-6 grid grid-cols-2 gap-3 xl:grid-cols-5">
          {(kpis.length > 0 ? kpis : Array.from({ length: 5 }, () => null)).map((k, i) => (
            <Card key={k?.label ?? i} className="px-4 py-3.5">
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold tracking-tight">{k?.value ?? "—"}</span>
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">{k?.label ?? "Loading…"}</div>
            </Card>
          ))}
        </section>

        <section className="mt-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-1.5">
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
          <div className="flex items-center gap-2">
            <UrgencyDropdown value={urgencyFilter} onChange={setUrgencyFilter} />
          </div>
        </section>

        <Card className="mt-4 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-2.5 font-medium">#</th>
                <th className="px-4 py-2.5 font-medium">Issue</th>
                <th className="px-4 py-2.5 font-medium">Address</th>
                <th className="px-4 py-2.5 font-medium">Urgency</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Assigned to</th>
                <th className="px-4 py-2.5 font-medium">Updated ↓</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {cases.isLoading && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-xs text-muted-foreground">
                    Loading tickets…
                  </td>
                </tr>
              )}
              {cases.isError && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-xs text-destructive">
                    Could not load tickets. Is the backend running?
                  </td>
                </tr>
              )}
              {!cases.isLoading && !cases.isError && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-xs text-muted-foreground">
                    No tickets match the current filters.
                  </td>
                </tr>
              )}
              {items.map((t) => (
                <tr
                  key={t.id}
                  className="group border-b border-border last:border-0 transition-colors hover:bg-muted/60"
                >
                  <td className="px-4 py-3 text-muted-foreground">
                    <Link
                      to="/maintenance/tickets/$ticketId/{-$section}"
                      params={{ ticketId: t.id, section: undefined }}
                      className="block"
                    >
                      #{t.case_number}
                    </Link>
                  </td>
                  <td className="max-w-xs px-4 py-3 font-medium">
                    <Link
                      to="/maintenance/tickets/$ticketId/{-$section}"
                      params={{ ticketId: t.id, section: undefined }}
                      className="block truncate hover:underline"
                      title={t.title}
                    >
                      {t.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{t.property_address}</td>
                  <td className="px-4 py-3">
                    <UrgencyBadge urgency={t.urgency} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={t.status} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {t.assigned_contractor_name ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatRelative(t.updated_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <RowActions caseId={t.id} status={t.status} version={t.version} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
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

function UrgencyDropdown({
  value,
  onChange,
}: {
  value: Urgency | "ALL";
  onChange: (v: Urgency | "ALL") => void;
}) {
  return (
    <label className="flex h-8 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-medium text-foreground hover:bg-accent">
      {/* appearance-none drops the browser's own arrow so only the
       * ChevronDown below renders -- without it the native select arrow
       * and this icon would both show. */}
      <select
        className="appearance-none bg-transparent outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value as Urgency | "ALL")}
      >
        <option value="ALL">All urgencies</option>
        {URGENCIES.map((u) => (
          <option key={u} value={u}>
            {URGENCY_LABEL[u]}
          </option>
        ))}
      </select>
      <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
    </label>
  );
}
