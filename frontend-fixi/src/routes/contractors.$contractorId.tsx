import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronLeft, HardHat } from "lucide-react";
import { useState } from "react";
import { ApiError } from "@/api/client";
import { AppShell, Card, PageContainer } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { ContractorFormDialog } from "@/components/fixi/DirectoryForms";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { Button } from "@/components/ui/button";
import {
  approvalExplanation,
  approvalTone,
  useApproveContractor,
  useContractor,
} from "@/hooks/use-directory";
import { formatDate, formatPence, titleCase } from "@/lib/format";

export const Route = createFileRoute("/contractors/$contractorId")({
  head: () => ({
    meta: [{ title: "Contractor — Fixi" }],
  }),
  component: ContractorProfilePage,
});

function BackLink() {
  return (
    <Link
      to="/contractors"
      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
    >
      <ChevronLeft className="h-3.5 w-3.5" /> Back to contractors
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

function ContractorProfilePage() {
  const { contractorId } = Route.useParams();
  const contractor = useContractor(contractorId);
  const approve = useApproveContractor(contractorId);
  const [approveError, setApproveError] = useState<string | null>(null);

  if (contractor.isLoading) {
    return (
      <AppShell>
        <PageContainer title="Contractor" description="Loading…">
          <BackLink />
          <div className="mt-4">
            <LoadingRows rows={5} />
          </div>
        </PageContainer>
      </AppShell>
    );
  }

  if (contractor.isError) {
    const notFound = contractor.error instanceof ApiError && contractor.error.status === 404;
    return (
      <AppShell>
        <PageContainer title="Contractor">
          <BackLink />
          <ErrorState
            className="mt-4"
            title={notFound ? "Contractor not found" : "This didn't load"}
            detail={
              notFound
                ? "It may have been removed, or the link is out of date."
                : contractor.error.message
            }
            {...(notFound ? {} : { onRetry: () => void contractor.refetch() })}
          />
        </PageContainer>
      </AppShell>
    );
  }

  const c = contractor.data;
  if (!c) return null;
  const hasNote = !!c.verification_note && c.verification_note.trim().length > 0;
  const canApprove = c.approval_status !== "APPROVED";

  async function handleApprove() {
    setApproveError(null);
    try {
      await approve.mutateAsync();
    } catch (err) {
      setApproveError(err instanceof ApiError ? err.message : "Could not approve contractor.");
    }
  }

  return (
    <AppShell>
      <PageContainer
        title={c.display_name}
        description={c.trades.length > 0 ? c.trades.map(titleCase).join(", ") : "No trades on file"}
        actions={
          <div className="flex items-center gap-2">
            <ContractorFormDialog
              mode="edit"
              contractor={c}
              trigger={<Button variant="outline">Edit</Button>}
            />
            {canApprove && (
              <div className="flex flex-col items-end gap-1">
                <Button
                  onClick={() => void handleApprove()}
                  disabled={!hasNote || approve.isPending}
                >
                  {approve.isPending ? "Approving…" : "Approve contractor"}
                </Button>
                {!hasNote && (
                  <span className="text-[10px] text-muted-foreground">
                    Add a verification note before approving
                  </span>
                )}
              </div>
            )}
          </div>
        }
      >
        <BackLink />

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {c.is_archived && <Pill tone="purple">Sample history</Pill>}
          <Pill tone={approvalTone(c.approval_status)}>{titleCase(c.approval_status)}</Pill>
          <span className="text-xs text-muted-foreground">
            {approvalExplanation(c.approval_status)}
          </span>
        </div>
        {approveError && <p className="mt-2 text-xs text-destructive">{approveError}</p>}

        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <Card className="p-4 lg:col-span-1">
            <h2 className="text-sm font-semibold">Details</h2>
            <dl className="mt-3 space-y-3">
              <DetailRow label="Contact reference" value={c.contact_reference ?? "—"} />
              <DetailRow label="Connector" value={c.connector ? titleCase(c.connector) : "—"} />
              <DetailRow
                label="Service postcodes"
                value={c.service_postcodes.length > 0 ? c.service_postcodes.join(", ") : "—"}
              />
              <DetailRow
                label="Verification note"
                value={c.verification_note ?? "Not verified yet"}
              />
              <DetailRow label="Appointments" value={String(c.appointment_count)} />
              <DetailRow
                label="Work orders"
                value={`${c.assigned_work_order_count} assigned · ${c.completed_work_order_count} completed`}
              />
            </dl>
          </Card>

          <Card className="overflow-x-auto lg:col-span-2">
            <div className="p-4 pb-0">
              <h2 className="text-sm font-semibold">Work history</h2>
            </div>
            <table className="mt-2 w-full min-w-[640px] text-[12px]">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">Case</th>
                  <th className="px-4 py-2.5 font-medium">Trade</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Scope</th>
                  <th className="px-4 py-2.5 font-medium">Quoted</th>
                  <th className="px-4 py-2.5 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {c.work_history.length === 0 && (
                  <tr>
                    <td colSpan={6} className="p-4">
                      <EmptyState
                        icon={HardHat}
                        title="No work history yet"
                        description="This contractor hasn't been assigned to any work orders yet."
                      />
                    </td>
                  </tr>
                )}
                {c.work_history.map((w) => (
                  <tr
                    key={w.work_order_id}
                    className="border-b border-border last:border-0 transition-colors hover:bg-muted/60"
                  >
                    <td className="max-w-[220px] px-4 py-2.5">
                      {w.is_archived ? (
                        <div>
                          <div className="truncate font-medium" title={w.case_title}>
                            {w.case_title}
                          </div>
                          <Pill tone="purple" className="mt-1">
                            Sample history
                          </Pill>
                        </div>
                      ) : (
                        <Link
                          to="/maintenance/tickets/$ticketId/{-$section}"
                          params={{ ticketId: w.case_id, section: undefined }}
                          className="block truncate font-medium hover:underline"
                          title={w.case_title}
                        >
                          {w.case_number ? `#${w.case_number} — ` : ""}
                          {w.case_title}
                        </Link>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {w.trade ? titleCase(w.trade) : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{titleCase(w.status)}</td>
                    <td
                      className="max-w-[200px] truncate px-4 py-2.5 text-muted-foreground"
                      title={w.scope}
                    >
                      {w.scope || "—"}
                    </td>
                    <td className="px-4 py-2.5 font-medium">{formatPence(w.quote_pence) ?? "—"}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {formatDate(w.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </PageContainer>
    </AppShell>
  );
}
