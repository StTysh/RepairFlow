import * as Dialog from "@radix-ui/react-dialog";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useCancelCase, useReopenCase, useResumeCase } from "@/hooks/use-case-actions";
import { STATUS_LABEL, type CaseStatus } from "@/lib/fixi-data";
import { cn } from "@/lib/utils";

/**
 * The case status control.
 *
 * Deliberately not a "set status" dropdown. Each entry is a *domain
 * action* with its own preconditions, and the menu only offers the ones
 * the legal transition graph in `backend/app/domain/transitions.py`
 * permits from the current status:
 *
 *   ACTIVE                -> Cancel
 *   AWAITING_CONFIRMATION -> Cancel
 *   ESCALATED             -> Resume, Cancel
 *   RESOLVED              -> Reopen
 *   CANCELLED             -> terminal, nothing offered
 *
 * Resolution is absent on purpose: a case becomes RESOLVED when the work
 * is verified complete, which the coordinator and the approval flow
 * decide. An operator cannot declare a repair fixed from a menu.
 *
 * Every action carries the case `version` the operator was looking at, so
 * a decision taken against stale data is rejected by the server rather
 * than silently overwriting someone else's change.
 */

interface ActionField {
  name: "reason" | "resolved_hold_evidence";
  label: string;
  placeholder: string;
  required: boolean;
}

interface LifecycleAction {
  key: "resume" | "reopen" | "cancel";
  label: string;
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  fields: ActionField[];
}

const REASON_FIELD: ActionField = {
  name: "reason",
  label: "Reason",
  placeholder: "Why is this happening? Recorded on the case timeline.",
  required: true,
};

const ACTIONS: Record<CaseStatus, LifecycleAction[]> = {
  ACTIVE: [
    {
      key: "cancel",
      label: "Cancel case",
      title: "Cancel this case",
      description:
        "Closes the case without a repair outcome. Outstanding work orders stop. This is recorded, not deleted — the case and its history stay readable.",
      confirmLabel: "Cancel case",
      destructive: true,
      fields: [REASON_FIELD],
    },
  ],
  AWAITING_CONFIRMATION: [
    {
      key: "cancel",
      label: "Cancel case",
      title: "Cancel this case",
      description:
        "Closes the case without a repair outcome while it is waiting on a confirmation. Recorded, not deleted.",
      confirmLabel: "Cancel case",
      destructive: true,
      fields: [REASON_FIELD],
    },
  ],
  ESCALATED: [
    {
      key: "resume",
      label: "Resume case",
      title: "Resume automatic handling",
      description:
        "Hands the case back to the coordinator. Only do this once whatever caused the escalation has actually been dealt with — record what that was.",
      confirmLabel: "Resume",
      fields: [
        REASON_FIELD,
        {
          name: "resolved_hold_evidence",
          label: "What resolved the hold?",
          placeholder: "e.g. Gas engineer attended and made the appliance safe at 14:10.",
          required: true,
        },
      ],
    },
    {
      key: "cancel",
      label: "Cancel case",
      title: "Cancel this case",
      description: "Closes an escalated case without a repair outcome. Recorded, not deleted.",
      confirmLabel: "Cancel case",
      destructive: true,
      fields: [REASON_FIELD],
    },
  ],
  RESOLVED: [
    {
      key: "reopen",
      label: "Reopen case",
      title: "Reopen this case",
      description:
        "Use when the issue was not actually fixed. The case returns to active handling with its full history intact.",
      confirmLabel: "Reopen",
      fields: [REASON_FIELD],
    },
  ],
  CANCELLED: [],
};

export function CaseLifecycleActions({
  caseId,
  status,
  version,
}: {
  caseId: string;
  status: CaseStatus;
  version: number;
}) {
  const resume = useResumeCase(caseId);
  const reopen = useReopenCase(caseId);
  const cancel = useCancelCase(caseId);
  const [open, setOpen] = useState<LifecycleAction | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const pending = resume.isPending || reopen.isPending || cancel.isPending;
  const available = ACTIONS[status] ?? [];

  function start(action: LifecycleAction) {
    setValues({});
    setError(null);
    setOpen(action);
  }

  const missing = open?.fields.filter((f) => f.required && !(values[f.name] ?? "").trim()) ?? [];

  async function submit() {
    if (open === null || missing.length > 0) return;
    setError(null);
    const reason = (values["reason"] ?? "").trim();
    try {
      if (open.key === "resume") {
        await resume.mutateAsync({
          version,
          reason,
          resolved_hold_evidence: (values["resolved_hold_evidence"] ?? "").trim(),
        });
      } else if (open.key === "reopen") {
        await reopen.mutateAsync({ version, reason });
      } else {
        await cancel.mutateAsync({ version, reason });
      }
      setOpen(null);
    } catch (err) {
      // Shown in the dialog so the operator can correct and retry without
      // losing what they typed; the hooks also raise a toast.
      setError(err instanceof Error ? err.message : "That action could not be completed.");
    }
  }

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button
            variant="outline"
            className="rounded-xl bg-card"
            disabled={pending || available.length === 0}
            aria-label={
              available.length === 0
                ? `Status: ${STATUS_LABEL[status]} — no further actions available`
                : "Change case status"
            }
            title={
              available.length === 0
                ? `This case is ${STATUS_LABEL[status].toLowerCase()}; there are no further actions to take on it.`
                : undefined
            }
          >
            <span className="font-semibold">{STATUS_LABEL[status]}</span>
            <ChevronDown />
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={6}
            className="z-50 w-72 rounded-xl border border-border bg-card p-1.5 shadow-panel"
          >
            <div className="px-2 py-1.5 text-micro text-muted-foreground">
              Actions allowed from “{STATUS_LABEL[status]}”
            </div>
            {available.map((action) => (
              <DropdownMenu.Item
                key={action.key}
                onSelect={() => start(action)}
                className={cn(
                  "cursor-pointer rounded-lg px-2 py-2 text-xs font-medium outline-none",
                  "focus:bg-accent data-[highlighted]:bg-accent",
                  action.destructive && "text-destructive",
                )}
              >
                {action.label}
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <Dialog.Root open={open !== null} onOpenChange={(next) => !next && setOpen(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/25 backdrop-blur-[1px]" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(28rem,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-5 shadow-panel">
            <Dialog.Title className="text-section font-semibold">{open?.title}</Dialog.Title>
            <Dialog.Description className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {open?.description}
            </Dialog.Description>

            <div className="mt-4 space-y-3">
              {open?.fields.map((field) => (
                <label key={field.name} className="block">
                  <span className="text-xs font-medium">
                    {field.label}
                    {field.required && <span className="text-destructive"> *</span>}
                  </span>
                  <textarea
                    rows={field.name === "reason" ? 3 : 2}
                    value={values[field.name] ?? ""}
                    placeholder={field.placeholder}
                    onChange={(e) =>
                      setValues((prev) => ({ ...prev, [field.name]: e.target.value }))
                    }
                    className="mt-1 w-full resize-y rounded-lg border border-border bg-background px-2.5 py-2 text-xs outline-none focus:ring-2 focus:ring-ring"
                  />
                </label>
              ))}
            </div>

            {error && <p className="mt-3 text-xs text-destructive">{error}</p>}

            <div className="mt-5 flex items-center justify-end gap-2">
              <Dialog.Close asChild>
                <Button variant="ghost" size="sm" disabled={pending}>
                  Cancel
                </Button>
              </Dialog.Close>
              <Button
                size="sm"
                variant={open?.destructive ? "destructive" : "default"}
                disabled={pending || missing.length > 0}
                title={missing.length > 0 ? `${missing[0]?.label} is required` : undefined}
                onClick={() => void submit()}
              >
                {pending ? "Working…" : (open?.confirmLabel ?? "Confirm")}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
