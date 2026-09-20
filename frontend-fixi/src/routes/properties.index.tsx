import * as Dialog from "@radix-ui/react-dialog";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Building2, ChevronLeft, ChevronRight, Plus, Search, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { EmptyState, ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { PropertyPhoto } from "@/components/fixi/PropertyTabs";
import { Button } from "@/components/ui/button";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import {
  PROPERTY_TYPE_OPTIONS,
  SELECTABLE_PROPERTY_PHOTOS,
  useCreateProperty,
  useProperties,
  type CreatePropertyRequest,
} from "@/hooks/use-property";
import { titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// No zod `validateSearch` here -- same reasoning as
// properties.$propertyId.history.tsx (see that file's Route comment): a
// hard navigation to any non-"/" path here always hits the SPA's prerendered
// 404-fallback shell, and TanStack Router's search validation running
// against that mismatched shell during hydration is what froze the renderer.
// Filter state below is read from window.location.search directly and
// written back with history.replaceState, entirely outside the router's
// search machinery.
export const Route = createFileRoute("/properties/")({
  head: () => ({
    meta: [
      { title: "Properties — Fixi" },
      {
        name: "description",
        content: "Every property in this portfolio, searchable, with tenants and open cases.",
      },
    ],
  }),
  component: PropertiesPage,
});

const PAGE_SIZE = 12;

interface FilterState {
  q: string;
  includeArchived: boolean;
  offset: number;
}

function readFiltersFromUrl(): FilterState {
  if (typeof window === "undefined") return { q: "", includeArchived: false, offset: 0 };
  const params = new URLSearchParams(window.location.search);
  const offset = Number.parseInt(params.get("offset") ?? "0", 10);
  return {
    q: params.get("q") ?? "",
    includeArchived: params.get("archived") === "1",
    offset: Number.isFinite(offset) && offset > 0 ? offset : 0,
  };
}

function writeFiltersToUrl(filters: FilterState) {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.includeArchived) params.set("archived", "1");
  if (filters.offset > 0) params.set("offset", String(filters.offset));
  const qs = params.toString();
  const url = `${window.location.pathname}${qs ? `?${qs}` : ""}`;
  window.history.replaceState(null, "", url);
}

function PropertiesPage() {
  const [filters, setFilters] = useState<FilterState>(() => readFiltersFromUrl());
  const [searchInput, setSearchInput] = useState(filters.q);
  const debouncedSearch = useDebouncedValue(searchInput, 300);
  const [dialogOpen, setDialogOpen] = useState(false);

  // Debounced search text drives the actual filter/query; typing itself
  // never fires a request per keystroke.
  useEffect(() => {
    setFilters((f) => (f.q === debouncedSearch ? f : { ...f, q: debouncedSearch, offset: 0 }));
  }, [debouncedSearch]);

  useEffect(() => {
    writeFiltersToUrl(filters);
  }, [filters]);

  const properties = useProperties({
    q: filters.q,
    limit: PAGE_SIZE,
    offset: filters.offset,
    includeArchived: filters.includeArchived,
  });

  const items = properties.data?.items ?? [];
  const total = properties.data?.total ?? 0;
  const hasMore = properties.data?.has_more ?? false;
  const rangeStart = total === 0 ? 0 : filters.offset + 1;
  const rangeEnd = filters.offset + items.length;

  return (
    <AppShell>
      <div className="mx-auto max-w-[1510px] px-6 py-6 xl:px-7">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Properties</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Every property in this portfolio, its current tenants and open cases.
            </p>
          </div>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" /> New property
          </Button>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <label className="flex h-9 w-[320px] max-w-[60vw] items-center gap-2 rounded-xl border border-border bg-card px-3 text-muted-foreground shadow-card">
            <Search className="h-4 w-4 shrink-0" />
            <input
              aria-label="Search properties"
              className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
              placeholder="Search address, postcode or landlord reference…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
            {searchInput && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => setSearchInput("")}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </label>
          <label className="flex h-9 items-center gap-2 rounded-xl border border-border bg-card px-3 text-xs font-medium text-foreground shadow-card">
            <input
              type="checkbox"
              className="accent-primary"
              checked={filters.includeArchived}
              onChange={(e) =>
                setFilters((f) => ({ ...f, includeArchived: e.target.checked, offset: 0 }))
              }
            />
            Include archived (sample history)
          </label>
          {!properties.isLoading && !properties.isError && (
            <span className="text-xs text-muted-foreground">
              {total === 0 ? "No properties" : `${rangeStart}–${rangeEnd} of ${total}`}
            </span>
          )}
        </div>

        <div className="mt-5">
          {properties.isLoading && <LoadingRows rows={4} />}
          {properties.isError && (
            <ErrorState
              detail={
                properties.error instanceof Error
                  ? properties.error.message
                  : "Could not load properties."
              }
              onRetry={() => void properties.refetch()}
            />
          )}
          {!properties.isLoading && !properties.isError && items.length === 0 && (
            <EmptyState
              icon={Building2}
              title={
                filters.q || filters.includeArchived
                  ? "No matching properties"
                  : "No properties yet"
              }
              description={
                filters.q
                  ? "Try a different address, postcode or landlord reference, or clear the search."
                  : "Add the first property in this portfolio to get started."
              }
              action={
                !filters.q ? (
                  <Button onClick={() => setDialogOpen(true)}>
                    <Plus className="h-4 w-4" /> New property
                  </Button>
                ) : undefined
              }
            />
          )}

          {items.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {items.map((p) => (
                <Link
                  key={p.id}
                  to="/properties/$propertyId/history"
                  params={{ propertyId: p.id }}
                  search={{ address: p.address_line, postcode: p.postcode }}
                >
                  <Card className="flex h-full flex-col overflow-hidden transition-colors hover:bg-accent">
                    <PropertyPhoto photoKey={p.photo_key} className="h-32 w-full" />
                    <div className="flex flex-1 flex-col gap-2 p-4">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold">{p.address_line}</div>
                          <div className="text-xs text-muted-foreground">{p.postcode}</div>
                        </div>
                        {p.is_archived && (
                          <Pill tone="gray" className="shrink-0">
                            Sample
                          </Pill>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {p.property_type ? titleCase(p.property_type) : "Type unknown"}
                        {p.bedrooms != null ? ` · ${p.bedrooms} bed` : ""}
                      </div>
                      <div className="mt-auto flex items-center gap-3 pt-2 text-xs">
                        <span className="flex items-center gap-1 text-muted-foreground">
                          <Users className="h-3.5 w-3.5" /> {p.tenant_count}
                        </span>
                        <Pill tone={p.open_case_count > 0 ? "blue" : "gray"}>
                          {p.open_case_count} open
                        </Pill>
                        <span className="text-muted-foreground">
                          {p.total_case_count} total case{p.total_case_count === 1 ? "" : "s"}
                        </span>
                      </div>
                    </div>
                  </Card>
                </Link>
              ))}
            </div>
          )}

          {items.length > 0 && (
            <div className="mt-4 flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                disabled={filters.offset === 0}
                onClick={() =>
                  setFilters((f) => ({ ...f, offset: Math.max(0, f.offset - PAGE_SIZE) }))
                }
              >
                <ChevronLeft className="h-4 w-4" /> Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!hasMore}
                onClick={() => setFilters((f) => ({ ...f, offset: f.offset + PAGE_SIZE }))}
              >
                Next <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </div>

      <NewPropertyDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </AppShell>
  );
}

// UK postcode shape check (permissive on purpose -- catches obvious typos
// like a missing space or a stray letter count, not a full Royal Mail
// validation service). Matches the format described in the task brief
// ("postcode with a UK-shaped client-side check").
const UK_POSTCODE_RE = /^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$/i;

function NewPropertyDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const createProperty = useCreateProperty();
  const [addressLine, setAddressLine] = useState("");
  const [postcode, setPostcode] = useState("");
  const [landlordReference, setLandlordReference] = useState("");
  const [propertyType, setPropertyType] = useState<string>(PROPERTY_TYPE_OPTIONS[0].value);
  const [bedrooms, setBedrooms] = useState("");
  const [buildYear, setBuildYear] = useState("");
  const [accessNotes, setAccessNotes] = useState("");
  const [photoKey, setPhotoKey] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const postcodeValid = postcode.trim().length === 0 || UK_POSTCODE_RE.test(postcode.trim());
  const canSubmit =
    addressLine.trim().length > 0 &&
    postcode.trim().length > 0 &&
    UK_POSTCODE_RE.test(postcode.trim()) &&
    landlordReference.trim().length > 0;

  function reset() {
    setAddressLine("");
    setPostcode("");
    setLandlordReference("");
    setPropertyType(PROPERTY_TYPE_OPTIONS[0].value);
    setBedrooms("");
    setBuildYear("");
    setAccessNotes("");
    setPhotoKey(null);
    setTouched(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!canSubmit) return;
    const body: CreatePropertyRequest = {
      address_line: addressLine.trim(),
      postcode: postcode.trim().toUpperCase(),
      landlord_reference: landlordReference.trim(),
      property_type: propertyType || null,
      bedrooms: bedrooms.trim() ? Number.parseInt(bedrooms, 10) : null,
      build_year: buildYear.trim() ? Number.parseInt(buildYear, 10) : null,
      access_notes: accessNotes.trim() || null,
      photo_key: photoKey,
    };
    try {
      await createProperty.mutateAsync(body);
      reset();
      onOpenChange(false);
    } catch {
      // handled by onError toast in use-property.ts; keep the dialog open
      // with the operator's input intact so they can fix and retry.
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/20" />
        <Dialog.Content
          onEscapeKeyDown={() => onOpenChange(false)}
          className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-full max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-border bg-card p-6 shadow-panel"
        >
          <div className="flex items-start justify-between">
            <div>
              <Dialog.Title className="text-sm font-semibold text-foreground">
                New property
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-muted-foreground">
                Add a property to the portfolio.
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

          <form onSubmit={(e) => void handleSubmit(e)}>
            <Field label="Address" htmlFor="np-address">
              <input
                id="np-address"
                autoFocus
                className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                value={addressLine}
                onChange={(e) => setAddressLine(e.target.value)}
                placeholder="e.g. 14 King Street"
              />
              {touched && addressLine.trim().length === 0 && (
                <p className="mt-1 text-[11px] text-destructive">Address is required.</p>
              )}
            </Field>

            <Field label="Postcode" htmlFor="np-postcode">
              <input
                id="np-postcode"
                className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                value={postcode}
                onChange={(e) => setPostcode(e.target.value)}
                placeholder="e.g. E17 6QX"
              />
              {!postcodeValid && (
                <p className="mt-1 text-[11px] text-destructive">
                  That doesn't look like a UK postcode.
                </p>
              )}
              {touched && postcode.trim().length === 0 && (
                <p className="mt-1 text-[11px] text-destructive">Postcode is required.</p>
              )}
            </Field>

            <Field label="Landlord reference" htmlFor="np-landlord-ref">
              <input
                id="np-landlord-ref"
                className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                value={landlordReference}
                onChange={(e) => setLandlordReference(e.target.value)}
                placeholder="e.g. LDN-0192"
              />
              {touched && landlordReference.trim().length === 0 && (
                <p className="mt-1 text-[11px] text-destructive">Landlord reference is required.</p>
              )}
            </Field>

            <div className="mt-3 grid grid-cols-2 gap-3">
              <Field label="Type" htmlFor="np-type">
                <select
                  id="np-type"
                  className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                  value={propertyType}
                  onChange={(e) => setPropertyType(e.target.value)}
                >
                  {PROPERTY_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Bedrooms" htmlFor="np-bedrooms">
                <input
                  id="np-bedrooms"
                  type="number"
                  min={0}
                  max={20}
                  className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                  value={bedrooms}
                  onChange={(e) => setBedrooms(e.target.value)}
                  placeholder="—"
                />
              </Field>
            </div>

            <Field label="Build year" htmlFor="np-build-year">
              <input
                id="np-build-year"
                type="number"
                min={1800}
                max={new Date().getFullYear()}
                className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                value={buildYear}
                onChange={(e) => setBuildYear(e.target.value)}
                placeholder="—"
              />
            </Field>

            <Field label="Access notes" htmlFor="np-access-notes">
              <textarea
                id="np-access-notes"
                className="mt-1.5 h-16 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring"
                value={accessNotes}
                onChange={(e) => setAccessNotes(e.target.value)}
                placeholder="e.g. key safe code, entry restrictions"
              />
            </Field>

            <fieldset className="mt-3">
              <legend className="block text-xs font-medium text-muted-foreground">Photo</legend>
              <div className="mt-1.5 grid grid-cols-4 gap-2">
                <button
                  type="button"
                  aria-label="No photo"
                  onClick={() => setPhotoKey(null)}
                  className={cn(
                    "overflow-hidden rounded-lg border-2",
                    photoKey === null ? "border-primary" : "border-transparent",
                  )}
                >
                  <PropertyPhoto photoKey={null} className="h-12 w-full" />
                </button>
                {SELECTABLE_PROPERTY_PHOTOS.map((photo) => (
                  <button
                    key={photo.key}
                    type="button"
                    aria-label={`Use photo ${photo.key}`}
                    onClick={() => setPhotoKey(photo.key)}
                    className={cn(
                      "overflow-hidden rounded-lg border-2",
                      photoKey === photo.key ? "border-primary" : "border-transparent",
                    )}
                  >
                    <img src={photo.src} alt="" className="h-12 w-full object-cover" />
                  </button>
                ))}
              </div>
            </fieldset>

            <button
              type="submit"
              disabled={createProperty.isPending}
              className="mt-5 flex h-9 w-full items-center justify-center rounded-lg bg-primary text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {createProperty.isPending ? "Adding…" : "Add property"}
            </button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-3">
      <label className="block text-xs font-medium text-muted-foreground" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
    </div>
  );
}
