import * as Dialog from "@radix-ui/react-dialog";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  Download,
  History,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Share2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import type { CaseSnapshot, Trade } from "@/api/types";
import { ApiError } from "@/api/client";
import { useEditCase } from "@/hooks/use-case-content";
import { caseDetailQueryKey } from "@/hooks/use-case-detail";
import { cn } from "@/lib/utils";

const fieldClass =
  "mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring disabled:opacity-50";
const labelClass = "block text-xs font-medium text-muted-foreground";

/** Attempts a clipboard write, returning whether it actually succeeded.
 * `navigator.clipboard` is `undefined` (not a rejected promise) on a
 * non-secure origin or when the permission is denied outright, so this
 * guards existence as well as catching the write itself. */
async function tryCopy(text: string): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.clipboard) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

// --- Share ------------------------------------------------------------

function ShareButton({ caseId }: { caseId: string }) {
  const [fallbackOpen, setFallbackOpen] = useState(false);
  const url =
    typeof window !== "undefined"
      ? `${window.location.origin}/maintenance/tickets/${caseId}`
      : `/maintenance/tickets/${caseId}`;

  async function handleShare() {
    const copied = await tryCopy(url);
    if (copied) {
      toast.success("Link copied — it grants no public access; anyone opening it still signs in.");
    } else {
      setFallbackOpen(true);
    }
  }

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="rounded-xl bg-card"
        onClick={() => void handleShare()}
        title="Copies a link to this case to your clipboard. It grants no public access — whoever opens it still has to sign in."
      >
        <Share2 /> Share
      </Button>
      <Dialog.Root open={fallbackOpen} onOpenChange={setFallbackOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/20" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-5 shadow-panel">
            <div className="flex items-start justify-between">
              <div>
                <Dialog.Title className="text-section font-semibold">Copy this link</Dialog.Title>
                <Dialog.Description className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  Your browser blocked automatic clipboard access. Copy it manually below — it
                  grants no public access; whoever opens it still has to sign in.
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
            <input
              readOnly
              value={url}
              onFocus={(e) => e.currentTarget.select()}
              className={fieldClass}
            />
            <div className="mt-4 flex justify-end">
              <Dialog.Close asChild>
                <Button size="sm" variant="ghost">
                  Close
                </Button>
              </Dialog.Close>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}

// --- Edit -----------------------------------------------------------------

const CATEGORY_UNCHANGED = "__unchanged__";
const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: CATEGORY_UNCHANGED, label: "Leave unchanged (current value isn't shown here)" },
  { value: "ROOFING", label: "Roofing" },
  { value: "PLUMBING", label: "Plumbing" },
  { value: "ELECTRICAL", label: "Electrical" },
  { value: "SCAFFOLDING", label: "Scaffolding" },
  { value: "OTHER", label: "Other" },
];

/** Edits the case's descriptive fields -- PATCH /api/v1/cases/{id}.
 *
 * `category` is deliberately never pre-filled: the case snapshot's `case`
 * object (backend/app/schemas.py RepairCase) does not carry the current
 * category at all (only CaseListItem does, from a different endpoint), so
 * there is no real value to show here. Rather than fabricate a default or
 * silently send a blind overwrite, the field defaults to "leave unchanged"
 * and is only included in the request if the operator actively picks a
 * different one. See NEEDS_FROM_ROOT_ticket.md.
 */
function EditCaseDialog({ snapshot }: { snapshot: CaseSnapshot }) {
  const { case: c, issue, property } = snapshot;
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState(CATEGORY_UNCHANGED);
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [accessNotes, setAccessNotes] = useState("");
  const [touched, setTouched] = useState(false);
  const [staleVersion, setStaleVersion] = useState(false);
  // Captured alongside the seeded values, not read fresh from `c.version`
  // at submit time: the case snapshot polls every 2s (use-case-detail.ts),
  // so by the time the operator clicks Save, `c` may already be a later
  // render than the one the form was seeded from. Submitting the *current*
  // version instead of the *seeded* one would defeat the whole point of
  // sending expected_version -- the 409 this dialog exists to catch would
  // never fire, and a stale edit could silently overwrite a newer one.
  const [seededVersion, setSeededVersion] = useState(c.version);
  const editCase = useEditCase(c.id);
  const queryClient = useQueryClient();

  function seedFromSnapshot() {
    setTitle(c.title);
    setCategory(CATEGORY_UNCHANGED);
    setLocation(issue.location);
    setDescription(issue.description);
    setAccessNotes(property.access_notes ?? "");
    setSeededVersion(c.version);
    setTouched(false);
    setStaleVersion(false);
  }

  // Seeds once when the dialog opens, never on the 2s snapshot poll that
  // keeps running underneath it (use-case-detail.ts) -- an effect keyed
  // only on `open` fires on that one transition, not on every re-render
  // the poll causes, so the operator's typing is never silently wiped.
  useEffect(() => {
    if (open) seedFromSnapshot();
  }, [open]);

  const errors = {
    title: title.trim().length >= 4 ? null : "Title needs at least a few characters.",
    location: location.trim().length >= 1 ? null : "Say where in the property this is.",
    description: description.trim().length >= 4 ? null : "Describe the issue.",
  };
  const canSubmit = Object.values(errors).every((e) => e === null) && !editCase.isPending;
  const showError = (key: keyof typeof errors) => touched && errors[key];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!canSubmit) return;
    try {
      await editCase.mutateAsync({
        expected_version: seededVersion,
        title: title.trim(),
        location: location.trim(),
        description: description.trim(),
        access_notes: accessNotes.trim(),
        ...(category !== CATEGORY_UNCHANGED ? { category: category as Trade } : {}),
      });
      setOpen(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setStaleVersion(true);
        // Pull the latest snapshot in immediately -- the operator's next
        // "Reload" click re-seeds the form from whatever comes back.
        void queryClient.invalidateQueries({ queryKey: caseDetailQueryKey(c.id) });
      }
      // Non-409 failures are toasted by the hook itself.
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
      }}
    >
      <Dialog.Trigger asChild>
        <Button variant="outline" size="sm" className="rounded-xl bg-card">
          <Pencil /> Edit
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/25 backdrop-blur-[1px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[min(30rem,92vw)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-panel">
          <div className="flex items-start justify-between gap-3">
            <div>
              <Dialog.Title className="text-section font-semibold text-foreground">
                Edit case
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Status isn't editable here -- it changes through the actions menu next to it, each
                with its own preconditions.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="iconSm" aria-label="Close">
                <X />
              </Button>
            </Dialog.Close>
          </div>

          {staleVersion && (
            <div className="mt-4 rounded-lg border border-status-red-foreground/25 bg-status-red/40 px-3 py-2 text-xs text-status-red-foreground">
              <p>Someone else changed this case — reload to see their version.</p>
              <button
                type="button"
                className="mt-1.5 font-semibold underline underline-offset-2"
                onClick={() => seedFromSnapshot()}
              >
                Reload from the latest version
              </button>
            </div>
          )}

          <form onSubmit={(e) => void handleSubmit(e)} noValidate>
            <div className="mt-4">
              <label className={labelClass} htmlFor="edit-case-title">
                Title
              </label>
              <input
                id="edit-case-title"
                className={fieldClass}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                aria-invalid={showError("title") ? true : undefined}
              />
              {showError("title") && (
                <p className="mt-1 text-micro text-destructive">{errors.title}</p>
              )}
            </div>

            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <label className={labelClass} htmlFor="edit-case-location">
                  Location
                </label>
                <input
                  id="edit-case-location"
                  className={fieldClass}
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  aria-invalid={showError("location") ? true : undefined}
                />
                {showError("location") && (
                  <p className="mt-1 text-micro text-destructive">{errors.location}</p>
                )}
              </div>
              <div>
                <label className={labelClass} htmlFor="edit-case-category">
                  Category
                </label>
                <select
                  id="edit-case-category"
                  className={fieldClass}
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {CATEGORY_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mt-3">
              <label className={labelClass} htmlFor="edit-case-description">
                Description
              </label>
              <textarea
                id="edit-case-description"
                className={`${fieldClass} h-20 resize-y`}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                aria-invalid={showError("description") ? true : undefined}
              />
              {showError("description") && (
                <p className="mt-1 text-micro text-destructive">{errors.description}</p>
              )}
            </div>

            <div className="mt-3">
              <label className={labelClass} htmlFor="edit-case-access-notes">
                Property access notes
              </label>
              <textarea
                id="edit-case-access-notes"
                className={`${fieldClass} h-16 resize-y`}
                value={accessNotes}
                onChange={(e) => setAccessNotes(e.target.value)}
                placeholder="Key safe code, parking, dog on site, etc."
              />
            </div>

            <div className="mt-5 flex items-center justify-end gap-2">
              <Dialog.Close asChild>
                <Button variant="ghost" size="sm" disabled={editCase.isPending}>
                  Cancel
                </Button>
              </Dialog.Close>
              <Button type="submit" size="sm" disabled={!canSubmit}>
                {editCase.isPending ? "Saving…" : "Save changes"}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// --- More actions (kebab) --------------------------------------------------

function exportCaseSummary(snapshot: CaseSnapshot) {
  const payload = {
    exported_at: new Date().toISOString(),
    case: snapshot.case,
    issue: snapshot.issue,
    property: snapshot.property,
    tenant: snapshot.tenant,
    assigned_contractor: snapshot.assigned_contractor,
    work_orders: snapshot.work_orders,
    dependencies: snapshot.dependencies,
    appointments: snapshot.appointments,
    latest_reports: snapshot.latest_reports,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `case-${snapshot.case.case_number}-summary.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Routes to a tenant/contractor/conversation/history destination that
 * doesn't have a registered route in this checkout yet (`/messages/$caseId`
 * -- see NEEDS_FROM_ROOT_ticket.md) fall back to a plain anchor instead of
 * a typed `<Link>`, since TanStack's `to` prop is type-checked against the
 * generated route tree and would fail `tsc` until that route lands. A full
 * navigation still lands on the right page once it does. */
function MoreActionsMenu({ snapshot }: { snapshot: CaseSnapshot }) {
  async function copyReference() {
    const ref = `#${snapshot.case.case_number}`;
    const copied = await tryCopy(ref);
    toast[copied ? "success" : "error"](
      copied ? `Copied ${ref} to clipboard` : `Could not copy automatically — reference is ${ref}`,
    );
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button
          aria-label="More actions"
          variant="outline"
          size="icon"
          className="h-9 w-9 rounded-xl"
        >
          <MoreHorizontal />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className="z-50 w-64 rounded-xl border border-border bg-card p-1.5 shadow-panel"
        >
          <DropdownMenu.Item
            onSelect={() => void copyReference()}
            className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-xs font-medium outline-none focus:bg-accent data-[highlighted]:bg-accent"
          >
            <Copy className="h-3.5 w-3.5" /> Copy case reference
          </DropdownMenu.Item>
          <DropdownMenu.Item asChild>
            <a
              href={`/messages/${snapshot.case.id}`}
              className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-xs font-medium outline-none focus:bg-accent data-[highlighted]:bg-accent"
            >
              <MessageSquare className="h-3.5 w-3.5" /> Open conversation
            </a>
          </DropdownMenu.Item>
          <DropdownMenu.Item asChild>
            <Link
              to="/properties/$propertyId/history"
              params={{ propertyId: snapshot.property.id }}
              search={{
                address: snapshot.property.address_line,
                postcode: snapshot.property.postcode,
              }}
              className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-xs font-medium outline-none focus:bg-accent data-[highlighted]:bg-accent"
            >
              <History className="h-3.5 w-3.5" /> View property history
            </Link>
          </DropdownMenu.Item>
          <DropdownMenu.Item
            onSelect={() => exportCaseSummary(snapshot)}
            className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-xs font-medium outline-none focus:bg-accent data-[highlighted]:bg-accent"
          >
            <Download className="h-3.5 w-3.5" /> Export case summary
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

// --- Root -------------------------------------------------------------

export function CaseToolbar({ snapshot }: { snapshot: CaseSnapshot }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2")}>
      <ShareButton caseId={snapshot.case.id} />
      <EditCaseDialog snapshot={snapshot} />
      <MoreActionsMenu snapshot={snapshot} />
    </div>
  );
}
