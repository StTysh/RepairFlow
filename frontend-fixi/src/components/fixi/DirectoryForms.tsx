import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import {
  TRADES,
  useCreateContractor,
  useCreateTenant,
  useDirectoryProperties,
  useUpdateContractor,
  useUpdateTenant,
  type ContractorListItem,
  type Trade,
  type TenantListItem,
} from "@/hooks/use-directory";
import { titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// Shared dialog chrome (overlay/content shell, header with title + close)
// -- copies NewTicketDialog.tsx / SimulateObservationDialog.tsx's Radix
// Dialog primitive usage exactly (same classes, same z-50/overlay pair) so
// every dialog in this app looks and behaves like one system. Radix's
// Dialog.Content already traps focus into itself on open and returns it to
// the trigger on close, and Escape already closes it -- nothing extra is
// needed here for that.
function FormDialogShell({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  trigger: React.ReactNode;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/20" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-full max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-border bg-card p-6 shadow-panel">
          <div className="flex items-start justify-between">
            <div>
              <Dialog.Title className="text-sm font-semibold text-foreground">
                {title}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-muted-foreground">
                {description}
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
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function FieldLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label className="mt-3 block text-xs font-medium text-muted-foreground" htmlFor={htmlFor}>
      {children}
    </label>
  );
}

const inputClass =
  "mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring disabled:opacity-50";

function TradeToggleRow({
  selected,
  onToggle,
}: {
  selected: Set<Trade>;
  onToggle: (t: Trade) => void;
}) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5" role="group" aria-label="Trades">
      {TRADES.map((t) => (
        <button
          key={t}
          type="button"
          aria-pressed={selected.has(t)}
          onClick={() => onToggle(t)}
          className={cn(
            "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
            selected.has(t)
              ? "border-foreground bg-foreground text-background"
              : "border-border bg-card text-foreground hover:bg-accent",
          )}
        >
          {titleCase(t)}
        </button>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------
// Contractors
// --------------------------------------------------------------------------

/** Create-or-edit dialog for a contractor. In create mode the backend never
 * auto-approves what's submitted here (CLAUDE.md: "A candidate from the web
 * is not an approved contractor") -- there is deliberately no
 * approval-status control on this form; approving is its own explicit,
 * separately-gated action on the profile page (see
 * routes/contractors.$contractorId.tsx's useApproveContractor). */
export function ContractorFormDialog({
  mode,
  contractor,
  trigger,
  onSaved,
}: {
  mode: "create" | "edit";
  contractor?: ContractorListItem | undefined;
  trigger: React.ReactNode;
  onSaved?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [trades, setTrades] = useState<Set<Trade>>(new Set());
  const [postcodes, setPostcodes] = useState("");
  const [contactReference, setContactReference] = useState("");
  const [verificationNote, setVerificationNote] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const create = useCreateContractor();
  const update = useUpdateContractor(contractor?.id ?? "");
  const pending = create.isPending || update.isPending;

  // Re-sync from the latest contractor every time the dialog opens (edit
  // mode) or clear to blank (create mode) -- the dialog stays mounted
  // across opens rather than remounting, so state can't just be seeded once.
  useEffect(() => {
    if (!open) return;
    if (mode === "edit" && contractor) {
      setDisplayName(contractor.display_name);
      setTrades(new Set(contractor.trades));
      setPostcodes(contractor.service_postcodes.join(", "));
      setContactReference(contractor.contact_reference ?? "");
      setVerificationNote(contractor.verification_note ?? "");
    } else {
      setDisplayName("");
      setTrades(new Set());
      setPostcodes("");
      setContactReference("");
      setVerificationNote("");
    }
    setFormError(null);
  }, [open, mode, contractor]);

  function toggleTrade(t: Trade) {
    setTrades((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  const postcodeList = postcodes
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  const canSubmit = displayName.trim().length > 0 && trades.size > 0 && !pending;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setFormError(null);
    const body = {
      display_name: displayName.trim(),
      trades: Array.from(trades),
      service_postcodes: postcodeList,
      contact_reference: contactReference.trim() || null,
      verification_note: verificationNote.trim() || null,
    };
    try {
      if (mode === "create") {
        await create.mutateAsync(body);
      } else {
        await update.mutateAsync(body);
      }
      setOpen(false);
      onSaved?.();
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Something went wrong. Please try again.",
      );
    }
  }

  return (
    <FormDialogShell
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      title={mode === "create" ? "New contractor" : "Edit contractor"}
      description={
        mode === "create"
          ? "Added as a research candidate -- not approved for assignment until verified."
          : "Update this contractor's details."
      }
    >
      <form onSubmit={(e) => void handleSubmit(e)}>
        <FieldLabel htmlFor="contractor-name">Display name</FieldLabel>
        <input
          id="contractor-name"
          className={inputClass}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="e.g. Apex Roofing Ltd"
          autoFocus
          required
        />
        {displayName.trim().length === 0 && (
          <p className="mt-1 text-[11px] text-muted-foreground">Required.</p>
        )}

        <span className="mt-3 block text-xs font-medium text-muted-foreground">Trades</span>
        <TradeToggleRow selected={trades} onToggle={toggleTrade} />
        {trades.size === 0 && (
          <p className="mt-1 text-[11px] text-muted-foreground">Select at least one trade.</p>
        )}

        <FieldLabel htmlFor="contractor-postcodes">Service postcodes</FieldLabel>
        <input
          id="contractor-postcodes"
          className={inputClass}
          value={postcodes}
          onChange={(e) => setPostcodes(e.target.value)}
          placeholder="e.g. SW1A, EC1, N1"
        />
        <p className="mt-1 text-[11px] text-muted-foreground">Comma-separated.</p>

        <FieldLabel htmlFor="contractor-contact">Contact reference</FieldLabel>
        <input
          id="contractor-contact"
          className={inputClass}
          value={contactReference}
          onChange={(e) => setContactReference(e.target.value)}
          placeholder="Phone, email or booking reference"
        />

        <FieldLabel htmlFor="contractor-note">Verification note</FieldLabel>
        <textarea
          id="contractor-note"
          className={cn(inputClass, "h-20 resize-none")}
          value={verificationNote}
          onChange={(e) => setVerificationNote(e.target.value)}
          placeholder="How was this contractor verified? Required before it can be approved."
        />

        {formError && <p className="mt-3 text-xs text-destructive">{formError}</p>}

        <button
          type="submit"
          disabled={!canSubmit}
          className="mt-5 flex h-9 w-full items-center justify-center rounded-lg bg-primary text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {pending ? "Saving…" : mode === "create" ? "Add contractor" : "Save changes"}
        </button>
      </form>
    </FormDialogShell>
  );
}

// --------------------------------------------------------------------------
// Tenants
// --------------------------------------------------------------------------

const PREFERRED_CHANNELS = ["PHONE", "SMS", "EMAIL"] as const;

/** Rejects nothing the backend wouldn't also accept -- Tenant.preferred_channel
 * is a plain `str` on the backend (backend/app/schemas.py), not a validated
 * enum, so this is a curated convenience list rather than an exhaustive one;
 * an existing tenant with some other value keeps it selectable below. */
function channelOptions(current: string | null): string[] {
  if (current && !(PREFERRED_CHANNELS as readonly string[]).includes(current)) {
    return [current, ...PREFERRED_CHANNELS];
  }
  return [...PREFERRED_CHANNELS];
}

function isValidE164(value: string): boolean {
  return /^\+\d{8,15}$/.test(value);
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export function TenantFormDialog({
  mode,
  tenant,
  trigger,
  onSaved,
}: {
  mode: "create" | "edit";
  tenant?: TenantListItem | undefined;
  trigger: React.ReactNode;
  onSaved?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [preferredChannel, setPreferredChannel] = useState<string>("PHONE");
  const [contactAllowed, setContactAllowed] = useState(true);
  const [accessibilityNotes, setAccessibilityNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const properties = useDirectoryProperties();
  const create = useCreateTenant();
  const update = useUpdateTenant(tenant?.id ?? "");
  const pending = create.isPending || update.isPending;

  useEffect(() => {
    if (!open) return;
    if (mode === "edit" && tenant) {
      setDisplayName(tenant.display_name);
      setPropertyId(tenant.property_id);
      setPhone(tenant.phone_e164 ?? "");
      setEmail(tenant.email ?? "");
      setPreferredChannel(tenant.preferred_channel ?? "PHONE");
      setContactAllowed(tenant.contact_allowed);
      setAccessibilityNotes(tenant.accessibility_notes ?? "");
    } else {
      setDisplayName("");
      setPropertyId(properties.data?.[0]?.id ?? "");
      setPhone("");
      setEmail("");
      setPreferredChannel("PHONE");
      setContactAllowed(true);
      setAccessibilityNotes("");
    }
    setFormError(null);
    // properties.data intentionally excluded -- only used to seed a default
    // on open, not to reset the field while the operator is mid-edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mode, tenant]);

  const phoneValid = phone.trim().length === 0 || isValidE164(phone.trim());
  const emailValid = email.trim().length === 0 || isValidEmail(email.trim());
  const canSubmit =
    displayName.trim().length > 0 &&
    propertyId.length > 0 &&
    phoneValid &&
    emailValid &&
    !pending;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setFormError(null);
    const body = {
      display_name: displayName.trim(),
      property_id: propertyId,
      phone_e164: phone.trim() || null,
      email: email.trim() || null,
      preferred_channel: preferredChannel,
      contact_allowed: contactAllowed,
      accessibility_notes: accessibilityNotes.trim() || null,
    };
    try {
      if (mode === "create") {
        await create.mutateAsync(body);
      } else {
        await update.mutateAsync(body);
      }
      setOpen(false);
      onSaved?.();
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Something went wrong. Please try again.",
      );
    }
  }

  return (
    <FormDialogShell
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      title={mode === "create" ? "New tenant" : "Edit tenant"}
      description="Contact and property details for this tenant."
    >
      <form onSubmit={(e) => void handleSubmit(e)}>
        <FieldLabel htmlFor="tenant-name">Display name</FieldLabel>
        <input
          id="tenant-name"
          className={inputClass}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="e.g. Priya Shah"
          autoFocus
          required
        />

        <FieldLabel htmlFor="tenant-property">Property</FieldLabel>
        <select
          id="tenant-property"
          className={inputClass}
          value={propertyId}
          onChange={(e) => setPropertyId(e.target.value)}
          disabled={properties.isLoading}
          required
        >
          <option value="" disabled>
            {properties.isLoading ? "Loading properties…" : "Select a property"}
          </option>
          {(properties.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.address_line}
              {p.postcode ? `, ${p.postcode}` : ""}
            </option>
          ))}
        </select>
        {properties.isError && (
          <p className="mt-1 text-[11px] text-destructive">Could not load properties.</p>
        )}

        <FieldLabel htmlFor="tenant-phone">Phone</FieldLabel>
        <input
          id="tenant-phone"
          className={inputClass}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+447700900000"
          inputMode="tel"
        />
        {!phoneValid && (
          <p className="mt-1 text-[11px] text-destructive">
            Enter a valid E.164 number: + followed by 8–15 digits.
          </p>
        )}

        <FieldLabel htmlFor="tenant-email">Email</FieldLabel>
        <input
          id="tenant-email"
          type="email"
          className={inputClass}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="tenant@example.com"
        />
        {!emailValid && <p className="mt-1 text-[11px] text-destructive">Enter a valid email.</p>}

        <FieldLabel htmlFor="tenant-channel">Preferred channel</FieldLabel>
        <select
          id="tenant-channel"
          className={inputClass}
          value={preferredChannel}
          onChange={(e) => setPreferredChannel(e.target.value)}
        >
          {channelOptions(tenant?.preferred_channel ?? null).map((c) => (
            <option key={c} value={c}>
              {titleCase(c)}
            </option>
          ))}
        </select>

        <span className="mt-3 block text-xs font-medium text-muted-foreground">
          Contact allowed?
        </span>
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            aria-pressed={contactAllowed}
            onClick={() => setContactAllowed(true)}
            className={cn(
              "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
              contactAllowed
                ? "border-foreground bg-foreground text-background"
                : "border-border bg-card hover:bg-accent",
            )}
          >
            Yes
          </button>
          <button
            type="button"
            aria-pressed={!contactAllowed}
            onClick={() => setContactAllowed(false)}
            className={cn(
              "h-8 rounded-lg border px-3 text-xs font-medium transition-colors",
              !contactAllowed
                ? "border-foreground bg-foreground text-background"
                : "border-border bg-card hover:bg-accent",
            )}
          >
            No
          </button>
        </div>
        {!contactAllowed && (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            No outbound contact will be offered for this tenant anywhere in the app.
          </p>
        )}

        <FieldLabel htmlFor="tenant-access-notes">Accessibility notes</FieldLabel>
        <textarea
          id="tenant-access-notes"
          className={cn(inputClass, "h-20 resize-none")}
          value={accessibilityNotes}
          onChange={(e) => setAccessibilityNotes(e.target.value)}
          placeholder="e.g. Hearing impaired -- prefers SMS over calls"
        />

        {formError && <p className="mt-3 text-xs text-destructive">{formError}</p>}

        <button
          type="submit"
          disabled={!canSubmit}
          className="mt-5 flex h-9 w-full items-center justify-center rounded-lg bg-primary text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {pending ? "Saving…" : mode === "create" ? "Add tenant" : "Save changes"}
        </button>
      </form>
    </FormDialogShell>
  );
}
