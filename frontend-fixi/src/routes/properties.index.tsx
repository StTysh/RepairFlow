import { createFileRoute, Link } from "@tanstack/react-router";
import { Building2, MapPin, User } from "lucide-react";
import { AppShell, Card } from "@/components/fixi/AppShell";
import { useSeedRefs } from "@/hooks/use-new-ticket";

export const Route = createFileRoute("/properties/")({
  head: () => ({
    meta: [
      { title: "Properties — Fixi" },
      { name: "description", content: "Every property in this portfolio and their tenants." },
    ],
  }),
  component: PropertiesPage,
});

function PropertiesPage() {
  const seedRefs = useSeedRefs();
  const properties = seedRefs.data?.properties ?? [];

  return (
    <AppShell>
      <div className="px-8 py-6">
        <h1 className="text-2xl font-bold tracking-tight">Properties</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every property in this portfolio and their current tenant.
        </p>

        {seedRefs.isLoading && <p className="mt-6 text-sm text-muted-foreground">Loading…</p>}
        {seedRefs.isError && (
          <p className="mt-6 text-sm text-destructive">Could not load properties.</p>
        )}

        <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {properties.map((p) => (
            <Link
              key={p.property_id}
              to="/properties/$propertyId/history"
              params={{ propertyId: p.property_id }}
            >
              <Card className="h-full p-4 transition-colors hover:bg-accent">
                <div className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent">
                    <Building2 className="h-4 w-4" />
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">{p.address_line}</div>
                    <div className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                      <MapPin className="h-3 w-3 shrink-0" />
                      {p.postcode}
                    </div>
                    <div className="mt-1.5 flex items-center gap-1 text-xs text-muted-foreground">
                      <User className="h-3 w-3 shrink-0" />
                      {p.tenant_name}
                    </div>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
