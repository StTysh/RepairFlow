/**
 * The pure arithmetic behind <Metric>, split out so it can be tested.
 *
 * vitest runs in a `node` environment over `src/**\/*.test.ts` only, so a
 * component test is not available here -- but every defect this code has
 * actually produced was arithmetic, not rendering, and arithmetic is
 * exactly what this file exposes.
 */

export interface ParsedMetric {
  prefix: string;
  value: number;
  decimals: boolean;
  grouped: boolean;
  suffix: string;
}

/** The first run of digits, with optional sign, grouping and one decimal part. */
const NUMERIC = /-?\d[\d,]*(?:\.\d+)?/;

/** Split a formatted display string into an animatable number plus its trimmings. */
export function parseMetric(display: string): ParsedMetric | null {
  const match = NUMERIC.exec(display);
  if (!match) return null;
  const raw = match[0];
  const value = Number(raw.replace(/,/g, ""));
  if (!Number.isFinite(value)) return null;
  return {
    prefix: display.slice(0, match.index),
    value,
    decimals: raw.includes("."),
    grouped: raw.includes(","),
    suffix: display.slice(match.index + raw.length),
  };
}

/** Re-render an interpolated number in the same shape it was parsed from. */
export function renderMetric(n: number, p: ParsedMetric): string {
  const digits = p.decimals ? 1 : 0;
  // Anything that ROUNDS to zero is displayed as zero, sign discarded.
  // Testing `n === 0` is not enough: toFixed keeps the sign of a small
  // negative, so -0.0004 prints "-0" and -0.04 prints "-0.0". Both are
  // strings that actually reached the live dashboard.
  const safe = Number(n.toFixed(digits)) === 0 ? 0 : n;
  const body = p.grouped
    ? safe.toLocaleString("en-GB", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
    : safe.toFixed(digits);
  return `${p.prefix}${body}${p.suffix}`;
}

/**
 * Elapsed time as a 0..1 progress value.
 *
 * Clamped at BOTH ends. requestAnimationFrame hands its callback the
 * timestamp of the frame the callback belongs to, and that can predate
 * the performance.now() captured when the frame was requested -- so
 * `now - started` is negative on the first frame. Unclamped, the cubic
 * ease below returns a negative multiplier and the counter renders "-0"
 * and "-0.6h" before correcting itself. Observed in Chrome on the live
 * dashboard, not hypothetical.
 */
export function progress(now: number, started: number, durationMs: number): number {
  if (durationMs <= 0) return 1;
  return Math.min(1, Math.max(0, (now - started) / durationMs));
}

/** Matches --ease-fixi-out, so the count and the flash read as one gesture. */
export function easeOut(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** The value to display at a given progress. */
export function interpolate(from: number, to: number, t: number): number {
  return t === 1 ? to : from + (to - from) * easeOut(t);
}
