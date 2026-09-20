import { describe, expect, it } from "vitest";
import { readFlag, readInt, readParam } from "@/lib/search-params";

// These readers exist because TanStack Router JSON-quotes every search
// value it writes (`?include_archived=%22true%22`, quotes and all), so a
// naive `params.get(key) === "true"` never matched and every URL filter
// flag in the app was silently inert -- the control ticked, the URL
// changed, and nothing else happened. That regression is exactly what
// these tests are pinned against: they assert the *quoted* forms the
// router actually produces, not just the unquoted forms a hand-typed URL
// would use.

describe("readParam", () => {
  it("strips a JSON-quoted string value (the router's own output)", () => {
    const params = new URLSearchParams('status=%22ACTIVE%22');
    expect(readParam(params, "status")).toBe("ACTIVE");
  });

  it("passes an unquoted value straight through (a hand-typed URL)", () => {
    const params = new URLSearchParams("status=ACTIVE");
    expect(readParam(params, "status")).toBe("ACTIVE");
  });

  it("returns undefined for a missing key", () => {
    const params = new URLSearchParams("");
    expect(readParam(params, "status")).toBeUndefined();
  });

  it("returns undefined for an empty-string value", () => {
    const params = new URLSearchParams("status=");
    expect(readParam(params, "status")).toBeUndefined();
  });

  it("returns undefined when params itself is null or undefined", () => {
    expect(readParam(null, "status")).toBeUndefined();
    expect(readParam(undefined, "status")).toBeUndefined();
  });

  it("unwraps a JSON-quoted empty string to an empty string, not undefined", () => {
    // `""` (two characters, both quotes) is a valid JSON string, distinct
    // from the "key present but no value" case above -- it must not be
    // conflated with "absent".
    const params = new URLSearchParams('status=%22%22');
    expect(readParam(params, "status")).toBe("");
  });

  it("leaves a single stray quote character untouched", () => {
    // Length 1: the `raw.length >= 2` guard must stop this from slicing
    // into an empty string.
    const params = new URLSearchParams("status=%22");
    expect(readParam(params, "status")).toBe('"');
  });

  it("leaves a quote-prefixed but unterminated value untouched", () => {
    const params = new URLSearchParams('status=%22unterminated');
    expect(readParam(params, "status")).toBe('"unterminated');
  });

  it("leaves a value that only ends in a quote untouched", () => {
    const params = new URLSearchParams('status=unterminated%22');
    expect(readParam(params, "status")).toBe('unterminated"');
  });
});

describe("readFlag", () => {
  it("reads the router's quoted true", () => {
    const params = new URLSearchParams('archived=%22true%22');
    expect(readFlag(params, "archived")).toBe(true);
  });

  it("reads an unquoted true", () => {
    const params = new URLSearchParams("archived=true");
    expect(readFlag(params, "archived")).toBe(true);
  });

  it("reads a quoted '1'", () => {
    const params = new URLSearchParams('archived=%221%22');
    expect(readFlag(params, "archived")).toBe(true);
  });

  it("reads an unquoted 1", () => {
    const params = new URLSearchParams("archived=1");
    expect(readFlag(params, "archived")).toBe(true);
  });

  it("is false for the router's quoted false", () => {
    const params = new URLSearchParams('archived=%22false%22');
    expect(readFlag(params, "archived")).toBe(false);
  });

  it("is false when the key is missing", () => {
    const params = new URLSearchParams("");
    expect(readFlag(params, "archived")).toBe(false);
  });

  it("is case-sensitive -- 'TRUE' is not accepted", () => {
    const params = new URLSearchParams("archived=TRUE");
    expect(readFlag(params, "archived")).toBe(false);
  });

  it("does not treat an arbitrary truthy-looking string as true", () => {
    const params = new URLSearchParams("archived=yes");
    expect(readFlag(params, "archived")).toBe(false);
  });
});

describe("readInt", () => {
  it("parses the router's quoted integer", () => {
    const params = new URLSearchParams('offset=%2212%22');
    expect(readInt(params, "offset", 0)).toBe(12);
  });

  it("parses an unquoted integer", () => {
    const params = new URLSearchParams("offset=12");
    expect(readInt(params, "offset", 0)).toBe(12);
  });

  it("falls back when the key is missing", () => {
    const params = new URLSearchParams("");
    expect(readInt(params, "offset", 7)).toBe(7);
  });

  it("falls back on an unparseable value", () => {
    const params = new URLSearchParams("offset=abc");
    expect(readInt(params, "offset", 7)).toBe(7);
  });

  it("parses a leading-integer prefix of a malformed value (parseInt leniency)", () => {
    // This pins parseInt's real, lenient behaviour -- "12abc" parses as 12
    // rather than falling back. If a future rewrite swaps in
    // Number.parseFloat or a stricter regex, this is the test that catches
    // the behaviour change.
    const params = new URLSearchParams("offset=12abc");
    expect(readInt(params, "offset", 0)).toBe(12);
  });

  it("falls back on a negative-looking non-numeric string", () => {
    const params = new URLSearchParams("offset=-");
    expect(readInt(params, "offset", 3)).toBe(3);
  });

  it("accepts a negative integer", () => {
    const params = new URLSearchParams("offset=-5");
    expect(readInt(params, "offset", 0)).toBe(-5);
  });
});
