import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { Pencil, Plus, PoundSterling, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import {
  useCaseCosts,
  useCreateCost,
  useDeleteCost,
  useUpdateCost,
  type CostEntryRecord,
  type CostKind,
  type CostTotals,
} from "@/hooks/use-case-content";
import type { WorkOrder } from "@/api/types";
import { formatDate, formatPence, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring disabled:opacity-50";
const labelClass = "block text-[11px] font-medium text-muted-foreground";

const workOrderKindLabel: Record<string, string> = {
  REPAIR: "Repair",
  SCAFFOLD_INSTALL: "Scaffold install",
  SCAFFOLD_REMOVE: "Scaffold removal",
};

const KIND_LABEL: Record<CostKind, string> = {
  QUOTE: "Quote",
  INVOICE: "Invoice",
  ADJUSTMENT: "Adjustment",
};

const KIND_TONE: Record<CostKind, "blue" | "green" | "purple"> = {
  QUOTE: "blue",
  INVOICE: "green",
  ADJUSTMENT: "purple",
};

/** Pounds-in-a-text-field -> integer pence, entirely by string handling --
 * never `Math.round(pounds * 100)` on a raw float, per the task
 * instructions and backend/app/api/costs.py's own "always pence" rule.
 * Mirrors `_validate_amount` there: every kind rejects zero; only
 * QUOTE/INVOICE additionally reject a negative amount -- ADJUSTMENT is a
 * signed correction and must be allowed to go either way. */
function parsePoundsToPence(raw: string, allowNegative: boolean): number | null {
  const trimmed = raw.trim();
  const re = allowNegative ? /^-?\d+(\.\d{1,2})?$/ : /^\d+(\.\d{1,2})?$/;
  if (!re.test(trimmed)) return null;
  const negative = trimmed.startsWith("-");
  const unsigned = negative ? trimmed.slice(1) : trimmed;
  const [poundsPart = "0", penceRaw = ""] = unsigned.split(".");
  const penceStr = (penceRaw + "00").slice(0, 2);
  const total = parseInt(poundsPart, 10) * 100 + parseInt(penceStr, 10);
  return negative ? -total : total;
}

function penceToPoundsInput(pence: number): string {
  const negative = pence < 0;
  const abs = Math.abs(pence);
  const pounds = Math.floor(abs / 100);
  const remainder = String(abs % 100).padStart(2, "0");
  return `${negative ? "-" : ""}${pounds}.${remainder}`;
}

const todayIso = () => new Date().toISOString().slice(0, 10);

interface CostFormValue {
  kind: CostKind;
  amountInput: string;
  workOrderId: string;
  description: string;
  incurredAt: string;
}

function emptyCostForm(): CostFormValue {
  return {
    kind: "QUOTE",
    amountInput: "",
    workOrderId: "",
    description: "",
    incurredAt: todayIso(),
  };
}

function costToForm(cost: CostEntryRecord): CostFormValue {
  return {
    kind: cost.kind,
    amountInput: penceToPoundsInput(cost.amount_pence),
    workOrderId: cost.work_order_id ?? "",
    description: cost.description,
    incurredAt: cost.incurred_at.slice(0, 10),
  };
}

function useCostFormErrors(form: CostFormValue) {
  const allowNegative = form.kind === "ADJUSTMENT";
  const parsedPence = parsePoundsToPence(form.amountInput, allowNegative);
  const today = todayIso();
  const errors = {
    amount:
      parsedPence === null
        ? "Enter an amount in pounds, e.g. 125.50."
        : parsedPence === 0
          ? "Amount can't be zero."
          : !allowNegative && parsedPence < 0
            ? `${KIND_LABEL[form.kind]} amounts must be positive.`
            : null,
    description: form.description.trim().length > 0 ? null : "Say what this cost is for.",
    incurredAt: !form.incurredAt
      ? "Pick a date."
      : form.incurredAt > today
        ? "Can't be in the future."
        : null,
  };
  return { parsedPence, errors, valid: Object.values(errors).every((e) => e === null) };
}

function CostFormFields({
  form,
  setForm,
  touched,
  errors,
  workOrders,
  idPrefix,
}: {
  form: CostFormValue;
  setForm: React.Dispatch<React.SetStateAction<CostFormValue>>;
  touched: boolean;
  errors: ReturnType<typeof useCostFormErrors>["errors"];
  workOrders: WorkOrder[];
  idPrefix: string;
}) {
  const showError = (key: keyof typeof errors) => touched && errors[key];
  return (
    <>
      <div className="grid grid-cols-2 gap-2.5">
        <div>
          <label className={labelClass} htmlFor={`${idPrefix}-kind`}>
            Kind
          </label>
          <select
            id={`${idPrefix}-kind`}
            className={fieldClass}
            value={form.kind}
            onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value as CostKind }))}
          >
            <option value="QUOTE">Quote</option>
            <option value="INVOICE">Invoice</option>
            <option value="ADJUSTMENT">Adjustment (can be negative)</option>
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor={`${idPrefix}-amount`}>
            Amount (£)
          </label>
          <input
            id={`${idPrefix}-amount`}
            className={fieldClass}
            value={form.amountInput}
            onChange={(e) => setForm((f) => ({ ...f, amountInput: e.target.value }))}
            placeholder={form.kind === "ADJUSTMENT" ? "e.g. -25.00" : "e.g. 125.50"}
            inputMode="decimal"
            aria-invalid={showError("amount") ? true : undefined}
          />
          {showError("amount") && (
            <p className="mt-1 text-[11px] text-destructive">{errors.amount}</p>
          )}
        </div>
      </div>
      <div className="mt-2.5 grid grid-cols-2 gap-2.5">
        <div>
          <label className={labelClass} htmlFor={`${idPrefix}-work-order`}>
            Work order (optional)
          </label>
          <select
            id={`${idPrefix}-work-order`}
            className={fieldClass}
            value={form.workOrderId}
            onChange={(e) => setForm((f) => ({ ...f, workOrderId: e.target.value }))}
          >
            <option value="">Case-level (no work order)</option>
            {workOrders.map((wo) => (
              <option key={wo.id} value={wo.id}>
                {workOrderKindLabel[wo.kind] ?? titleCase(wo.kind)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor={`${idPrefix}-incurred-at`}>
            Incurred on
          </label>
          <input
            id={`${idPrefix}-incurred-at`}
            type="date"
            max={todayIso()}
            className={fieldClass}
            value={form.incurredAt}
            onChange={(e) => setForm((f) => ({ ...f, incurredAt: e.target.value }))}
            aria-invalid={showError("incurredAt") ? true : undefined}
          />
          {showError("incurredAt") && (
            <p className="mt-1 text-[11px] text-destructive">{errors.incurredAt}</p>
          )}
        </div>
      </div>
      <div className="mt-2.5">
        <label className={labelClass} htmlFor={`${idPrefix}-description`}>
          Description
        </label>
        <input
          id={`${idPrefix}-description`}
          className={fieldClass}
          value={form.description}
          onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          placeholder="What is this cost for?"
          aria-invalid={showError("description") ? true : undefined}
        />
        {showError("description") && (
          <p className="mt-1 text-[11px] text-destructive">{errors.description}</p>
        )}
      </div>
    </>
  );
}

function AddCostForm({ caseId, workOrders }: { caseId: string; workOrders: WorkOrder[] }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CostFormValue>(emptyCostForm);
  const [touched, setTouched] = useState(false);
  const create = useCreateCost(caseId);
  const { parsedPence, errors, valid } = useCostFormErrors(form);

  useEffect(() => {
    if (open) {
      setForm(emptyCostForm());
      setTouched(false);
    }
  }, [open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (parsedPence === null || !valid) return;
    try {
      await create.mutateAsync({
        kind: form.kind,
        amount_pence: parsedPence,
        description: form.description.trim(),
        // `T00:00:00` (local midnight), not local noon: `new Date(...)`
        // parses that string in the browser's local timezone, and local
        // noon on "today" is already in the future in UTC for any
        // timezone ahead of UTC (e.g. BST) -- the server's
        // `_validate_incurred_at` (backend/app/api/costs.py) would then
        // reject a same-day entry recorded before lunch. Local midnight is
        // never in the future for a date that itself isn't.
        incurred_at: new Date(`${form.incurredAt}T00:00:00`).toISOString(),
        work_order_id: form.workOrderId || null,
      });
      setOpen(false);
    } catch {
      // toasted by the hook; keep the form open with the input intact.
    }
  }

  if (!open) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-3 rounded-xl bg-card"
        onClick={() => setOpen(true)}
      >
        <Plus /> Add cost
      </Button>
    );
  }

  return (
    <form
      onSubmit={(e) => void handleSubmit(e)}
      noValidate
      className="mt-3 rounded-lg border border-border p-3"
    >
      <CostFormFields
        form={form}
        setForm={setForm}
        touched={touched}
        errors={errors}
        workOrders={workOrders}
        idPrefix="add-cost"
      />
      <div className="mt-3 flex justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setOpen(false)}
          disabled={create.isPending}
        >
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={create.isPending || !valid}>
          {create.isPending ? "Saving…" : "Add cost"}
        </Button>
      </div>
    </form>
  );
}

function CostRow({
  caseId,
  cost,
  workOrders,
}: {
  caseId: string;
  cost: CostEntryRecord;
  workOrders: WorkOrder[];
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<CostFormValue>(() => costToForm(cost));
  const [touched, setTouched] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const update = useUpdateCost(caseId);
  const del = useDeleteCost(caseId);
  const { parsedPence, errors, valid } = useCostFormErrors(form);

  async function handleDelete() {
    try {
      await del.mutateAsync(cost.id);
      setConfirmOpen(false);
    } catch {
      // toasted by the hook; keep the confirmation open so the operator
      // can retry.
    }
  }

  // Re-seeds once per edit session (not on every background refetch of the
  // costs list) so an in-flight edit never gets silently overwritten.
  useEffect(() => {
    if (editing) {
      setForm(costToForm(cost));
      setTouched(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (parsedPence === null || !valid) return;
    try {
      await update.mutateAsync({
        costId: cost.id,
        body: {
          kind: form.kind,
          amount_pence: parsedPence,
          description: form.description.trim(),
          incurred_at: new Date(`${form.incurredAt}T00:00:00`).toISOString(),
          work_order_id: form.workOrderId || null,
        },
      });
      setEditing(false);
    } catch {
      // toasted by the hook
    }
  }

  if (editing) {
    return (
      <li className="rounded-lg border border-border p-3">
        <form onSubmit={(e) => void handleSave(e)} noValidate>
          <CostFormFields
            form={form}
            setForm={setForm}
            touched={touched}
            errors={errors}
            workOrders={workOrders}
            idPrefix={`cost-${cost.id}`}
          />
          <div className="mt-3 flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setEditing(false)}
              disabled={update.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={update.isPending || !valid}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </li>
    );
  }

  const workOrder = workOrders.find((w) => w.id === cost.work_order_id);

  return (
    <li className="flex items-start justify-between gap-3 rounded-lg border border-border p-3 text-xs">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={KIND_TONE[cost.kind]}>{KIND_LABEL[cost.kind]}</Pill>
          {workOrder && (
            <Pill tone="gray">
              {workOrderKindLabel[workOrder.kind] ?? titleCase(workOrder.kind)}
            </Pill>
          )}
          {cost.is_archived && <Pill tone="gray">Archival</Pill>}
        </div>
        <p className="mt-1.5 font-medium">{cost.description}</p>
        <p className="mt-0.5 text-muted-foreground">
          {formatDate(cost.incurred_at)} · recorded by {cost.recorded_by}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <span
          className={cn("text-[13px] font-semibold", cost.amount_pence < 0 && "text-destructive")}
        >
          {formatPence(cost.amount_pence)}
        </span>
        {!cost.is_archived && (
          <div className="flex gap-1">
            <button
              type="button"
              aria-label={`Edit ${cost.description}`}
              onClick={() => setEditing(true)}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Pencil className="h-3 w-3" />
            </button>
            <AlertDialog.Root open={confirmOpen} onOpenChange={setConfirmOpen}>
              <AlertDialog.Trigger asChild>
                <button
                  type="button"
                  aria-label={`Delete ${cost.description}`}
                  className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:border-destructive hover:bg-destructive/10 hover:text-destructive"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </AlertDialog.Trigger>
              <AlertDialog.Portal>
                <AlertDialog.Overlay className="fixed inset-0 z-50 bg-foreground/20" />
                <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-5 shadow-panel">
                  <AlertDialog.Title className="text-sm font-semibold">
                    Delete this cost entry?
                  </AlertDialog.Title>
                  <AlertDialog.Description className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    “{cost.description}” ({formatPence(cost.amount_pence)}) will be permanently
                    removed. This can't be undone.
                  </AlertDialog.Description>
                  <div className="mt-4 flex justify-end gap-2">
                    <AlertDialog.Cancel asChild>
                      <Button variant="ghost" size="sm" disabled={del.isPending}>
                        Cancel
                      </Button>
                    </AlertDialog.Cancel>
                    {/* Plain Button, not AlertDialog.Action -- see the
                     * matching comment in DocumentsPanel.tsx's delete
                     * confirmation for why. */}
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={del.isPending}
                      onClick={() => void handleDelete()}
                    >
                      {del.isPending ? "Deleting…" : "Delete"}
                    </Button>
                  </div>
                </AlertDialog.Content>
              </AlertDialog.Portal>
            </AlertDialog.Root>
          </div>
        )}
      </div>
    </li>
  );
}

function TotalTile({
  label,
  value,
  hint,
  emphasize,
}: {
  label: string;
  value: number;
  hint: string;
  emphasize?: boolean;
}) {
  return (
    <div title={hint}>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-0.5 font-semibold",
          emphasize ? "text-sm" : "text-xs",
          value < 0 && "text-destructive",
        )}
      >
        {formatPence(value)}
      </div>
    </div>
  );
}

/** Mirrors backend/app/api/costs.py's `_compute_totals` -- quoted/invoiced/
 * adjustments/net/committed are five distinct figures, never summed
 * together into one another (quoted and actual money must stay visually
 * distinct per the task's own instructions). */
function TotalsBlock({ totals }: { totals: CostTotals }) {
  return (
    <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2.5 rounded-lg border border-border bg-muted/40 p-3 sm:grid-cols-5">
      <TotalTile
        label="Quoted"
        value={totals.quoted_pence}
        hint="Estimates -- not money actually spent."
      />
      <TotalTile label="Invoiced" value={totals.invoiced_pence} hint="Actually billed." />
      <TotalTile
        label="Adjustments"
        value={totals.adjustments_pence}
        hint="Signed corrections to invoiced amounts."
      />
      <TotalTile
        label="Net"
        value={totals.net_pence}
        hint="Invoiced + adjustments -- the real money figure."
        emphasize
      />
      <TotalTile
        label="Committed est."
        value={totals.committed_pence}
        hint="Current best estimate per work order: the invoice where one exists, else the quote. Not a sum of quoted and invoiced."
      />
    </div>
  );
}

/** Replaces the old CostsColumn. Keeps the real per-work-order quote/
 * approved-limit block, and adds the real CostEntry ledger --
 * GET|POST /api/v1/cases/{id}/costs, PATCH|DELETE /api/v1/costs/{id}
 * (backend/app/api/costs.py). */
export function CostsPanel({ caseId, workOrders }: { caseId: string; workOrders: WorkOrder[] }) {
  const costs = useCaseCosts(caseId);

  return (
    <Card className="p-5">
      <div>
        <h2 className="text-[15px] font-semibold">Costs</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Quotes and approved spend limits per work order, plus every recorded cost entry on this
          case.
        </p>
      </div>

      <div className="mt-4">
        <div className="text-[13px] font-semibold">By work order</div>
        {workOrders.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">No work orders on this case yet.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {workOrders.map((wo) => (
              <li key={wo.id} className="rounded-lg border border-border p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-[13px] font-semibold">
                      {workOrderKindLabel[wo.kind] ?? titleCase(wo.kind)}
                      <Pill tone="gray">{titleCase(wo.trade)}</Pill>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{wo.scope}</p>
                  </div>
                  <Pill tone={wo.status === "COMPLETED" ? "green" : "blue"}>
                    {titleCase(wo.status)}
                  </Pill>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 border-t border-border pt-2.5 text-xs">
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <PoundSterling className="h-3 w-3" /> Quoted
                  </div>
                  <div className="text-right font-medium">
                    {formatPence(wo.quote_pence) ?? "No quote recorded"}
                  </div>
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    <PoundSterling className="h-3 w-3" /> Approved limit
                  </div>
                  <div className="text-right font-medium">
                    {formatPence(wo.approved_limit_pence) ?? "No approved limit set"}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-5 border-t border-border pt-4">
        <div className="text-[13px] font-semibold">Recorded costs</div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Quoted and actual money are never summed together -- see the figures below.
        </p>

        {costs.isLoading && <LoadingRows rows={3} className="mt-3" />}
        {costs.isError && (
          <ErrorState
            className="mt-3"
            detail={costs.error instanceof Error ? costs.error.message : undefined}
            onRetry={() => void costs.refetch()}
          />
        )}

        {costs.data && (
          <>
            <TotalsBlock totals={costs.data.totals} />
            {costs.data.items.length === 0 ? (
              <EmptyState
                className="mt-3"
                icon={PoundSterling}
                title="No costs recorded yet"
                description="Log a quote, an invoice or an adjustment as it comes in."
              />
            ) : (
              <ul className="mt-3 space-y-2">
                {costs.data.items.map((cost) => (
                  <CostRow key={cost.id} caseId={caseId} cost={cost} workOrders={workOrders} />
                ))}
              </ul>
            )}
            <AddCostForm caseId={caseId} workOrders={workOrders} />
          </>
        )}
      </div>
    </Card>
  );
}
