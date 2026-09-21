import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";

/** How deep a path is, ignoring trailing slashes. */
function depth(pathname: string): number {
  return pathname.split("/").filter(Boolean).length;
}

function matches(query: string): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(query).matches;
}

/**
 * Cross-document-style transitions between routes.
 *
 * The direction is derived from path depth rather than from browser
 * history: going from /maintenance to /maintenance/tickets/42 should read
 * as moving inward whether the operator got there by clicking a row or by
 * pressing Forward, and the reverse should read as coming back out.
 * Same-depth moves (Maintenance -> Properties) are lateral and get a
 * plain cross-fade, because neither one contains the other.
 *
 * Returning `false` skips the transition entirely -- TanStack calls the
 * update function directly and never touches `startViewTransition`. Two
 * cases need that:
 *
 *   - **Reduced motion.** styles.css also neutralises the
 *     ::view-transition animations, but not starting one at all is both
 *     cheaper and more honest, and deciding it here means the preference
 *     is re-read on every navigation rather than once at startup.
 *   - **A document that is not visible.** Chrome aborts a transition
 *     started in a hidden document and rejects the transition's `ready`
 *     promise. TanStack never attaches to that promise, so the rejection
 *     is unhandled and lands in the console as
 *     `InvalidStateError: Transition was aborted ... Document hidden`
 *     -- observed while driving the app in a backgrounded tab. The
 *     navigation itself completes either way; this just keeps the
 *     console clean for anyone who switches tabs mid-navigation.
 *
 * The CSS lives in styles.css under ::view-transition-*.
 */
const viewTransitionTypes = ({
  fromLocation,
  toLocation,
}: {
  fromLocation?: { pathname: string } | undefined;
  toLocation: { pathname: string };
}): string[] | false => {
  if (matches("(prefers-reduced-motion: reduce)")) return false;
  if (typeof document !== "undefined" && document.visibilityState !== "visible") return false;
  if (!fromLocation) return ["lateral"];
  const from = depth(fromLocation.pathname);
  const to = depth(toLocation.pathname);
  if (to > from) return ["forward"];
  if (to < from) return ["back"];
  return ["lateral"];
};

export const getRouter = () => {
  const queryClient = new QueryClient();

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
    defaultViewTransition: { types: viewTransitionTypes },
  });

  return router;
};
