import { createFileRoute, Link, useRouterState } from "@tanstack/react-router";
import { ChevronDown, ChevronRight, Plus, Search, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell, Card, PageContainer } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { TenantFormDialog } from "@/components/fixi/DirectoryForms";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { Button } from "@/components/ui/button";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useDirectoryProperties, useTenants } from "@/hooks/use-directory";
import { titleCase } from "@/lib/format";
import { readParam } from "@/lib/search-params";

// Same URL-as-state approach as contractors.index.tsx: read the reactive
// search string off the router (useRouterState), no zod `validateSearch`
// (see properties.$propertyId.history.tsx for why that's avoided app-wide).
export const Route = createFileRoute("/tenants/")({
  head: () => ({
    meta: [
      { title: "Tenants — Fixi" },
      { name: "description", content: "Every tenant across this portfolio and their cases." },
    ],
  }),
  component: TenantsPage,
});

function TenantsPage() {
  const searchStr = useRouterState({ select: (s) => s.location.searchStr });
  const navigate = Route.useNavigate();
  const urlParams = useMemo(() => new URLSearchParams(searchStr), [searchStr]);

  const qParam = readParam(urlParams, "q") ?? "";
  const propertyParam = readParam(urlParams, "property_id") ?? "ALL";

  const [searchInput, setSearchInput] = useState(qParam);
  const debouncedSearch = useDebouncedValue(searchInput, 300);
  const properties = useDirectoryProperties();

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

  useEffect(() => {
    setSearchInput(qParam);
  }, [qParam]);

  useEffect(() => {
    if (debouncedSearch === qParam) return;
    updateUrl({ q: debouncedSearch || undefined }, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const tenants = useTenants({
    q: qParam || undefined,
    property_id: propertyParam,
    limit: 50,
  });

  const items = tenants.data?.items ?? [];
  const hasFilters = qParam.length > 0 || propertyParam !== "ALL";

  return (
    <AppShell>
      <PageContainer
        title="Tenants"
        description="Everyone renting across this portfolio, their contact preferences and open cases."
        actions={
          <TenantFormDialog
            mode="create"
            trigger={
              <Button>
                <Plus /> New tenant
              </Button>
            }
          />
        }
      >
        <section className="flex flex-wrap items-center gap-2">
          <label className="flex h-9 w-[280px] max-w-full items-center gap-2 rounded-xl border border-border bg-card px-3 text-muted-foreground shadow-card">
            <Search className="h-4 w-4 shrink-0" />
            <input
              aria-label="Search tenants"
              className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
              placeholder="Search by name..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </label>
          <label className="flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-medium text-foreground hover:bg-accent">
            <select
              className="max-w-[200px] truncate appearance-none bg-transparent outline-none"
              value={propertyParam}
              onChange={(e) => updateUrl({ property_id: e.target.value })}
            >
              <option value="ALL">All properties</option>
              {(properties.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.address_line}
                </option>
              ))}
            </select>
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          </label>
        </section>

        <Card className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[860px] text-[12px]">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="w-11 px-2 py-2" />
                <th className="px-2 py-2 font-medium">Tenant</th>
                <th className="px-2 py-2 font-medium">Property</th>
                <th className="px-2 py-2 font-medium">Preferred channel</th>
                <th className="px-2 py-2 font-medium">Contact allowed</th>
                <th className="px-2 py-2 font-medium">Open cases</th>
                <th className="px-2 py-2 font-medium">Total cases</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {tenants.isLoading && (
                <tr>
                  <td colSpan={8} className="p-4">
                    <LoadingRows rows={5} />
                  </td>
                </tr>
              )}
              {tenants.isError && (
                <tr>
                  <td colSpan={8} className="p-4">
                    <ErrorState
                      detail={errorMessage(tenants.error)}
                      onRetry={() => void tenants.refetch()}
                    />
                  </td>
                </tr>
              )}
              {!tenants.isLoading && !tenants.isError && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-4">
                    <EmptyState
                      icon={Users}
                      title={hasFilters ? "No tenants match these filters" : "No tenants yet"}
                      description={
                        hasFilters
                          ? "Try a different search term or property."
                          : "Add your first tenant to start tracking their cases."
                      }
                      action={
                        !hasFilters ? (
                          <TenantFormDialog
                            mode="create"
                            trigger={<Button size="sm">Add your first tenant</Button>}
                          />
                        ) : undefined
                      }
                    />
                  </td>
                </tr>
              )}
              {items.map((t) => (
                <tr
                  key={t.id}
                  className="group border-b border-border last:border-0 transition-colors hover:bg-muted/60"
                >
                  <td className="px-2 py-1.5">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-status-purple text-[11px] font-semibold text-status-purple-foreground">
                      {t.display_name
                        .trim()
                        .split(/\s+/)
                        .slice(0, 2)
                        .map((p) => p[0])
                        .join("")
                        .toUpperCase() || "?"}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <Link
                      to="/tenants/$tenantId"
                      params={{ tenantId: t.id }}
                      className="block font-medium hover:underline"
                    >
                      {t.display_name}
                    </Link>
                    {t.is_archived && (
                      <Pill tone="purple" className="mt-0.5">
                        Sample history
                      </Pill>
                    )}
                  </td>
                  <td className="max-w-[200px] truncate px-2 py-2 text-muted-foreground">
                    {t.property_address}
                  </td>
                  <td className="px-2 py-2 text-muted-foreground">
                    {t.preferred_channel ? titleCase(t.preferred_channel) : "—"}
                  </td>
                  <td className="px-2 py-2">
                    <Pill tone={t.contact_allowed ? "green" : "red"}>
                      {t.contact_allowed ? "Allowed" : "Not allowed"}
                    </Pill>
                  </td>
                  <td className="px-2 py-2 text-muted-foreground">{t.open_case_count}</td>
                  <td className="px-2 py-2 text-muted-foreground">{t.total_case_count}</td>
                  <td className="px-2 py-2 text-right">
                    <Link
                      to="/tenants/$tenantId"
                      params={{ tenantId: t.id }}
                      aria-label={`View ${t.display_name}`}
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
        {tenants.data && tenants.data.has_more && (
          <p className="mt-2 text-xs text-muted-foreground">
            Showing {items.length} of {tenants.data.total} — refine your search to narrow the list.
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
