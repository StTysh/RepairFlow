/**
 * Pounds-in-a-text-field <-> integer pence, entirely by string handling --
 * never `Math.round(pounds * 100)` on a raw float, per the task
 * instructions and backend/app/api/costs.py's own "always pence" rule.
 *
 * Originated in CostsPanel.tsx (the cost-entry form); extracted here so it
 * is importable and testable as a plain function rather than a
 * component-file-local helper.
 */

/** Mirrors `_validate_amount` in backend/app/api/costs.py: every kind
 * rejects zero (that check lives in the caller, not here -- this returns
 * `0`, never `null`, for the string `"0"`); only QUOTE/INVOICE
 * additionally reject a negative amount -- ADJUSTMENT is a signed
 * correction and must be allowed to go either way, which is what
 * `allowNegative` controls. Returns `null` for anything that isn't a
 * plain (optionally signed) decimal with at most two fraction digits. */
export function parsePoundsToPence(raw: string, allowNegative: boolean): number | null {
  const trimmed = raw.trim();
  const re = allowNegative ? /^-?\d+(\.\d{1,2})?$/ : /^\d+(\.\d{1,2})?$/;
  if (!re.test(trimmed)) return null;
  const negative = trimmed.startsWith("-");
  const unsigned = negative ? trimmed.slice(1) : trimmed;
  const [poundsPart = "0", penceRaw = ""] = unsigned.split(".");
  const penceStr = (penceRaw + "00").slice(0, 2);
  const total = parseInt(poundsPart, 10) * 100 + parseInt(penceStr, 10);
  return negative ? -total : total;
}

/** The inverse of `parsePoundsToPence` -- integer pence back to the
 * "pounds.pence" string a text input should be pre-filled with when
 * editing an existing cost entry. */
export function penceToPoundsInput(pence: number): string {
  const negative = pence < 0;
  const abs = Math.abs(pence);
  const pounds = Math.floor(abs / 100);
  const remainder = String(abs % 100).padStart(2, "0");
  return `${negative ? "-" : ""}${pounds}.${remainder}`;
}
