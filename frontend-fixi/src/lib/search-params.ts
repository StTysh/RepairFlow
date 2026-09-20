/**
 * Tolerant readers for URL query values.
 *
 * TanStack Router's default search serialiser JSON-encodes the values it
 * writes, so `navigate({ search: { include_archived: "true" } })` lands in
 * the address bar as `?include_archived=%22true%22` -- the quotes are part
 * of the value. A reader doing `params.get(key) === "true"` then never
 * matches, and the control silently does nothing: the URL changes, the
 * checkbox ticks, and the data does not move. That is exactly the class of
 * "enabled control that quietly does nothing" this app is not allowed to
 * ship, and it is invisible in a type check.
 *
 * Rather than fight the serialiser (and rather than each screen inventing
 * its own workaround), every screen reads through here.
 */

/** A query value with any JSON quoting the router added stripped off. */
export function readParam(
  // Nullable because a caller reading `window.location.search` during a
  // prerender pass has no location to read from.
  params: URLSearchParams | null | undefined,
  key: string,
): string | undefined {
  const raw = params?.get(key) ?? null;
  if (raw === null || raw === "") return undefined;
  if (raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"')) {
    return raw.slice(1, -1);
  }
  return raw;
}

/** A boolean flag. Accepts `true`, `"true"`, `1` and `"1"`, so it survives
 * both the router's serialiser and a hand-typed URL. */
export function readFlag(params: URLSearchParams | null | undefined, key: string): boolean {
  const value = readParam(params, key);
  return value === "true" || value === "1";
}

/** An integer, or the fallback when absent or unparseable. */
export function readInt(
  params: URLSearchParams | null | undefined,
  key: string,
  fallback: number,
): number {
  const value = readParam(params, key);
  if (value === undefined) return fallback;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}
