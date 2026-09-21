import { describe, expect, it } from "vitest";
import { easeOut, interpolate, parseMetric, progress, renderMetric } from "@/lib/metric-format";

describe("parseMetric", () => {
  it("splits the formats the dashboards actually produce", () => {
    expect(parseMetric("39")).toMatchObject({ prefix: "", value: 39, suffix: "" });
    expect(parseMetric("59.8h")).toMatchObject({ value: 59.8, decimals: true, suffix: "h" });
    expect(parseMetric("\u00a31,565")).toMatchObject({
      prefix: "\u00a3",
      value: 1565,
      grouped: true,
    });
    expect(parseMetric("+200%")).toMatchObject({ prefix: "+", value: 200, suffix: "%" });
  });

  it("returns null for a value with no number in it, so it renders verbatim", () => {
    // The dashboards use an em-dash for "no data"; animating it would be
    // both meaningless and a lie about there being a figure.
    expect(parseMetric("\u2014")).toBeNull();
    expect(parseMetric("Unknown")).toBeNull();
  });
});

describe("renderMetric", () => {
  it("round-trips each parsed shape", () => {
    for (const s of ["39", "59.8h", "\u00a31,565", "12 active"]) {
      const p = parseMetric(s);
      expect(p, s).not.toBeNull();
      expect(renderMetric(p!.value, p!)).toBe(s);
    }
  });

  it("never emits a negative zero", () => {
    // `(-0).toFixed(0)` is "-0". This is the exact string that reached
    // the live dashboard.
    const p = parseMetric("39")!;
    expect(renderMetric(-0, p)).toBe("0");
    expect(renderMetric(-0.0004, p)).toBe("0");
  });
});

describe("progress", () => {
  it("clamps a frame timestamp that predates the frame request", () => {
    // requestAnimationFrame passes the timestamp of the frame the
    // callback belongs to, which can be EARLIER than the performance.now()
    // captured when the animation started. Unclamped this is negative.
    expect(progress(990, 1000, 620)).toBe(0);
    expect(progress(-50, 0, 620)).toBe(0);
  });

  it("clamps past the end and behaves in between", () => {
    expect(progress(2000, 1000, 620)).toBe(1);
    expect(progress(1310, 1000, 620)).toBeCloseTo(0.5, 5);
  });

  it("treats a zero duration as already finished rather than dividing by zero", () => {
    expect(progress(1000, 1000, 0)).toBe(1);
  });
});

describe("interpolate", () => {
  it("cannot undershoot the start or overshoot the target", () => {
    // The regression, end to end: a negative raw progress must not turn
    // a count up to 39 into a count down through zero.
    const t = progress(990, 1000, 620);
    expect(interpolate(0, 39, t)).toBe(0);

    const p = parseMetric("59.8h")!;
    expect(renderMetric(interpolate(0, 59.8, t), p)).toBe("0.0h");
  });

  it("lands exactly on the target, with no floating-point residue", () => {
    expect(interpolate(0, 39, 1)).toBe(39);
    expect(interpolate(12, 59.8, 1)).toBe(59.8);
  });

  it("eases out rather than running linearly", () => {
    expect(easeOut(0)).toBe(0);
    expect(easeOut(1)).toBe(1);
    expect(easeOut(0.5)).toBeGreaterThan(0.5);
  });
});
