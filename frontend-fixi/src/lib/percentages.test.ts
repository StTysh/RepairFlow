import { describe, expect, it } from "vitest";
import { largestRemainderPercentages } from "@/lib/percentages";

describe("largestRemainderPercentages", () => {
  it("resolves a 51.5/48.5 tie deterministically to 52/48, not 99 or 101", () => {
    expect(largestRemainderPercentages([51.5, 48.5])).toEqual([52, 48]);
  });

  it("distributes the leftover point(s) to the largest remainders first", () => {
    // Floors: 0, 0, 99 (sum 99). Remainders: .4, .3, .3 -- only the first
    // gets the single leftover point.
    expect(largestRemainderPercentages([0.4, 0.3, 99.3])).toEqual([1, 0, 99]);
  });

  it("sums to exactly 100 across a spread of realistic trade-breakdown inputs", () => {
    const cases: number[][] = [
      [33.3, 33.3, 33.4],
      [25, 25, 25, 25],
      [10, 20, 30, 40],
      [1, 1, 1, 1, 1, 1, 1, 1, 1, 91],
      [60, 30, 10],
      [16.666, 16.666, 16.666, 16.666, 16.666, 16.67],
    ];
    for (const values of cases) {
      const result = largestRemainderPercentages(values);
      const sum = result.reduce((a, b) => a + b, 0);
      expect(sum).toBe(100);
    }
  });

  it("returns an empty array for an empty input", () => {
    expect(largestRemainderPercentages([])).toEqual([]);
  });

  it("handles a single 100% share", () => {
    expect(largestRemainderPercentages([100])).toEqual([100]);
  });

  it("preserves the input total rather than forcing 100 -- it is not itself a normaliser", () => {
    // Documented behaviour: this function only fixes up *rounding*, it
    // does not renormalise a total that isn't already ~100. Two whole
    // numbers with no fractional part round-trip unchanged even though
    // they don't sum to 100.
    expect(largestRemainderPercentages([10, 20])).toEqual([10, 20]);
  });

  it("rounds an already-whole-number input to itself", () => {
    expect(largestRemainderPercentages([25, 25, 25, 25])).toEqual([25, 25, 25, 25]);
  });
});
