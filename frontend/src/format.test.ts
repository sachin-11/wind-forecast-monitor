import { describe, expect, it } from "vitest";
import { toRange } from "./api";
import { biasSentence, gw, mw, signedMw } from "./format";

describe("format", () => {
  it("formats power values", () => {
    expect(mw(12345.6)).toBe("12,346 MW");
    expect(gw(12345)).toBe("12.3 GW");
    expect(signedMw(250)).toBe("+250 MW");
    expect(signedMw(-250)).toBe("−250 MW");
    expect(mw(null)).toBe("–");
  });

  it("describes bias in plain English", () => {
    expect(biasSentence(20)).toMatch(/unbiased/);
    expect(biasSentence(500)).toMatch(/too high/);
    expect(biasSentence(-500)).toMatch(/too low/);
  });
});

describe("toRange", () => {
  it("makes the end date inclusive", () => {
    expect(toRange("2026-01-01", "2026-01-31")).toEqual({ start: "2026-01-01T00:00:00Z", end: "2026-02-01T00:00:00Z" });
  });
});
