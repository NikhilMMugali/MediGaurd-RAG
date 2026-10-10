// Locates a cited passage inside a PDF page's text-layer items so the viewer
// can highlight exactly those items. Pure string matching over the text the
// PDF itself contains — it never invents positions, and returns an empty set
// when the passage can't be found so the caller can say so honestly.

const DASHES = /[‐-―−]/g;
const IGNORABLE = /[\s­​ ]+/g;

function normalize(s: string): string {
  return s.normalize("NFKC").replace(DASHES, "-").toLowerCase().replace(IGNORABLE, "");
}

const MIN_LINE_FALLBACK_CHARS = 8;

function findRun(compact: string, owner: number[], needle: string, into: Set<number>): boolean {
  if (needle.length === 0) return false;
  const at = compact.indexOf(needle);
  if (at < 0) return false;
  for (let k = at; k < at + needle.length; k++) into.add(owner[k]);
  return true;
}

export function locateHighlightItems(itemStrings: string[], target: string | null | undefined): Set<number> {
  const result = new Set<number>();
  if (!target) return result;

  let compact = "";
  const owner: number[] = [];
  itemStrings.forEach((str, index) => {
    for (const ch of normalize(str)) {
      compact += ch;
      owner.push(index);
    }
  });

  const whole = normalize(target);
  if (whole.length >= 3 && findRun(compact, owner, whole, result)) return result;

  // The passage spans lines the text layer split or ordered differently —
  // fall back to each sufficiently long line on its own rather than guess.
  for (const line of target.split("\n")) {
    const n = normalize(line);
    if (n.length >= MIN_LINE_FALLBACK_CHARS) findRun(compact, owner, n, result);
  }
  return result;
}
