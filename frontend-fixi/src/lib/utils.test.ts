import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

/**
 * These guard a silent failure, not a style preference.
 *
 * Unextended, tailwind-merge treats every custom `text-*` size as a
 * colour and drops it when a real colour is present in the same call.
 * Nothing errors; the class simply is not in the DOM. Revert the
 * `extendTailwindMerge` call in utils.ts and the first block below fails.
 */

const SIZES = ["micro", "body", "strong", "section", "title", "metric"] as const;

describe("cn keeps custom font sizes alongside colours", () => {
  it.each(SIZES)("keeps text-%s next to a text colour", (size) => {
    expect(cn(`text-${size}`, "text-muted-foreground")).toBe(`text-${size} text-muted-foreground`);
  });

  it("keeps the size when the colour comes first, too", () => {
    expect(cn("text-sidebar-foreground", "text-strong")).toBe(
      "text-sidebar-foreground text-strong",
    );
  });

  it("still treats two sizes as a conflict, last one winning", () => {
    expect(cn("text-body", "text-strong")).toBe("text-strong");
    expect(cn("text-xs", "text-body")).toBe("text-body");
    expect(cn("text-body", "text-xs")).toBe("text-xs");
  });

  it("still treats two colours as a conflict", () => {
    expect(cn("text-muted-foreground", "text-destructive")).toBe("text-destructive");
  });
});

describe("cn resolves the other custom token groups", () => {
  it.each([
    ["max-w-page", "max-w-sm"],
    ["duration-fast", "duration-200"],
    ["ease-fixi", "ease-out"],
    ["animate-shimmer", "animate-pulse"],
  ])("lets a built-in override the custom %s", (custom, builtin) => {
    expect(cn(custom, builtin)).toBe(builtin);
  });

  it.each([
    ["max-w-sm", "max-w-page"],
    ["duration-200", "duration-instant"],
    ["ease-out", "ease-fixi-out"],
    ["animate-pulse", "animate-value-flash"],
  ])("lets the custom token override a built-in (%s -> %s)", (builtin, custom) => {
    expect(cn(builtin, custom)).toBe(custom);
  });
});
