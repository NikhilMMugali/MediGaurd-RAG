"""Picks the passage on a cited PDF page that actually supports an answer, so
the viewer can highlight that passage instead of only opening the page.

Deterministic and lexical: it only ever returns text that already exists in
the page's stored content (a window of consecutive lines), scored by overlap
with the question and the generated answer. It returns None rather than
guess when nothing matches convincingly.
"""
import re
import unicodedata

_STOPWORDS = {
    "the", "and", "for", "are", "was", "were", "what", "which", "who", "whom", "when", "where", "how", "does", "did",
    "his", "her", "their", "this", "that", "these", "those", "with", "from", "about", "have", "has", "had", "any",
    "can", "you", "tell", "show", "give", "please", "result", "results", "value", "values", "report", "page", "pdf",
    "into", "than", "then", "also", "its", "not", "but", "per", "source", "sources", "patient", "document",
}
_TOKEN_RE = re.compile(r"[a-z]+|[0-9]+(?:\.[0-9]+)?")
# Header lines the knowledge generator prepends to a page chunk; they are not
# printed in the PDF itself, so they can never be located on the page.
_SYNTHETIC_HEADER_RE = re.compile(r"^(patient:|document (page|image) \d+)", re.IGNORECASE)
_MAX_WINDOW_LINES = 6
_LINE_PENALTY = 0.15
# Each unmatched token in a window costs this much, so a tight table row
# (every token matches) beats a long paragraph that merely mentions the topic.
_UNMATCHED_TOKEN_PENALTY = 0.35
_MIN_SCORE = 3.0


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return [t for t in _TOKEN_RE.findall(normalized) if t not in _STOPWORDS]


def _weight(token: str, from_question: bool) -> float:
    base = 1.5 if token[0].isdigit() else (0.5 if len(token) <= 2 else 1.0)
    return base * (1.5 if from_question else 1.0)


def select_highlight(content: str | None, question: str, answer: str | None = None) -> str | None:
    if not content:
        return None
    lines = [
        ln.strip()
        for ln in content.splitlines()
        if ln.strip() and not _SYNTHETIC_HEADER_RE.match(ln.strip())
    ]
    if not lines:
        return None

    weights: dict[str, float] = {}
    for token in _tokens(answer or ""):
        weights[token] = max(weights.get(token, 0.0), _weight(token, False))
    for token in _tokens(question):
        weights[token] = max(weights.get(token, 0.0), _weight(token, True))
    if not weights:
        return None

    line_token_lists = [_tokens(ln) for ln in lines]
    line_tokens = [set(toks) for toks in line_token_lists]
    best_score, best_span = 0.0, None
    for start in range(len(lines)):
        matched: set[str] = set()
        for end in range(start, min(start + _MAX_WINDOW_LINES, len(lines))):
            matched |= line_tokens[end] & weights.keys()
            # A window must begin and end on a line that contributes a match,
            # so the highlight never starts/ends on an unrelated line.
            if not (line_tokens[start] & weights.keys()) or not (line_tokens[end] & weights.keys()):
                continue
            window_tokens = [t for k in range(start, end + 1) for t in line_token_lists[k]]
            unmatched = sum(1 for t in window_tokens if t not in weights)
            score = (
                sum(weights[t] for t in matched)
                - _LINE_PENALTY * (end - start)
                - _UNMATCHED_TOKEN_PENALTY * unmatched
            )
            if len(matched) >= 2 and score > best_score:
                best_score, best_span = score, (start, end)

    if best_span is None or best_score < _MIN_SCORE:
        return None
    return "\n".join(lines[best_span[0] : best_span[1] + 1])
