import { describe, expect, it } from "vitest";
import { matchOcrLines } from "@/components/documents/ocrHighlight";
import type { OcrLine } from "@/types";

const line = (text: string): OcrLine => ({ text, confidence: 0.97, box: [0, 0, 10, 10] });
const LINES = ["LABORATORY REPORT", "Patient Name: Meera Krishnan", "Hemoglobin 13.8 g/dL", "25-OH Vitamin D 18 ng/mL 30 - 100 LOW", "ng/mL", "Ferritin 42 ng/mL"].map(line);

describe("matchOcrLines", () => {
  it("finds the cited lines as one contiguous run", () => {
    expect(matchOcrLines(LINES, "Hemoglobin 13.8 g/dL\n25-OH Vitamin D 18 ng/mL 30 - 100 LOW")).toEqual([2, 3]);
  });
  it("ignores case and spacing differences", () => {
    expect(matchOcrLines(LINES, "ferritin   42 NG/ML")).toEqual([5]);
  });
  it("picks the right occurrence of a repeated line by using the run", () => {
    const lines = ["ng/mL", "A", "ng/mL", "B"].map(line);
    expect(matchOcrLines(lines, "ng/mL\nB")).toEqual([2, 3]);
  });
  it("returns nothing, rather than guessing, when the lines are not in the OCR output", () => {
    expect(matchOcrLines(LINES, "Cholesterol 200 mg/dL")).toEqual([]);
    expect(matchOcrLines(LINES, null)).toEqual([]);
    expect(matchOcrLines(LINES, "")).toEqual([]);
  });
});
