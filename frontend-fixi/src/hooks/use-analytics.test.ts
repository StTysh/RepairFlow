import { parse } from "date-fns";
import { describe, expect, it } from "vitest";
import { normalizeInsights, type RawInsightsResponse } from "@/hooks/use-analytics";

// normalizeInsights exists because the real /insights response's field
// names don't match what the chart components read (month arrives as
// separate year/month integers, the trade axis is called `category`,
// resolution figures nest under `resolution.buckets` with `label` instead
// of `bucket`, etc.) -- see the RawInsightsResponse docstring in
// use-analytics.ts. Before this normaliser existed, date-fns `parse` was
// handed the raw month integer where it expected a "yyyy-MM" string and
// crashed the whole Insights page. These tests pin both: the field
// renaming, and that the value it hands to date-fns is actually parseable.

describe("normalizeInsights", () => {
  it("zero-pads year/month into a yyyy-MM key that date-fns can parse", () => {
    const raw: RawInsightsResponse = {
      case_volume_by_month: [{ year: 2026, month: 3, count: 7 }],
    };
    const result = normalizeInsights(raw);
    expect(result.case_volume_by_month).toEqual([{ month: "2026-03", count: 7 }]);

    // This is the actual regression: date-fns `parse` must not crash and
    // must not yield an Invalid Date when handed the normalised value.
    const parsed = parse(result.case_volume_by_month[0]!.month, "yyyy-MM", new Date());
    expect(Number.isNaN(parsed.getTime())).toBe(false);
    expect(parsed.getFullYear()).toBe(2026);
    expect(parsed.getMonth()).toBe(2); // 0-indexed: March
  });

  it("pads a single-digit month with a leading zero", () => {
    const raw: RawInsightsResponse = {
      case_volume_by_month: [{ year: 2026, month: 1, count: 1 }],
    };
    expect(normalizeInsights(raw).case_volume_by_month).toEqual([{ month: "2026-01", count: 1 }]);
  });

  it("renames category -> trade in the category breakdown, keeping null distinct from a string", () => {
    const raw: RawInsightsResponse = {
      category_breakdown: [
        { category: "ROOFING", count: 4, percentage: 66.7 },
        { category: null as unknown as string, count: 2, percentage: 33.3 },
      ],
    };
    const result = normalizeInsights(raw);
    expect(result.category_breakdown).toEqual([
      { trade: "ROOFING", count: 4, percentage: 66.7 },
      { trade: null, count: 2, percentage: 33.3 },
    ]);
  });

  it("renames resolution.buckets[].label -> bucket and flattens average/median up a level", () => {
    const raw: RawInsightsResponse = {
      resolution: {
        buckets: [{ label: "0-24h", count: 3, min_hours: 0, max_hours: 24 }],
        average_hours: 12.5,
        median_hours: 10,
      },
    };
    const result = normalizeInsights(raw);
    expect(result.resolution_time_distribution).toEqual([
      { bucket: "0-24h", count: 3, min_hours: 0, max_hours: 24 },
    ]);
    expect(result.average_hours).toBe(12.5);
    expect(result.median_hours).toBe(10);
  });

  it("renames case_volume_comparison.change_pct -> comparison.case_volume.pct_change", () => {
    const raw: RawInsightsResponse = {
      case_volume_comparison: { current: 10, previous: 8, change_pct: 25, is_new: false },
    };
    const result = normalizeInsights(raw);
    expect(result.comparison["case_volume"]).toEqual({
      current: 10,
      previous: 8,
      pct_change: 25,
      is_new: false,
    });
  });

  it("preserves a null pct_change rather than coercing it to 0", () => {
    const raw: RawInsightsResponse = {
      case_volume_comparison: { current: 5, previous: 0, change_pct: null, is_new: true },
    };
    const result = normalizeInsights(raw);
    expect(result.comparison["case_volume"]?.pct_change).toBeNull();
    expect(result.comparison["case_volume"]?.is_new).toBe(true);
  });

  it("defaults a recurring issue's missing category to OTHER", () => {
    const raw: RawInsightsResponse = {
      recurring_issues: [
        {
          property_id: "p1",
          property_address: "1 Main St",
          category: undefined as unknown as string,
          count: 3,
          last_occurred_at: "2026-01-01T00:00:00Z",
        },
      ],
    };
    const result = normalizeInsights(raw);
    expect(result.recurring_issues[0]?.trade).toBe("OTHER");
  });

  it("omits case_ids from a recurring issue row when the API didn't send any", () => {
    const raw: RawInsightsResponse = {
      recurring_issues: [
        {
          property_id: "p1",
          property_address: "1 Main St",
          category: "PLUMBING",
          count: 2,
          last_occurred_at: "2026-01-01T00:00:00Z",
        },
      ],
    };
    const result = normalizeInsights(raw);
    expect(result.recurring_issues[0]).not.toHaveProperty("case_ids");
  });

  it("keeps case_ids when the API did send them", () => {
    const raw: RawInsightsResponse = {
      recurring_issues: [
        {
          property_id: "p1",
          property_address: "1 Main St",
          category: "PLUMBING",
          count: 2,
          last_occurred_at: "2026-01-01T00:00:00Z",
          case_ids: ["c1", "c2"],
        },
      ],
    };
    const result = normalizeInsights(raw);
    expect(result.recurring_issues[0]?.case_ids).toEqual(["c1", "c2"]);
  });

  it("tolerates a fully empty response: every array empty, hours null, comparison empty", () => {
    const result = normalizeInsights({});
    expect(result).toEqual({
      case_volume_by_month: [],
      category_breakdown: [],
      spend_by_year: [],
      resolution_time_distribution: [],
      average_hours: null,
      median_hours: null,
      recurring_issues: [],
      comparison: {},
      includes_archived_history: false,
      archived_case_count: 0,
    });
  });

  it("defaults includes_archived_history and archived_case_count when absent", () => {
    const result = normalizeInsights({});
    expect(result.includes_archived_history).toBe(false);
    expect(result.archived_case_count).toBe(0);
  });

  it("passes spend_by_year through unchanged (no renaming needed there)", () => {
    const raw: RawInsightsResponse = {
      spend_by_year: [{ year: 2025, quoted_pence: 10000, actual_pence: 9500 }],
    };
    expect(normalizeInsights(raw).spend_by_year).toEqual([
      { year: 2025, quoted_pence: 10000, actual_pence: 9500 },
    ]);
  });
});
