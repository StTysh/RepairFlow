import { createFileRoute, redirect } from "@tanstack/react-router";

// Bare `/properties/$propertyId` (no tab) isn't a screen of its own -- it
// just lands on the history tab, the same default the old single-file
// version of this screen had. `beforeLoad` (not `loader`) so this redirects
// before any data fetch would fire, rather than firing one it immediately
// discards.
export const Route = createFileRoute("/properties/$propertyId/")({
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/properties/$propertyId/history",
      params: { propertyId: params.propertyId },
    });
  },
});
