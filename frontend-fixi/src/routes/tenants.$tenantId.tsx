import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, MessageSquare, ShieldAlert } from "lucide-react";
import { ApiError } from "@/api/client";
import { AppShell, Card, PageContainer } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { TenantFormDialog } from "@/components/fixi/DirectoryForms";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { Button } from "@/components/ui/button";
import { useTenant } from "@/hooks/use-directory";
import { CASE_STATUSES, STATUS_LABEL, statusTone, type CaseStatus } from "@/lib/fixi-data";
import { formatRelative, titleCase } from "@/lib/format";

export const Route = createFileRoute("/tenants/$tenantId")({
  head: () => ({ meta: [{ title: "Tenant — Fixi" }] }),
  component: TenantProfilePage,
});

function BackLink() {
  return (
    <Link
      to="/tenants"
      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
    >
      <ChevronLeft className="h-3.5 w-3.5" /> Back to tenants
    </Link>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-[13px] font-medium">{value}</dd>
    </div>
  );
}

/** Case status pill that degrades gracefully -- the tenant-detail contract
 * doesn't pin down whether `cases[].status` is guaranteed to be one of the
 * 5 canonical CaseStatus values, so an unrecognized string still renders
 * (titleCased, neutral tone) instead of crashing StatusBadge's strict prop
 * type. */
function CaseStatusPill({ status }: { status: string }) {
  if ((CASE_STATUSES as string[]).includes(status)) {
    const s = status as CaseStatus;
    return <Pill tone={statusTone(s)}>{STATUS_LABEL[s]}</Pill>;
  }
  return <Pill tone="gray">{titleCase(status)}</Pill>;
}

function TenantProfilePage() {
  const { tenantId } = Route.useParams();
  const tenant = useTenant(tenantId);

  if (tenant.isLoading) {
    return (
      <AppShell>
        <PageContainer title="Tenant" description="Loading…">
          <BackLink />
          <div className="mt-4">
            <LoadingRows rows={5} />
          </div>
        </PageContainer>
      </AppShell>
    );
  }

  if (tenant.isError) {
    const notFound = tenant.error instanceof ApiError && tenant.error.status === 404;
    return (
      <AppShell>
        <PageContainer title="Tenant">
          <BackLink />
          <ErrorState
            className="mt-4"
            title={notFound ? "Tenant not found" : "This didn't load"}
            detail={
              notFound
                ? "It may have been removed, or the link is out of date."
                : tenant.error.message
            }
            {...(notFound ? {} : { onRetry: () => void tenant.refetch() })}
          />
        </PageContainer>
      </AppShell>
    );
  }

  const t = tenant.data;
  if (!t) return null;
  // No confirmed way from this endpoint to know whether any of this
  // tenant's cases actually has a message thread -- "has open cases" is
  // the closest honest proxy available, so the link only appears then.
  const hasCases = t.cases.length > 0;

  return (
    <AppShell>
      <PageContainer
        title={t.display_name}
        description={t.property_address}
        actions={
          <div className="flex items-center gap-2">
            {hasCases && (
              // `q` is the Messages screen's real filter parameter (see
              // useThreadListFilters in hooks/use-messaging.ts), and its
              // search spans tenant name, so filtering by name lands on
              // this tenant's threads. There is no tenant-id filter to use
              // instead, and inventing one would produce a link that looks
              // precise and quietly matches nothing.
              <Link
                to="/messages"
                search={{ q: t.display_name }}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3.5 text-sm font-medium shadow-card transition-colors hover:bg-accent"
              >
                <MessageSquare className="h-4 w-4" /> Messages
              </Link>
            )}
            <TenantFormDialog
              mode="edit"
              tenant={t}
              trigger={<Button variant="outline">Edit</Button>}
            />
          </div>
        }
      >
        <BackLink />

        {t.is_archived && (
          <div className="mt-3">
            <Pill tone="purple">Sample history</Pill>
          </div>
        )}

        {!t.contact_allowed && (
          <Card className="mt-3 flex items-start gap-2.5 border-status-red-foreground/25 bg-status-red/40 p-4">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-status-red-foreground" />
            <div>
              <p className="text-sm font-semibold text-status-red-foreground">
                Contact not allowed
              </p>
              <p className="mt-0.5 text-xs text-status-red-foreground/80">
                This tenant has not consented to contact. Do not call, text or email them from this
                app.
              </p>
            </div>
          </Card>
        )}

        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-1">
            <Card className="p-4">
              <h2 className="text-sm font-semibold">Contact details</h2>
              <dl className="mt-3 space-y-3">
                <DetailRow label="Phone" value={t.phone_e164 ?? "—"} />
                <DetailRow label="Email" value={t.email ?? "—"} />
                <DetailRow
                  label="Preferred channel"
                  value={t.preferred_channel ? titleCase(t.preferred_channel) : "—"}
                />
                <DetailRow
                  label="Contact allowed"
                  value={
                    <Pill tone={t.contact_allowed ? "green" : "red"}>
                      {t.contact_allowed ? "Allowed" : "Not allowed"}
                    </Pill>
                  }
                />
                <DetailRow
                  label="Accessibility notes"
                  value={t.accessibility_notes ?? "None recorded"}
                />
              </dl>
            </Card>

            <Link to="/properties/$propertyId/history" params={{ propertyId: t.property_id }}>
              <Card className="p-4 transition-colors hover:bg-accent">
                <h2 className="text-sm font-semibold">Property</h2>
                <p className="mt-2 text-[13px] font-medium">{t.property_address}</p>
                {t.property_postcode && (
                  <p className="text-xs text-muted-foreground">{t.property_postcode}</p>
                )}
                <p className="mt-2 flex items-center gap-1 text-xs text-primary">
                  View property history <ChevronRight className="h-3.5 w-3.5" />
                </p>
              </Card>
            </Link>
          </div>

          <Card className="lg:col-span-2">
            <div className="p-4 pb-0">
              <h2 className="text-sm font-semibold">
                Cases ({t.open_case_count} open, {t.total_case_count} total)
              </h2>
            </div>
            {t.cases.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  icon={MessageSquare}
                  title="No cases yet"
                  description="This tenant has no maintenance cases on record."
                />
              </div>
            ) : (
              <div className="mt-2 divide-y divide-border">
                {t.cases.map((cs) => (
                  <Link
                    key={cs.id}
                    to="/maintenance/tickets/$ticketId/{-$section}"
                    params={{ ticketId: cs.id, section: undefined }}
                    className="flex items-center justify-between gap-3 px-4 py-3 text-[13px] transition-colors hover:bg-muted/60"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium">
                        {cs.case_number ? `#${cs.case_number} — ` : ""}
                        {cs.title}
                      </div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">
                        {/* Both, because they answer different questions:
                         * when the tenant raised it, and whether anything
                         * has happened since. */}
                        Reported {formatRelative(cs.created_at)}
                        {cs.updated_at && cs.updated_at !== cs.created_at
                          ? ` · updated ${formatRelative(cs.updated_at)}`
                          : ""}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <CaseStatusPill status={cs.status} />
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Card>
        </div>
      </PageContainer>
    </AppShell>
  );
}
