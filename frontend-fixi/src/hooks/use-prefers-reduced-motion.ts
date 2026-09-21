import { useSyncExternalStore } from "react";

/**
 * Whether the operator has asked their OS to reduce motion.
 *
 * The CSS side of this is handled globally in styles.css, which clamps
 * every animation and transition to 1ms under the media query. This hook
 * exists for the cases CSS cannot reach:
 *
 *   - animations driven by JS state (the KPI count-up, which interpolates
 *     a *number*, not a style -- clamping its duration would leave the
 *     final digits mid-count);
 *   - View Transitions, where the meaningful choice is not to start the
 *     transition at all rather than to run a 1ms one;
 *   - decorative elements that should not merely animate faster but not
 *     render, like the pulsing ring behind the agent indicator.
 *
 * `useSyncExternalStore` rather than useState+useEffect so it is
 * subscribed: the value updates if the preference is toggled while the
 * app is open, and it is SSR/hydration-safe by construction.
 */

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void): () => void {
  // matchMedia is absent in the `node` test environment (vitest.config.ts
  // sets environment: "node"), so this stays defensive rather than
  // assuming a DOM.
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {};
  }
  const mql = window.matchMedia(QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

function getSnapshot(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia(QUERY).matches;
}

/** The server/prerender answer: assume motion is fine, then correct on mount. */
function getServerSnapshot(): boolean {
  return false;
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
