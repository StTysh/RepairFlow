import * as Dialog from "@radix-ui/react-dialog";
import { CalendarClock, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/fixi/Badge";
import { useRescheduleAppointment } from "@/hooks/use-case-content";
import type { Appointment } from "@/api/types";
import { formatDateRange } from "@/lib/format";

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring disabled:opacity-50";
const labelClass = "block text-xs font-medium text-muted-foreground";

/**
 * Moves a visit to a time the operator arranged out-of-band --
 * POST /api/v1/appointments/{id}/reschedule.
 *
 * This replaces the old "Reschedule" button, which only cancelled the
 * appointment and left the operator to notice a new one never appeared.
 * The backend cancels the old slot and creates the replacement as
 * **PENDING**, never CONFIRMED (docs/19: "provider request acceptance is
 * not booking confirmation", and an operator typing in a time is not even
 * a provider accepting it) -- the success state below says so in the same
 * words the API returns, rather than a generic "Saved".
 */
export function RescheduleDialog({
  caseId,
  appointment,
}: {
  caseId: string;
  appointment: Appointment;
}) {
  const [open, setOpen] = useState(false);
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [reason, setReason] = useState("");
  const [arrangedWith, setArrangedWith] = useState("");
  const [touched, setTouched] = useState(false);
  const [success, setSuccess] = useState<{ note: string } | null>(null);
  const reschedule = useRescheduleAppointment(caseId);

  // Seed once per open, not on every poll refresh of `appointment` (the
  // case detail query refetches every 2s -- see use-case-detail.ts) -- an
  // effect keyed only on `open` runs once when the dialog opens rather
  // than on every parent re-render, so the operator's typing is never
  // silently wiped mid-edit.
  useEffect(() => {
    if (open) {
      setStartAt("");
      setEndAt("");
      setReason("");
      setArrangedWith("");
      setTouched(false);
      setSuccess(null);
    }
  }, [open]);

  const startDate = startAt ? new Date(startAt) : null;
  const endDate = endAt ? new Date(endAt) : null;
  const now = new Date();

  const errors = {
    start: !startAt
      ? "Pick when the visit starts."
      : startDate && startDate <= now
        ? "The new visit must be in the future."
        : null,
    end: !endAt
      ? "Pick when the visit ends."
      : startDate && endDate && endDate <= startDate
        ? "The new visit must end after it starts."
        : null,
    reason: reason.trim().length >= 3 ? null : "Say why this is being moved.",
    arrangedWith:
      arrangedWith.trim().length >= 2 ? null : "Name who actually agreed this new time.",
  };
  const canSubmit = Object.values(errors).every((e) => e === null) && !reschedule.isPending;
  const showError = (key: keyof typeof errors) => touched && errors[key];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!startDate || !endDate || !Object.values(errors).every((v) => v === null)) return;
    try {
      const res = await reschedule.mutateAsync({
        appointmentId: appointment.id,
        body: {
          start_at: startDate.toISOString(),
          end_at: endDate.toISOString(),
          reason: reason.trim(),
          arranged_with: arrangedWith.trim(),
        },
      });
      setSuccess({ note: res.note });
    } catch {
      // Toasted by the hook's onError; the form stays open with the
      // operator's input intact so they can correct and retry.
    }
  }

  const { date, time } = formatDateRange(appointment.start_at, appointment.end_at);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
      }}
    >
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="h-8 rounded-lg border border-border bg-card px-3 text-xs font-medium shadow-card hover:bg-accent"
        >
          Reschedule
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/20" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-6 shadow-panel">
          <div className="flex items-start justify-between">
            <div>
              <Dialog.Title className="text-section font-semibold text-foreground">
                Reschedule visit
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Currently {date}, {time}. Moving this cancels that slot and records the new time as
                arranged by you -- not confirmed by the contractor.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close"
                className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {success ? (
            <div className="mt-4">
              <div className="flex items-center gap-2">
                <CalendarClock className="h-4 w-4 text-muted-foreground" />
                <Pill tone="amber">Pending — contractor has not confirmed</Pill>
              </div>
              <p className="mt-3 rounded-lg bg-muted px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                {success.note}
              </p>
              <Button className="mt-4 w-full" onClick={() => setOpen(false)}>
                Done
              </Button>
            </div>
          ) : (
            <form onSubmit={(e) => void handleSubmit(e)} noValidate>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div>
                  <label className={labelClass} htmlFor="reschedule-start">
                    New start
                  </label>
                  <input
                    id="reschedule-start"
                    type="datetime-local"
                    className={fieldClass}
                    value={startAt}
                    onChange={(e) => setStartAt(e.target.value)}
                    aria-invalid={showError("start") ? true : undefined}
                  />
                  {showError("start") && (
                    <p className="mt-1 text-micro text-destructive">{errors.start}</p>
                  )}
                </div>
                <div>
                  <label className={labelClass} htmlFor="reschedule-end">
                    New end
                  </label>
                  <input
                    id="reschedule-end"
                    type="datetime-local"
                    className={fieldClass}
                    value={endAt}
                    onChange={(e) => setEndAt(e.target.value)}
                    aria-invalid={showError("end") ? true : undefined}
                  />
                  {showError("end") && (
                    <p className="mt-1 text-micro text-destructive">{errors.end}</p>
                  )}
                </div>
              </div>

              <div className="mt-3">
                <label className={labelClass} htmlFor="reschedule-arranged-with">
                  Arranged with
                </label>
                <input
                  id="reschedule-arranged-with"
                  className={fieldClass}
                  value={arrangedWith}
                  onChange={(e) => setArrangedWith(e.target.value)}
                  placeholder="e.g. ABC Roofing — spoke to Dave"
                  aria-invalid={showError("arrangedWith") ? true : undefined}
                />
                {showError("arrangedWith") && (
                  <p className="mt-1 text-micro text-destructive">{errors.arrangedWith}</p>
                )}
              </div>

              <div className="mt-3">
                <label className={labelClass} htmlFor="reschedule-reason">
                  Reason
                </label>
                <textarea
                  id="reschedule-reason"
                  className={`${fieldClass} h-20 resize-y`}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Why is this visit moving?"
                  aria-invalid={showError("reason") ? true : undefined}
                />
                {showError("reason") && (
                  <p className="mt-1 text-micro text-destructive">{errors.reason}</p>
                )}
              </div>

              <div className="mt-5 flex items-center justify-end gap-2">
                <Dialog.Close asChild>
                  <Button variant="ghost" size="sm" disabled={reschedule.isPending}>
                    Cancel
                  </Button>
                </Dialog.Close>
                <Button type="submit" size="sm" disabled={!canSubmit}>
                  {reschedule.isPending ? "Saving…" : "Reschedule"}
                </Button>
              </div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
