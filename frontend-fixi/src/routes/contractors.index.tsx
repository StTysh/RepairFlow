import { createFileRoute, Link, useRouterState } from "@tanstack/react-router";
import { ChevronDown, ChevronRight, HardHat, Plus, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell, Card, PageContainer } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { ContractorFormDialog } from "@/components/fixi/DirectoryForms";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { Button } from "@/components/ui/button";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import {
  CONTRACTOR_APPROVAL_STATUSES,
  TRADES,
  approvalTone,
  useContractors,
  type ContractorApprovalStatus,
  type Trade,
} from "@/hooks/use-directory";
import { titleCase } from "@/lib/format";
import { readFlag, readParam } from "@/lib/search-params";

// No zod `validateSearch` here -- see properties.$propertyId.history.tsx for
// why: it reproducibly froze the renderer against this app's SPA-fallback
// hydration. Filters are instead read straight off the router's reactive
// search string (useRouterState, same primitive AppShell.tsx already uses
// for the active nav highlight) and written back with useNavigate, so the
// URL stays linkable and survives back/forward without going through a
// validated search schema.
export const Route = createFileRoute("/contractors/")({
  head: () => ({
    meta: [
      { title: "Contractors — Fixi" },
      { name: "description", content: "Your roster of researched and approved contractors." },
    ],
  }),
  component: ContractorsPage,
});

function ContractorsPage() {
  const searchStr = useRouterState({ select: (s) => s.location.searchStr });
  const navigate = Route.useNavigate();
  const urlParams = useMemo(() => new URLSearchParams(searchStr), [searchStr]);

  const qParam = readParam(urlParams, "q") ?? "";
  const tradeParam = (readParam(urlParams, "trade") as Trade | undefined) ?? "ALL";
  const approvalParam =
    (readParam(urlParams, "approval_status") as ContractorApprovalStatus | undefined) ?? "ALL";
  const includeArchived = readFlag(urlParams, "archived");

  const [searchInput, setSearchInput] = useState(qParam);
  const debouncedSearch = useDebouncedValue(searchInput, 300);

  // `replace` defaults to false (push) so a filter change is a real,
  // back-navigable step -- the debounced search-box write below is the one
  // exception, using `replace: true` so every keystroke's settled value
  // doesn't spam a fresh history entry per pause.
  function updateUrl(patch: Record<string, string | undefined>, options?: { replace?: boolean }) {
    const next = new URLSearchParams(searchStr);
    for (const [k, v] of Object.entries(patch)) {
      if (!v || v === "ALL") next.delete(k);
      else next.set(k, v);
    }
    const nextSearch: Record<string, string> = {};
    next.forEach((v, k) => {
      nextSearch[k] = v;
    });
    navigate({ search: nextSearch, replace: options?.replace ?? false });
  }

  // Keep the input in sync when the URL changes from outside typing (back/
  // forward, a bookmarked link) -- a no-op when the change was caused by
  // our own debounced write below, since debouncedSearch already matches.
  useEffect(() => {
    setSearchInput(qParam);
  }, [qParam]);

  useEffect(() => {
    if (debouncedSearch === qParam) return;
    updateUrl({ q: debouncedSearch || undefined }, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const contractors = useContractors({
    q: qParam || undefined,
    trade: tradeParam,
    approval_status: approvalParam,
    include_archived: includeArchived,
    limit: 50,
  });

  const items = contractors.data?.items ?? [];
  const hasFilters =
    qParam.length > 0 || tradeParam !== "ALL" || approvalParam !== "ALL" || includeArchived;

  return (
    <AppShell>
      <PageContainer
        title="Contractors"
        description="Only Approved contractors can be assigned to work orders. Pending contractors are unverified research candidates found via web search."
        actions={
          <ContractorFormDialog
            mode="create"
            trigger={
              <Button>
                <Plus /> New contractor
              </Button>
            }
          />
        }
      >
        <section className="flex flex-wrap items-center gap-2">
          <label className="flex h-9 w-[280px] max-w-full items-center gap-2 rounded-xl border border-border bg-card px-3 text-muted-foreground shadow-card">
            <Search className="h-4 w-4 shrink-0" />
            <input
              aria-label="Search contractors"
              className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
              placeholder="Search by name or postcode..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </label>
          <FilterSelect
            label="All trades"
            value={tradeParam}
            onChange={(v) => updateUrl({ trade: v })}
            options={TRADES.map((t) => ({ value: t, label: titleCase(t) }))}
          />
          <FilterSelect
            label="All approval statuses"
            value={approvalParam}
            onChange={(v) => updateUrl({ approval_status: v })}
            options={CONTRACTOR_APPROVAL_STATUSES.map((s) => ({ value: s, label: titleCase(s) }))}
          />
          {/* Archival contractors exist only to give imported historical
           * work orders a named supplier. They are never approved and
           * carry no contact details, so they stay out of the directory
           * unless asked for -- the same opt-in the Properties, Tenants
           * and Insights screens offer. */}
          <label className="flex h-9 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs font-medium text-foreground hover:bg-accent">
            <input
              type="checkbox"
              className="accent-primary"
              checked={includeArchived}
              aria-label="Include archived sample contractors"
              onChange={(e) => updateUrl({ archived: e.target.checked ? "1" : undefined })}
            />
            Include archived
          </label>
        </section>

        <Card className="mt-4 max-w-[1180px] overflow-x-auto">
          {/* Explicit budget + a card cap. Auto layout gave "Contractor"
           * 661px for a ~325px name, leaving ~374px of dead space
           * before "Service area" on every row, while "Assigned" took
           * 133px to hold one digit. Capping the card turns the
           * leftover into margin instead of column padding (docs/27). */}
          <table className="w-full min-w-[820px] table-fixed text-body">
            <colgroup>
              <col className="w-[56px]" />
              <col />
              <col className="w-[220px]" />
              <col className="w-[130px]" />
              <col className="w-[96px]" />
              <col className="w-[96px]" />
              <col className="w-[44px]" />
            </colgroup>
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-3 py-2" />
                <th className="px-3 py-2 font-medium">Contractor</th>
                <th className="px-3 py-2 font-medium">Service area</th>
                <th className="px-3 py-2 font-medium">Approval</th>
                <th className="px-3 py-2 text-right font-medium">Assigned</th>
                <th className="px-3 py-2 text-right font-medium">Completed</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {contractors.isLoading && (
                <tr>
                  <td colSpan={7} className="p-4">
                    <LoadingRows rows={5} />
                  </td>
                </tr>
              )}
              {contractors.isError && (
                <tr>
                  <td colSpan={7} className="p-4">
                    <ErrorState
                      detail={errorMessage(contractors.error)}
                      onRetry={() => void contractors.refetch()}
                    />
                  </td>
                </tr>
              )}
              {!contractors.isLoading && !contractors.isError && items.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-4">
                    <EmptyState
                      icon={HardHat}
                      title={
                        hasFilters ? "No contractors match these filters" : "No contractors yet"
                      }
                      description={
                        hasFilters
                          ? "Try a different search term, trade or approval status."
                          : "Add your first contractor to start building your roster."
                      }
                      action={
                        !hasFilters ? (
                          <ContractorFormDialog
                            mode="create"
                            trigger={<Button size="sm">Add your first contractor</Button>}
                          />
                        ) : undefined
                      }
                    />
                  </td>
                </tr>
              )}
              {items.map((c) => (
                <tr
                  key={c.id}
                  className="group border-b border-border last:border-0 transition-colors hover:bg-muted/60"
                >
                  <td className="px-2 py-1.5">
                    <span className="flex h-8 w-8 items-center justify-center rounded-md bg-muted text-muted-foreground">
                      <HardHat className="h-4 w-4" />
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Link
                      to="/contractors/$contractorId"
                      params={{ contractorId: c.id }}
                      className="block font-medium hover:underline"
                    >
                      {c.display_name}
                    </Link>
                    <div className="mt-0.5 truncate text-micro text-muted-foreground">
                      {c.trades.length > 0
                        ? c.trades.map(titleCase).join(", ")
                        : "No trades on file"}
                    </div>
                  </td>
                  <td className="max-w-[180px] truncate px-2 py-2 text-muted-foreground">
                    {c.service_postcodes.length > 0 ? c.service_postcodes.join(", ") : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <Pill tone={approvalTone(c.approval_status)}>
                      {titleCase(c.approval_status)}
                    </Pill>
                    {c.approval_status !== "APPROVED" && (
                      <div className="mt-0.5 text-micro text-muted-foreground">Not assignable</div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {c.assigned_work_order_count}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {c.completed_work_order_count}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Link
                      to="/contractors/$contractorId"
                      params={{ contractorId: c.id }}
                      aria-label={`View ${c.display_name}`}
                      className="inline-flex rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        {contractors.data && contractors.data.has_more && (
          <p className="mt-2 text-xs text-muted-foreground">
            Showing {items.length} of {contractors.data.total} — refine your search to narrow the
            list.
          </p>
        )}
      </PageContainer>
    </AppShell>
  );
}

/** Avoids `(error as Error).message` -- a rejection isn't guaranteed to be
 * an Error instance (ApiError is one, but a network failure or thrown
 * non-Error value isn't), so this checks rather than assumes. */
function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

/** Same shape as maintenance.index.tsx's FilterDropdown -- kept local rather
 * than shared since each route file here is self-contained, matching that
 * file's own precedent (it doesn't import a shared filter component either). */
function FilterSelect<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: T | "ALL";
  onChange: (v: T | "ALL") => void;
  options: Array<{ value: T; label: string }>;
}) {
  return (
    <label className="flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-medium text-foreground hover:bg-accent">
      <select
        className="max-w-[160px] truncate appearance-none bg-transparent outline-none"
        value={value}
        onChange={(e) => onChange(e.target.value as T | "ALL")}
      >
        <option value="ALL">{label}</option>
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
