import { describe, expect, it } from "vitest";
import { locateHighlightItems } from "@/components/documents/highlight";

// One text-layer item per table cell, as pdf.js actually emits them.
const ROW = ["25-OH Vitamin D", "18", "ng/mL", "30 - 100", "LOW", "Vitamin B12", "245", "pg/mL"];

describe("locateHighlightItems", () => {
  it("highlights exactly the items that make up the cited passage", () => {
    const result = locateHighlightItems(ROW, "25-OH Vitamin D\n18\nng/mL\n30 - 100\nLOW");
    expect([...result].sort()).toEqual([0, 1, 2, 3, 4]);
  });

  it("does not highlight an identical value elsewhere on the page", () => {
    const items = ["Age", "18", "years", "25-OH Vitamin D", "18", "ng/mL"];
    const result = locateHighlightItems(items, "25-OH Vitamin D\n18\nng/mL");
    expect([...result].sort()).toEqual([3, 4, 5]);
  });

  it("ignores case, spacing, and dash style differences", () => {
    const result = locateHighlightItems(["25–OH  VITAMIN", "d  18 ng/ml"], "25-oh vitamin d 18 ng/mL");
    expect([...result].sort()).toEqual([0, 1]);
  });

  it("returns an empty set, not a guess, when the passage is not on the page", () => {
    expect(locateHighlightItems(ROW, "Hemoglobin 13.5 g/dL").size).toBe(0);
  });

  it("returns an empty set for missing or tiny targets", () => {
    expect(locateHighlightItems(ROW, null).size).toBe(0);
    expect(locateHighlightItems(ROW, "").size).toBe(0);
    expect(locateHighlightItems(ROW, "18").size).toBe(0);
  });

  it("falls back to individual long lines when the whole passage is split differently on the page", () => {
    const items = ["The distinctive flagged result is", "something unrelated", "marked LOW against the printed interval"];
    const result = locateHighlightItems(items, "The distinctive flagged result is\nmarked LOW against the printed interval\nnot on page at all");
    expect([...result].sort()).toEqual([0, 2]);
  });
});
