"""app.rag.highlight picks the passage on a cited page that supports an
answer, so the PDF viewer can highlight it. The page below is synthetic and
mirrors how page chunks are actually stored: one table cell per line, with a
generated 'Patient:/Document page N' header that is not printed in the PDF."""
from app.rag.highlight import select_highlight

PAGE = """Patient: Unknown
Document page 3

SYNTHETIC TEST DATA - NOT A REAL PATIENT
Vitamin and Iron Markers
Test / Measurement
Result
Units
Reference Interval
Flag
25-OH Vitamin D
18
ng/mL
30 - 100
LOW
Vitamin B12
245
pg/mL
200 - 900
NORMAL
Ferritin
42
ng/mL
15 - 150
NORMAL
Printed laboratory flag
25-OH Vitamin D is recorded as 18 ng/mL. The fictional report prints a reference interval of 30 - 100
ng/mL and marks this result LOW."""

ANSWER = "The report shows a 25-OH Vitamin D level of **18 ng/mL**, flagged **LOW** against 30 - 100 ng/mL [SOURCE_1]."


def test_selects_a_passage_that_supports_the_answer():
    highlight = select_highlight(PAGE, "What about his vitamin D result?", ANSWER)
    assert highlight is not None
    assert "Vitamin D" in highlight
    assert "18" in highlight


def test_highlight_is_always_verbatim_lines_from_the_page_never_invented_text():
    highlight = select_highlight(PAGE, "What about his vitamin D result?", ANSWER)
    page_lines = {ln.strip() for ln in PAGE.splitlines()}
    assert highlight is not None
    assert all(line in page_lines for line in highlight.split("\n"))


def test_synthetic_header_lines_are_never_selected():
    highlight = select_highlight(PAGE, "Patient Unknown document page", "Patient: Unknown, document page 3")
    assert highlight is None or ("Patient: Unknown" not in highlight and "Document page 3" not in highlight)


def test_does_not_pick_the_unrelated_vitamin_b12_row():
    highlight = select_highlight(PAGE, "What is the ferritin value?", "Ferritin is 42 ng/mL")
    assert highlight is not None
    assert "Ferritin" in highlight
    assert "B12" not in highlight


def test_returns_none_when_the_page_does_not_support_the_answer():
    unrelated = "Patient: Unknown\nDocument page 1\n\nWBC Count\n6,200\ncells/uL\nHemoglobin\n13.8\ng/dL"
    assert select_highlight(unrelated, "What about his vitamin D result?", ANSWER) is None


def test_returns_none_for_empty_content_or_question_with_no_usable_terms():
    assert select_highlight(None, "anything about vitamin D", ANSWER) is None
    assert select_highlight("", "anything", None) is None
    assert select_highlight(PAGE, "what is the", None) is None
