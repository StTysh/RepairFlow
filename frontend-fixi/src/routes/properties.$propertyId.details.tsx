import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { Pill } from "@/components/fixi/Badge";
import { ErrorState, LoadingRows } from "@/components/fixi/EmptyState";
import { SkeletonCards } from "@/components/fixi/Skeleton";
import { PropertyPhoto, PropertyTabs } from "@/components/fixi/PropertyTabs";
import { Button } from "@/components/ui/button";
import { usePropertyHistory } from "@/hooks/use-property-history";
import {
  PROPERTY_TYPE_OPTIONS,
  ROOF_RESPONSIBILITY_OPTIONS,
  SELECTABLE_PROPERTY_PHOTOS,
  useProperty,
  useUpdateProperty,
  type PropertyDetail,
  type RoofResponsibility,
  type UpdatePropertyRequest,
} from "@/hooks/use-property";
import { statusTone, STATUS_LABEL } from "@/lib/fixi-data";
import { titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

// Same "no validateSearch" reasoning as history.tsx -- this route reads
// nothing from search itself, but shares the file family, so it keeps the
// same convention rather than being the one exception.
export const Route = createFileRoute("/properties/$propertyId/details")({
  head: () => ({
    meta: [
      { title: "Property details — Fixi" },
      { name: "description", content: "Every stored field for this property, and its tenants." },
    ],
  }),
  component: DetailsPage,
});

const roofResponsibilityLabel: Record<RoofResponsibility, string> = {
  LANDLORD: "Landlord",
  OTHER: "Other",
  UNKNOWN: "Unknown",
};

// Cases still open enough to matter on this tab -- everything except the two
// terminal statuses. Mirrors the strict ACTIVE-only reading used elsewhere
// (DashboardMetrics) being too narrow for this purpose: AWAITING_CONFIRMATION
// and ESCALATED cases are still "open" work at this property.
const OPEN_STATUSES = new Set(["ACTIVE", "AWAITING_CONFIRMATION", "ESCALATED"]);

function DetailsPage() {
  const { propertyId } = Route.useParams();
  const searchParams =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const address = searchParams?.get("address") ?? undefined;
  const postcode = searchParams?.get("postcode") ?? undefined;

  const property = useProperty(propertyId);
  const history = usePropertyHistory(propertyId);
  const openCases = (history.data?.items ?? []).filter((h) => OPEN_STATUSES.has(h.status));
  const [editing, setEditing] = useState(false);

  return (
    <AppShell>
      <PropertyTabs
        propertyId={propertyId}
        active="details"
        fallbackAddress={address}
        fallbackPostcode={postcode}
      >
        {property.isLoading && <LoadingRows rows={5} />}
        {property.isError && (
          <ErrorState
            {...(property.error instanceof Error ? { detail: property.error.message } : {})}
            onRetry={() => void property.refetch()}
          />
        )}
        {!property.isLoading && !property.isError && property.data && (
          <div className="grid gap-3 xl:grid-cols-3">
            <Card className="p-5 xl:col-span-2">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-section font-semibold">Property details</h2>
                {!editing && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={property.data.is_archived}
                    title={
                      property.data.is_archived
                        ? "Sample-history properties can't be edited"
                        : undefined
                    }
                    onClick={() => setEditing(true)}
                  >
                    Edit
                  </Button>
                )}
              </div>
              {property.data.is_archived && (
                <p className="mt-2 rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
                  This property was created from the synthetic sample-history archive. Its records
                  are illustrative, not a real portfolio entry, and can't be edited.
                </p>
              )}
              {editing ? (
                <EditPropertyForm property={property.data} onDone={() => setEditing(false)} />
              ) : (
                <ReadOnlyDetails property={property.data} />
              )}
            </Card>

            <div className="flex flex-col gap-3">
              <Card className="p-5">
                <h2 className="text-section font-semibold">
                  Tenants ({property.data.tenants.length})
                </h2>
                {property.data.tenants.length === 0 ? (
                  <p className="mt-2 text-xs text-muted-foreground">No tenants on file.</p>
                ) : (
                  <ul className="mt-2 divide-y divide-border">
                    {property.data.tenants.map((t) => (
                      <li key={t.id} className="py-2.5">
                        <Link
                          to="/tenants/$tenantId"
                          params={{ tenantId: t.id }}
                          className="text-strong font-medium hover:underline"
                        >
                          {t.display_name}
                        </Link>
                        {/* TenantSummary now carries the contact fields, so
                         * this shows what is actually on record. It used to
                         * read "No contact on file" for every tenant --
                         * asserting an absence from a projection that simply
                         * did not include the fields. Only say it when both
                         * are genuinely null. */}
                        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <Pill tone={t.contact_allowed ? "green" : "red"}>
                            {t.contact_allowed ? "Contact allowed" : "Contact not allowed"}
                          </Pill>
                          {t.phone_e164 && <span>{t.phone_e164}</span>}
                          {t.email && <span>{t.email}</span>}
                          {!t.phone_e164 && !t.email && <span>No contact details on record</span>}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              <Card className="p-5">
                <h2 className="text-section font-semibold">Open cases ({openCases.length})</h2>
                {history.isLoading && <SkeletonCards className="mt-2" count={3} height="h-12" />}
                {history.isError && (
                  <p className="mt-2 text-xs text-destructive">Could not load cases.</p>
                )}
                {!history.isLoading && !history.isError && openCases.length === 0 && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    No open cases at this property.
                  </p>
                )}
                {openCases.length > 0 && (
                  <ul className="mt-2 divide-y divide-border">
                    {openCases.map((c) => (
                      <li key={c.case_id} className="py-2">
                        <Link
                          to="/maintenance/tickets/$ticketId/{-$section}"
                          params={{ ticketId: c.case_id, section: undefined }}
                          className="flex items-center justify-between gap-2 text-xs hover:underline"
                        >
                          <span className="min-w-0 flex-1 truncate font-medium">{c.title}</span>
                          <Pill tone={statusTone(c.status)}>
                            {STATUS_LABEL[c.status] ?? c.status}
                          </Pill>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          </div>
        )}
      </PropertyTabs>
    </AppShell>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-strong">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

function ReadOnlyDetails({ property: p }: { property: PropertyDetail }) {
  return (
    <div className="mt-2 divide-y divide-border">
      <DetailRow label="Address" value={p.address_line} />
      <DetailRow label="Postcode" value={p.postcode} />
      <DetailRow label="Landlord reference" value={p.landlord_reference || "—"} />
      <DetailRow label="Type" value={p.property_type ? titleCase(p.property_type) : "Unknown"} />
      <DetailRow label="Bedrooms" value={p.bedrooms ?? "—"} />
      <DetailRow label="Build year" value={p.build_year ?? "Unknown"} />
      <DetailRow label="Timezone" value={p.timezone} />
      <DetailRow
        label="Roof responsibility"
        value={roofResponsibilityLabel[p.roof_responsibility]}
      />
      <DetailRow label="Access notes" value={p.access_notes || "No access notes recorded."} />
      <DetailRow
        label="Photo"
        value={<PropertyPhoto photoKey={p.photo_key} className="ml-auto h-10 w-16 rounded" />}
      />
    </div>
  );
}

function EditPropertyForm({
  property: p,
  onDone,
}: {
  property: PropertyDetail;
  onDone: () => void;
}) {
  const updateProperty = useUpdateProperty(p.id);
  const [addressLine, setAddressLine] = useState(p.address_line);
  const [postcode, setPostcode] = useState(p.postcode);
  const [landlordReference, setLandlordReference] = useState(p.landlord_reference);
  const [propertyType, setPropertyType] = useState(p.property_type ?? "");
  const [bedrooms, setBedrooms] = useState(p.bedrooms?.toString() ?? "");
  const [buildYear, setBuildYear] = useState(p.build_year?.toString() ?? "");
  const [timezone, setTimezone] = useState(p.timezone);
  const [roofResponsibility, setRoofResponsibility] = useState<RoofResponsibility>(
    p.roof_responsibility,
  );
  const [accessNotes, setAccessNotes] = useState(p.access_notes ?? "");
  const [photoKey, setPhotoKey] = useState<string | null>(p.photo_key);

  // Escape cancels the form, matching the app's dialog convention.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onDone();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onDone]);

  const canSubmit = addressLine.trim().length > 0 && postcode.trim().length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    const body: UpdatePropertyRequest = {
      address_line: addressLine.trim(),
      postcode: postcode.trim().toUpperCase(),
      landlord_reference: landlordReference.trim(),
      property_type: propertyType || null,
      bedrooms: bedrooms.trim() ? Number.parseInt(bedrooms, 10) : null,
      build_year: buildYear.trim() ? Number.parseInt(buildYear, 10) : null,
      // Spread, not `timezone: timezone.trim() || undefined` -- the target
      // type's `timezone?: string` rejects an explicit `undefined` under
      // this project's `exactOptionalPropertyTypes: true`.
      ...(timezone.trim() ? { timezone: timezone.trim() } : {}),
      roof_responsibility: roofResponsibility,
      access_notes: accessNotes.trim() || null,
      photo_key: photoKey,
    };
    try {
      await updateProperty.mutateAsync(body);
      onDone();
    } catch {
      // handled by onError toast in use-property.ts
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="mt-3">
      <div className="grid grid-cols-2 gap-3">
        <LabeledInput
          id="edit-address"
          label="Address"
          value={addressLine}
          onChange={setAddressLine}
        />
        <LabeledInput id="edit-postcode" label="Postcode" value={postcode} onChange={setPostcode} />
        <LabeledInput
          id="edit-landlord-ref"
          label="Landlord reference"
          value={landlordReference}
          onChange={setLandlordReference}
        />
        <div>
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="edit-type">
            Type
          </label>
          <select
            id="edit-type"
            className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            value={propertyType}
            onChange={(e) => setPropertyType(e.target.value)}
          >
            <option value="">Unknown</option>
            {PROPERTY_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <LabeledInput
          id="edit-bedrooms"
          label="Bedrooms"
          value={bedrooms}
          onChange={setBedrooms}
          type="number"
        />
        <LabeledInput
          id="edit-build-year"
          label="Build year"
          value={buildYear}
          onChange={setBuildYear}
          type="number"
        />
        <LabeledInput id="edit-timezone" label="Timezone" value={timezone} onChange={setTimezone} />
        <div>
          <label
            className="block text-xs font-medium text-muted-foreground"
            htmlFor="edit-roof-responsibility"
          >
            Roof responsibility
          </label>
          <select
            id="edit-roof-responsibility"
            className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            value={roofResponsibility}
            onChange={(e) => setRoofResponsibility(e.target.value as RoofResponsibility)}
          >
            {ROOF_RESPONSIBILITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-3">
        <label
          className="block text-xs font-medium text-muted-foreground"
          htmlFor="edit-access-notes"
        >
          Access notes
        </label>
        <textarea
          id="edit-access-notes"
          className="mt-1.5 h-16 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          value={accessNotes}
          onChange={(e) => setAccessNotes(e.target.value)}
        />
      </div>

      <fieldset className="mt-3">
        <legend className="block text-xs font-medium text-muted-foreground">Photo</legend>
        <div className="mt-1.5 grid grid-cols-6 gap-2">
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

      <div className="mt-4 flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={!canSubmit || updateProperty.isPending}>
          {updateProperty.isPending ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}

function LabeledInput({
  id,
  label,
  value,
  onChange,
  type = "text",
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-muted-foreground" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type={type}
        className="mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
