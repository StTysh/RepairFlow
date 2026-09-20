import * as Dialog from "@radix-ui/react-dialog";
import { ClipboardPen, X } from "lucide-react";
import { useState } from "react";
import { useSubmitFieldUpdate } from "@/hooks/use-case-actions";
import type { Appointment, WorkOrder } from "@/api/types";
import { Button } from "@/components/ui/button";
import { formatDateRange, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

type Kind = "CONTRACTOR_REPORT" | "TENANT_UPDATE" | "ATTENDANCE_WINDOW_ENDED";

const kindLabel: Record<Kind, string> = {
  CONTRACTOR_REPORT: "Contractor told us",
  TENANT_UPDATE: "Tenant told us",
  ATTENDANCE_WINDOW_ENDED: "Visit window passed",
};

function appointmentLabel(appointment: Appointment, workOrders: WorkOrder[]): string {
  const wo = workOrders.find((w) => w.id === appointment.work_order_id);
  const { date, time } = formatDateRange(appointment.start_at, appointment.end_at);
  const scope = wo ? `${titleCase(wo.trade)} — ${titleCase(wo.kind)}` : "Work order";
  return `${scope} · ${date}, ${time} · ${appointment.status}`;
}

/**
 * Record what a contractor or tenant actually told the operator.
 *
 * POST /api/v1/cases/{case_id}/field-updates. This replaced a demo
 * control that fabricated observations. The form is similar; the claim it
 * makes is not. Every submission names the person who gave the report and
 * is attributed server-side to the authenticated operator, so the case
 * history records second-hand information as second-hand rather than
 * presenting it as something the system observed.
 *
 * It contacts nobody. Recording that a contractor phoned in a finding is
 * a write to this database and nothing more; the tenant and contractor
 * calling paths are separate and deliberate.
 *
 * CONTRACTOR_REPORT and ATTENDANCE_WINDOW_ENDED both require a real
 * appointment already on the case (the API 404s otherwise), so both
 * pickers are built from `appointments` on the snapshot -- never a
 * free-typed id, never a fabricated option. TENANT_UPDATE needs none.
 */
export function RecordFieldUpdateDialog({
  caseId,
  appointments,
  workOrders,
}: {
  caseId: string;
  appointments: Appointment[];
  workOrders: WorkOrder[];
}) {
  const hasAppointments = appointments.length > 0;

  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind>(hasAppointments ? "CONTRACTOR_REPORT" : "TENANT_UPDATE");
  // Nullable operator override rather than an eagerly-initialized default:
  // this dialog stays mounted while the route polls, so `appointments` can
  // go from empty to populated (exactly the hero path, right after the
  // coordinator books the scaffold visit) without the component
  // remounting. Deriving the selected id at render time -- override falling
  // back to the first appointment -- means that transition is never missed
  // the way a one-time useState initializer would miss it.
  const [appointmentIdOverride, setAppointmentIdOverride] = useState<string | null>(null);
  const [text, setText] = useState("");
  // Who actually said it. Required for both narrative kinds: an
  // unattributed report is exactly the thing this form exists to avoid.
  const [reportedBy, setReportedBy] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [confirmsResolved, setConfirmsResolved] = useState(true);
  const submit = useSubmitFieldUpdate(caseId);

  const selectedAppointmentId = appointmentIdOverride ?? appointments[0]?.id ?? null;

  function reset() {
    setKind(appointments.length > 0 ? "CONTRACTOR_REPORT" : "TENANT_UPDATE");
    setAppointmentIdOverride(null);
    setText("");
    setReportedBy("");
    setObservedAt("");
    setConfirmsResolved(true);
  }

  const needsAttribution = kind === "TENANT_UPDATE" || kind === "CONTRACTOR_REPORT";
  const canSubmit =
    !submit.isPending &&
    (!needsAttribution || (text.trim().length >= 4 && reportedBy.trim().length >= 2)) &&
    (kind === "TENANT_UPDATE" || !!selectedAppointmentId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (kind === "CONTRACTOR_REPORT") {
        if (!selectedAppointmentId) return;
        await submit.mutateAsync({
          kind: "CONTRACTOR_REPORT",
          appointment_id: selectedAppointmentId,
          text: text.trim(),
          // Defaults to now, but an operator writing up a call from
          // earlier can say when it actually happened -- the timeline is
          // only useful if it reflects the real sequence of events.
          observed_at: observedAt
            ? new Date(observedAt).toISOString()
            : new Date().toISOString(),
          reported_by: reportedBy.trim(),
        });
      } else if (kind === "TENANT_UPDATE") {
        await submit.mutateAsync({
          kind: "TENANT_UPDATE",
          confirms_resolved: confirmsResolved,
          text: text.trim(),
          reported_by: reportedBy.trim(),
        });
      } else {
        if (!selectedAppointmentId) return;
        await submit.mutateAsync({
          kind: "ATTENDANCE_WINDOW_ENDED",
          appointment_id: selectedAppointmentId,
        });
      }
      reset();
      setOpen(false);
    } catch {
      // handled by onError toast (see use-case-actions.ts); keep the dialog
      // open with the operator's input intact so they can retry.
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <Dialog.Trigger asChild>
        <Button
          variant="outline"
          className="rounded-xl bg-card"
          title="Write up what a contractor or tenant told you. Contacts nobody."
        >
          <ClipboardPen /> Record an update
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/20" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-6 shadow-panel">
          <div className="flex items-start justify-between">
            <div>
              <Dialog.Title className="text-sm font-semibold text-foreground">
                Record an update
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Write up what a contractor or tenant told you. It is recorded
                against the case in your name, attributed to whoever reported
                it. Nobody is contacted.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <form onSubmit={(e) => void handleSubmit(e)}>
            <div className="mt-4 flex gap-1.5">
              {(Object.keys(kindLabel) as Kind[]).map((k) => {
                const disabled = k !== "TENANT_UPDATE" && !hasAppointments;
                return (
                  <button
                    key={k}
                    type="button"
                    disabled={disabled}
                    onClick={() => setKind(k)}
                    className={cn(
                      "h-8 flex-1 rounded-lg border px-1.5 text-[11px] font-medium leading-tight transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                      kind === k
                        ? "border-foreground bg-foreground text-background"
                        : "border-border bg-card text-foreground hover:bg-accent",
                    )}
                  >
                    {kindLabel[k]}
                  </button>
                );
              })}
            </div>
            {!hasAppointments && (
              <p className="mt-2 text-xs text-muted-foreground">
                No booked visit on this case yet, so there is nothing to attach a
                contractor report or a missed-window note to. A tenant update
                needs no appointment.
              </p>
            )}

            {(kind === "CONTRACTOR_REPORT" || kind === "ATTENDANCE_WINDOW_ENDED") && (
              <>
                <label
                  className="mt-4 block text-xs font-medium text-muted-foreground"
                  htmlFor="sim-appointment"
                >
                  Appointment
                </label>
                <select
                  id="sim-appointment"
                  className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                  value={selectedAppointmentId ?? ""}
                  onChange={(e) => setAppointmentIdOverride(e.target.value)}
                  disabled={!hasAppointments}
                >
                  {appointments.map((a) => (
                    <option key={a.id} value={a.id}>
                      {appointmentLabel(a, workOrders)}
                    </option>
                  ))}
                </select>
              </>
            )}

            {kind === "CONTRACTOR_REPORT" && (
              <>
                <label
                  className="mt-3 block text-xs font-medium text-muted-foreground"
                  htmlFor="sim-report-text"
                >
                  What did they find?
                </label>
                <textarea
                  id="sim-report-text"
                  className="mt-1.5 h-24 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="e.g. Roof can't be safely accessed without scaffolding first"
                  autoFocus
                />
              </>
            )}

            {kind === "TENANT_UPDATE" && (
              <>
                <label
                  className="mt-4 block text-xs font-medium text-muted-foreground"
                  htmlFor="sim-feedback-text"
                >
                  What did they say?
                </label>
                <textarea
                  id="sim-feedback-text"
                  className="mt-1.5 h-24 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="e.g. The leak has stopped since the repair"
                  autoFocus
                />
                <div className="mt-3 flex items-center gap-2.5">
                  <span className="text-xs font-medium text-muted-foreground">
                    Tenant confirms resolved?
                  </span>
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => setConfirmsResolved(true)}
                      className={cn(
                        "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
                        confirmsResolved
                          ? "border-foreground bg-foreground text-background"
                          : "border-border bg-card hover:bg-accent",
                      )}
                    >
                      Yes
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmsResolved(false)}
                      className={cn(
                        "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
                        !confirmsResolved
                          ? "border-foreground bg-foreground text-background"
                          : "border-border bg-card hover:bg-accent",
                      )}
                    >
                      No
                    </button>
                  </div>
                </div>
              </>
            )}

            {needsAttribution && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <label
                    className="block text-xs font-medium text-muted-foreground"
                    htmlFor="field-update-reported-by"
                  >
                    Who reported this?
                  </label>
                  <input
                    id="field-update-reported-by"
                    className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                    value={reportedBy}
                    onChange={(e) => setReportedBy(e.target.value)}
                    placeholder="Name of the contractor or tenant"
                  />
                </div>
                {kind === "CONTRACTOR_REPORT" && (
                  <div>
                    <label
                      className="block text-xs font-medium text-muted-foreground"
                      htmlFor="field-update-observed-at"
                    >
                      When (optional)
                    </label>
                    <input
                      id="field-update-observed-at"
                      type="datetime-local"
                      className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                      value={observedAt}
                      onChange={(e) => setObservedAt(e.target.value)}
                      max={new Date().toISOString().slice(0, 16)}
                    />
                  </div>
                )}
              </div>
            )}

            {kind === "ATTENDANCE_WINDOW_ENDED" && (
              <p className="mt-3 text-xs text-muted-foreground">
                Records that the booked window passed without a report arriving.
                No further detail needed.
              </p>
            )}

            <Button
              type="submit"
              disabled={!canSubmit}
              className="mt-5 w-full"
              title={
                canSubmit
                  ? undefined
                  : needsAttribution
                    ? "Describe what was reported and name who reported it."
                    : "Select the visit this applies to."
              }
            >
              {submit.isPending ? "Recording…" : "Record on the case"}
            </Button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
