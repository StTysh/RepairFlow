import { Link } from "@tanstack/react-router";
import { ArrowLeft, Bed, Building2, Calendar, PencilLine, Users } from "lucide-react";
import { Pill } from "@/components/fixi/Badge";
import { LoadingRows } from "@/components/fixi/EmptyState";
import { resolvePropertyPhoto, useProperty } from "@/hooks/use-property";
import { titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

type PropertyTabKey = "history" | "details" | "documents" | "notes";

/** photo_key -> real `<img>`, or a plain icon tile for null/unknown --
 * shared by this header, the properties grid and the details tab's photo
 * picker/read view, so "no photo on file" always renders identically
 * (never a real photo of a different building standing in for it). */
export function PropertyPhoto({
  photoKey,
  className,
}: {
  photoKey: string | null | undefined;
  className?: string;
}) {
  const src = resolvePropertyPhoto(photoKey);
  if (!src) {
    return (
      <div
        className={cn("flex items-center justify-center bg-muted text-muted-foreground", className)}
      >
        <Building2 className="h-5 w-5" strokeWidth={1.6} />
      </div>
    );
  }
  return (
    <img src={src} alt="" width={912} height={736} className={cn("object-cover", className)} />
  );
}

/** Shared header (photo, address, key facts, Edit) + 4-way tab bar for every
 * `/properties/$propertyId/*` screen. Matches maintenance.tickets'
 * SectionLink pattern: the URL is the source of truth for which tab is
 * active (real routes, not local useState), so back/forward and deep links
 * both just work for free.
 *
 * GET /api/v1/properties/{id} doesn't exist on the backend yet in this
 * session (another agent is adding it alongside the other properties
 * routes) -- `fallbackAddress`/`fallbackPostcode` let a caller that already
 * knows the address (a Link that passed it via `search`, same convention
 * the old history-only version of this screen used) keep the header
 * meaningful while that 404s, instead of showing only the raw id. */
export function PropertyTabs({
  propertyId,
  active,
  fallbackAddress,
  fallbackPostcode,
  children,
}: {
  propertyId: string;
  active: PropertyTabKey;
  fallbackAddress?: string | undefined;
  fallbackPostcode?: string | undefined;
  children: React.ReactNode;
}) {
  const property = useProperty(propertyId);
  const p = property.data;
  // Forwarded onto every tab Link below so switching tabs doesn't lose the
  // fallback address/postcode while /properties/{id} is unavailable.
  // Spread (never passed as `search={maybeUndefined}`) because the
  // project's `exactOptionalPropertyTypes: true` treats an explicit
  // `search={undefined}` as a type error distinct from omitting the prop.
  const searchLinkProps =
    fallbackAddress !== undefined
      ? { search: { address: fallbackAddress, postcode: fallbackPostcode } }
      : {};

  return (
    <div className="mx-auto max-w-page px-6 py-4 xl:px-7">
      <Link
        to="/properties"
        className="flex w-fit items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> All properties
      </Link>

      {property.isLoading ? (
        <div className="mt-4">
          <LoadingRows rows={2} />
        </div>
      ) : property.isError || !p ? (
        <div className="mt-3">
          <h1 className="text-title font-bold leading-tight">Property</h1>
          <p className="text-strong text-muted-foreground">
            {fallbackAddress
              ? `${fallbackAddress}${fallbackPostcode ? `, ${fallbackPostcode}` : ""}`
              : propertyId}
          </p>
          {property.isError && (
            <p className="mt-2 text-xs text-destructive">
              Could not load the full property record
              {property.error instanceof Error ? ` (${property.error.message})` : ""}. Showing
              what's known from the page you came from.
            </p>
          )}
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div className="flex items-start gap-4">
            <PropertyPhoto photoKey={p.photo_key} className="h-[72px] w-32 shrink-0 rounded-lg" />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-title font-bold leading-tight">{p.address_line}</h1>
                {p.is_archived && <Pill tone="gray">Sample history</Pill>}
              </div>
              <p className="text-strong text-muted-foreground">{p.postcode}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                {p.property_type && (
                  <span className="flex items-center gap-1">
                    <Building2 className="h-3 w-3" /> {titleCase(p.property_type)}
                  </span>
                )}
                {p.bedrooms != null && (
                  <span className="flex items-center gap-1">
                    <Bed className="h-3 w-3" /> {p.bedrooms} bed
                  </span>
                )}
                {p.build_year != null && (
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" /> Built {p.build_year}
                  </span>
                )}
                <span className="flex items-center gap-1">
                  <Users className="h-3 w-3" /> {p.tenant_count} tenant
                  {p.tenant_count === 1 ? "" : "s"}
                </span>
                <span>
                  {p.open_case_count} open of {p.total_case_count} case
                  {p.total_case_count === 1 ? "" : "s"}
                </span>
              </div>
            </div>
          </div>
          <Link
            to="/properties/$propertyId/details"
            params={{ propertyId }}
            title={
              p.is_archived
                ? "Sample-history properties can't be edited"
                : "Edit this property's details"
            }
            className={cn(
              "flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-xs font-medium shadow-card transition-colors",
              p.is_archived ? "pointer-events-none opacity-50" : "hover:bg-accent",
            )}
            aria-disabled={p.is_archived}
          >
            <PencilLine className="h-3.5 w-3.5" /> Edit
          </Link>
        </div>
      )}

      <div className="mt-4 flex gap-6 border-b border-border text-sm">
        <Link
          to="/properties/$propertyId/history"
          params={{ propertyId }}
          {...searchLinkProps}
          className={cn(
            "-mb-px border-b-2 pb-2.5 font-medium transition-colors",
            active === "history"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Maintenance history
        </Link>
        <Link
          to="/properties/$propertyId/details"
          params={{ propertyId }}
          {...searchLinkProps}
          className={cn(
            "-mb-px border-b-2 pb-2.5 font-medium transition-colors",
            active === "details"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Property details
        </Link>
        <Link
          to="/properties/$propertyId/documents"
          params={{ propertyId }}
          {...searchLinkProps}
          className={cn(
            "-mb-px border-b-2 pb-2.5 font-medium transition-colors",
            active === "documents"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Documents
        </Link>
        <Link
          to="/properties/$propertyId/notes"
          params={{ propertyId }}
          {...searchLinkProps}
          className={cn(
            "-mb-px border-b-2 pb-2.5 font-medium transition-colors",
            active === "notes"
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          Notes
        </Link>
      </div>

      <div className="mt-3">{children}</div>
    </div>
  );
}
