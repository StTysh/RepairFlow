import * as Dialog from "@radix-ui/react-dialog";
import { FlaskConical, X } from "lucide-react";
import { useState } from "react";
import { useSubmitSimulationObservation } from "@/hooks/use-case-actions";
import type { Appointment, WorkOrder } from "@/api/types";
import { formatDateRange, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

type Kind = "CONTRACTOR_REPORT" | "TENANT_FEEDBACK" | "ATTENDANCE_WINDOW_ENDED";

const kindLabel: Record<Kind, string> = {
  CONTRACTOR_REPORT: "Contractor report",
  TENANT_FEEDBACK: "Tenant feedback",
  ATTENDANCE_WINDOW_ENDED: "Attendance window ended",
};

function appointmentLabel(appointment: Appointment, workOrders: WorkOrder[]): string {
  const wo = workOrders.find((w) => w.id === appointment.work_order_id);
  const { date, time } = formatDateRange(appointment.start_at, appointment.end_at);
  const scope = wo ? `${titleCase(wo.trade)} — ${titleCase(wo.kind)}` : "Work order";
  return `${scope} · ${date}, ${time} · ${appointment.status}`;
}

/** POST /api/v1/demo/cases/{case_id}/observations -- the only way to drive
 * the hero demo path from the UI. There's no live contractor/tenant channel
 * in this MVP, so an operator manually feeds in exactly what a real phone
 * call would have reported (e.g. "scaffolding needed before the roof can be
 * accessed"); the backend records it with SIMULATED provenance through the
 * same domain services a real ElevenLabs call would use
 * (backend/app/api/demo.py, demo_simulation_observation). This dialog must
 * never imply a real call happened -- it's an honest manual substitute.
 *
 * CONTRACTOR_REPORT and ATTENDANCE_WINDOW_ENDED both need a real
 * appointment already on the case (the backend 404s on anything else), so
 * both pickers are built directly off `appointments` from the snapshot --
 * never a free-typed ID, never a fabricated option. TENANT_FEEDBACK needs
 * no appointment and always works.
 *
 * Built on @radix-ui/react-dialog, matching NewTicketDialog.tsx's pattern
 * (same primitive, same layout shell) -- that's still the one other
 * multi-field flow in this app worth a real dialog over window.prompt(). */
export function SimulateObservationDialog({
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
  const [kind, setKind] = useState<Kind>(hasAppointments ? "CONTRACTOR_REPORT" : "TENANT_FEEDBACK");
  // Nullable operator override rather than an eagerly-initialized default:
  // this dialog stays mounted while the route polls, so `appointments` can
  // go from empty to populated (exactly the hero path, right after the
  // coordinator books the scaffold visit) without the component
  // remounting. Deriving the selected id at render time -- override falling
  // back to the first appointment -- means that transition is never missed
  // the way a one-time useState initializer would miss it.
  const [appointmentIdOverride, setAppointmentIdOverride] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [confirmsResolved, setConfirmsResolved] = useState(true);
  const submit = useSubmitSimulationObservation(caseId);

  const selectedAppointmentId = appointmentIdOverride ?? appointments[0]?.id ?? null;

  function reset() {
    setKind(appointments.length > 0 ? "CONTRACTOR_REPORT" : "TENANT_FEEDBACK");
    setAppointmentIdOverride(null);
    setText("");
    setConfirmsResolved(true);
  }

  const canSubmit =
    !submit.isPending &&
    (kind === "TENANT_FEEDBACK"
      ? text.trim().length > 0
      : kind === "CONTRACTOR_REPORT"
        ? !!selectedAppointmentId && text.trim().length > 0
        : !!selectedAppointmentId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (kind === "CONTRACTOR_REPORT") {
        if (!selectedAppointmentId) return;
        await submit.mutateAsync({
          kind: "CONTRACTOR_REPORT",
          appointment_id: selectedAppointmentId,
          text: text.trim(),
          observed_at: new Date().toISOString(),
        });
      } else if (kind === "TENANT_FEEDBACK") {
        await submit.mutateAsync({
          kind: "TENANT_FEEDBACK",
          confirms_resolved: confirmsResolved,
          text: text.trim(),
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
        <button
          type="button"
          title="Manually simulate what a contractor or tenant reported -- there's no live phone channel in this MVP"
          className="flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3.5 text-sm font-medium shadow-card transition-colors hover:bg-accent"
        >
          <FlaskConical className="h-4 w-4" /> Simulate contractor/tenant update
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/20" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-6 shadow-panel">
          <div className="flex items-start justify-between">
            <div>
              <Dialog.Title className="text-sm font-semibold text-foreground">
                Simulate an observation
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-muted-foreground">
                Manual input standing in for a real phone call -- there's no live contractor or
                tenant channel in this MVP. Recorded with SIMULATED provenance.
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
                const disabled = k !== "TENANT_FEEDBACK" && !hasAppointments;
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
                No booked appointment on this case yet, so there's no real appointment to pick for a
                contractor report or attendance-window update -- only tenant feedback needs none.
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
                  What did the contractor report?
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

            {kind === "TENANT_FEEDBACK" && (
              <>
                <label
                  className="mt-4 block text-xs font-medium text-muted-foreground"
                  htmlFor="sim-feedback-text"
                >
                  What did the tenant say?
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

            {kind === "ATTENDANCE_WINDOW_ENDED" && (
              <p className="mt-3 text-xs text-muted-foreground">
                Marks the selected appointment's attendance window as ended -- no further detail
                needed.
              </p>
            )}

            <button
              type="submit"
              disabled={!canSubmit}
              className="mt-5 flex h-9 w-full items-center justify-center rounded-lg bg-primary text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {submit.isPending ? "Submitting…" : "Submit simulated observation"}
            </button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
