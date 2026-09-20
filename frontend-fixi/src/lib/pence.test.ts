import { describe, expect, it } from "vitest";
import { parsePoundsToPence, penceToPoundsInput } from "@/lib/pence";

describe("parsePoundsToPence", () => {
  it("parses a plain pounds-and-pence amount", () => {
    expect(parsePoundsToPence("12.34", false)).toBe(1234);
  });

  it("parses a whole-pounds amount with no decimal part", () => {
    expect(parsePoundsToPence("5", false)).toBe(500);
  });

  it("pads a single fraction digit: '0.1' is 10p, not 1p", () => {
    expect(parsePoundsToPence("0.1", false)).toBe(10);
  });

  it("parses '0' to 0, not null -- the zero-rejection is the caller's job", () => {
    expect(parsePoundsToPence("0", false)).toBe(0);
  });

  it("trims surrounding whitespace", () => {
    expect(parsePoundsToPence(" 12.34 ", false)).toBe(1234);
  });

  it("rejects three or more fraction digits", () => {
    expect(parsePoundsToPence("1.234", false)).toBeNull();
  });

  it("rejects a thousands separator", () => {
    expect(parsePoundsToPence("1,234.56", false)).toBeNull();
  });

  it("rejects non-numeric input", () => {
    expect(parsePoundsToPence("abc", false)).toBeNull();
  });

  it("rejects an empty string", () => {
    expect(parsePoundsToPence("", false)).toBeNull();
  });

  it("rejects a negative amount when allowNegative is false", () => {
    expect(parsePoundsToPence("-5.00", false)).toBeNull();
  });

  it("accepts a negative amount when allowNegative is true", () => {
    expect(parsePoundsToPence("-5.00", true)).toBe(-500);
  });

  it("never loses precision to float rounding on a value like 4.35", () => {
    // The whole reason this function does string arithmetic instead of
    // Math.round(parseFloat(raw) * 100): 4.35 * 100 is 434.99999999999994
    // in IEEE-754 float math. Math.round happens to still save that
    // particular case, but the string path never goes near the float
    // representation at all -- assert the exact integer, not "close to".
    expect(parsePoundsToPence("4.35", false)).toBe(435);
  });

  it("never loses precision on a value like 19.99", () => {
    expect(parsePoundsToPence("19.99", false)).toBe(1999);
  });

  it("round-trips through penceToPoundsInput for a range of amounts, including negatives", () => {
    const amounts = [0, 1, 10, 99, 100, 435, 1999, 123456, -1, -50, -1234];
    for (const pence of amounts) {
      const input = penceToPoundsInput(pence);
      expect(parsePoundsToPence(input, true)).toBe(pence);
    }
  });
});

describe("penceToPoundsInput", () => {
  it("formats a plain amount as pounds.pence", () => {
    expect(penceToPoundsInput(1234)).toBe("12.34");
  });

  it("pads a sub-10p remainder with a leading zero", () => {
    expect(penceToPoundsInput(1005)).toBe("10.05");
  });

  it("formats an amount under a pound", () => {
    expect(penceToPoundsInput(45)).toBe("0.45");
  });

  it("formats a negative amount with a leading minus and no double sign", () => {
    expect(penceToPoundsInput(-1234)).toBe("-12.34");
  });

  it("formats zero", () => {
    expect(penceToPoundsInput(0)).toBe("0.00");
  });
});
