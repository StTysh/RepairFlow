import * as Dialog from "@radix-ui/react-dialog";
import { Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useCreateTicket, useSeedRefs } from "@/hooks/use-new-ticket";

/** "+ New Ticket" -- creates a real case via POST /api/v1/demo/intake. The
 * operator picks which seeded property/tenant it's reported against (GET
 * /api/v1/demo/seed-refs now returns every seeded property, not just one),
 * defaulting to the original hero-path property so the rehearsed demo
 * flow's default behaviour doesn't change. Deliberately minimal beyond
 * that picker -- per the "don't over-build this" guidance; no
 * safety-answers UI, no availability picker.
 *
 * Built directly on @radix-ui/react-dialog (already a dependency, no
 * shadcn Dialog wrapper exists yet under components/fixi) rather than a
 * blocking window.prompt(), since this is the one flow in this phase with
 * more than one field to fill in. */
export function NewTicketDialog() {
  const [open, setOpen] = useState(false);
  const [propertyId, setPropertyId] = useState<string | null>(null);
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const seedRefs = useSeedRefs();
  const createTicket = useCreateTicket();

  // Default to the original hero-path property once refs load, unless the
  // operator has already picked something else.
  useEffect(() => {
    if (seedRefs.data && propertyId === null) {
      setPropertyId(seedRefs.data.property_id);
    }
  }, [seedRefs.data, propertyId]);

  const selected = seedRefs.data?.properties.find((p) => p.property_id === propertyId) ?? null;
  const canSubmit =
    location.trim().length > 0 && description.trim().length > 0 && !!seedRefs.data && !!selected;

  function reset() {
    setLocation("");
    setDescription("");
    setPropertyId(seedRefs.data?.property_id ?? null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    try {
      await createTicket.mutateAsync({
        property_id: selected.property_id,
        tenant_id: selected.tenant_id,
        description: description.trim(),
        location: location.trim(),
        source_text: description.trim(),
      });
      reset();
      setOpen(false);
    } catch {
      // handled by onError toast (see use-new-ticket.ts); keep the dialog
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
        <button className="flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-sm font-medium text-primary-foreground shadow-card transition-colors hover:bg-primary/90">
          <Plus className="h-4 w-4" /> New Ticket
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/20" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-6 shadow-panel">
          <div className="flex items-start justify-between">
            <div>
              <Dialog.Title className="text-sm font-semibold text-foreground">
                New maintenance ticket
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-muted-foreground">
                Pick a property and reported issue. A case is created immediately.
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
            <label
              className="mt-4 block text-xs font-medium text-muted-foreground"
              htmlFor="new-ticket-property"
            >
              Property
            </label>
            <select
              id="new-ticket-property"
              className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
              value={propertyId ?? ""}
              onChange={(e) => setPropertyId(e.target.value)}
              disabled={!seedRefs.data}
            >
              {(seedRefs.data?.properties ?? []).map((p) => (
                <option key={p.property_id} value={p.property_id}>
                  {p.address_line}
                </option>
              ))}
            </select>

            <label
              className="mt-3 block text-xs font-medium text-muted-foreground"
              htmlFor="new-ticket-location"
            >
              Location
            </label>
            <input
              id="new-ticket-location"
              className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. rear bedroom ceiling"
              autoFocus
            />

            <label
              className="mt-3 block text-xs font-medium text-muted-foreground"
              htmlFor="new-ticket-description"
            >
              What's the issue?
            </label>
            <textarea
              id="new-ticket-description"
              className="mt-1.5 h-24 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what's wrong, as reported by the tenant"
            />

            {seedRefs.isError && (
              <p className="mt-3 text-xs text-destructive">
                Could not load the demo property. Is the backend running?
              </p>
            )}

            <button
              type="submit"
              disabled={!canSubmit || createTicket.isPending}
              className="mt-5 flex h-9 w-full items-center justify-center rounded-lg bg-primary text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {createTicket.isPending ? "Creating…" : "Create ticket"}
            </button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
