/**
 * Largest-remainder rounding for a set of percentage shares.
 *
 * Rounding each share independently can print a column that doesn't add
 * up (51.5 + 48.5 -> "52% + 49%" = 101%, or two 33.3s and a 33.4 -> "33 +
 * 33 + 33" = 99%). This keeps every floor, then hands the leftover whole
 * points to whichever shares were rounded down hardest (largest
 * fractional remainder first), so a displayed percentage column always
 * sums to the same total as the input -- typically exactly 100 when the
 * inputs already sum to 100.
 *
 * Extracted here (rather than living in Charts.tsx, where it originated)
 * so both Charts.tsx's category-breakdown donut and
 * PropertyStatsCharts.tsx's quoted-by-trade donut -- which had drifted
 * into an inline copy of the exact same algorithm -- share one
 * implementation, and so it's testable as a plain function.
 */
export function largestRemainderPercentages(values: number[]): number[] {
  const floors = values.map((v) => Math.floor(v));
  const total = values.reduce((a, b) => a + b, 0);
  let leftover = Math.round(total) - floors.reduce((a, b) => a + b, 0);
  const order = values
    .map((v, index) => ({ index, remainder: v - Math.floor(v) }))
    .sort((a, b) => b.remainder - a.remainder);
  const result = [...floors];
  for (const { index } of order) {
    if (leftover <= 0) break;
    result[index] = (result[index] ?? 0) + 1;
    leftover -= 1;
  }
  return result;
}
