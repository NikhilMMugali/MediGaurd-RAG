import type { OcrLine } from "@/types";

// Which OCR lines make up a cited passage. The citation's highlight_text is
// built from the very same OCR line strings the box data came from, so this is
// exact matching of the engine's own output — never a guessed position. It
// returns [] (and the viewer says so) when the lines cannot be found.

function normalize(s: string): string {
  return s.normalize("NFKC").toLowerCase().replace(/[\s­​ ]+/g, "");
}

export function matchOcrLines(lines: OcrLine[], highlightText: string | null | undefined): number[] {
  if (!highlightText) return [];
  const wanted = highlightText.split("\n").map(normalize).filter(Boolean);
  if (wanted.length === 0) return [];
  const have = lines.map((line) => normalize(line.text));

  // Prefer one contiguous run in reading order — this is how the selector
  // chose the passage, and it disambiguates repeated lines like "ng/mL".
  for (let start = 0; start + wanted.length <= have.length; start++) {
    if (wanted.every((w, k) => have[start + k] === w)) return wanted.map((_, k) => start + k);
  }

  // Otherwise match lines individually, each at most once.
  const used = new Set<number>();
  const matched: number[] = [];
  for (const w of wanted) {
    const idx = have.findIndex((h, i) => !used.has(i) && h === w);
    if (idx >= 0) {
      used.add(idx);
      matched.push(idx);
    }
  }
  return matched;
}
