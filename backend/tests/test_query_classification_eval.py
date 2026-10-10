"""A real, measurable evaluation set for app.rag.query_classification —
section 5/10 of the master audit prompt ("create automated tests that run
the same intent through several natural phrasings and verify that
equivalent questions route consistently" / "measure intent classification
accuracy").

This is NOT an ML training set and classify_query is NOT a trained model —
it is a deterministic, keyword-and-fuzzy-match classifier (see the module
docstring). What's "learned" here is a curated set of representative
natural-language examples per intent, used to measure and lock in routing
behavior, not to train anything. See progress/DECISIONS.md "Query
classification robustness" for what was actually changed and why, and for
the one documented gap this suite intentionally still reports (a single
missing-letter typo like "alergic" falls just under the fuzzy-match
threshold by design — see test_known_typo_tolerance_limit below).

Each case is (question, expected_route, expected_record_types_or_None).
`expected_record_types=None` means "don't care" (only the route is
asserted) — used for semantic/summary/identity cases where the exact
record_types union isn't the point of the example.
"""
import pytest

from app.rag.query_classification import classify_query

# ---- STRUCTURED: exact-fact questions with a deterministic DB answer ----
STRUCTURED_CASES = [
    ("What meds is P001 taking?", ["medication"]),
    ("whats his meds", ["medication"]),
    ("Can you tell me his current medication?", ["medication"]),
    ("What medications is the patient on?", ["medication"]),
    ("wat medicatoin does she take", ["medication"]),  # typo tolerance
    ("Any allergies for this patient?", ["allergy"]),
    ("Does he have any allergies?", ["allergy"]),
    ("What conditions does this patient have?", ["condition"]),
    ("What's his diagnosis?", ["condition"]),
    ("What procedures has she had?", ["procedure"]),
    ("Did he undergo any surgery?", ["procedure"]),
    ("Show me the latest visit.", ["encounter"]),
    ("What happened in the last appointment?", ["encounter"]),
    ("When did he last come to the hospital?", ["encounter"]),
    ("What is the outstanding amount?", ["claim", "claim_transaction"]),
    ("How much does he owe?", ["claim", "claim_transaction"]),
    ("Who is his payer?", ["payer", "payer_transition"]),
    ("What insurance does she have?", ["payer", "payer_transition"]),
    ("What about his blood report?", ["observation"]),
    ("And what was the value for vitamin D?", ["observation"]),
    ("What are his recent lab results?", ["observation"]),
]


@pytest.mark.parametrize("question,expected_types", STRUCTURED_CASES)
def test_structured_routing(question: str, expected_types: list[str]):
    intent = classify_query(question, role_is_clinical=True)
    assert intent.route == "structured", f"{question!r} -> expected structured, got {intent.route} ({intent.intent_kind})"
    assert intent.record_types is not None
    assert set(expected_types) & set(intent.record_types), f"{question!r}: expected overlap with {expected_types}, got {intent.record_types}"


# ---- SUMMARY: cross-domain rollups, no single exact fact ----
SUMMARY_CASES = [
    "Give me a quick summary.",
    "Tell me about Kavya Demo Patient.",
    "What do you have on him?",
    "Summarize this patient's record.",
    "Give me an overview.",
]


@pytest.mark.parametrize("question", SUMMARY_CASES)
def test_summary_routing(question: str):
    intent = classify_query(question, role_is_clinical=True)
    assert intent.route == "summary", f"{question!r} -> expected summary, got {intent.route}"


# ---- IDENTITY: name/age/gender, a structured sub-case handled separately
# from the record-type rules (patient_identity intent_kind) ----
IDENTITY_CASES = [
    "What is his name?",
    "Tell me his age.",
    "How old is the patient?",
    "What is P001's gender?",
]


@pytest.mark.parametrize("question", IDENTITY_CASES)
def test_identity_routing(question: str):
    intent = classify_query(question, role_is_clinical=True)
    assert intent.intent_kind == "patient_identity"
    assert intent.route == "structured"


# ---- SEMANTIC: open-ended, document-grounded, or flag/abnormal questions
# that must NOT be answered from a Synthea field that doesn't carry the
# concept being asked about (see the "flagged"/"abnormal" rule's own
# comment in query_classification.py) ----
SEMANTIC_CASES = [
    "Does this report mention anything abnormal?",
    "Find the relevant information in this PDF.",
    "Compare the latest report with the previous one.",
    "Can you explain that result?",
    "any flagged values",
    "whats abnormal in the labs",
]


def test_questions_about_an_uploaded_document_go_to_its_text_not_the_sql_summary():
    """"Summarize the report..." used to match the generic summary rule and
    return route="summary" — the deterministic SQL rollup. In Document
    Intelligence that was masked by run_query's `document_id is None` guard,
    but in Clinical Chat (no document_id) it answered "0 documented" for a
    patient whose data exists only in an uploaded PDF or OCR image. A
    question that refers to the report/image/PDF itself is now routed to the
    document text by the classifier (semantic, record type "document"); the
    pipeline guard remains as defense in depth."""
    for question in (
        "Summarize the report and cite the pages supporting each measurement.",
        "Tell me about this report.",
        "What does this image say?",
        "Which image contains this information?",
        "Summarize the uploaded report.",
        "Explain the result using only the information in the report.",
    ):
        intent = classify_query(question, role_is_clinical=True)
        assert intent.route == "semantic", question
        assert "document" in (intent.record_types or []), question


def test_blood_report_still_means_lab_results_not_an_uploaded_document():
    """Plain "report" is not a document reference — "his blood report" is a
    lab-results phrase and must keep its structured observation route."""
    intent = classify_query("What about his blood report?", role_is_clinical=True)
    assert intent.route == "structured"
    assert intent.record_types == ["observation"]


@pytest.mark.parametrize("question", SEMANTIC_CASES)
def test_semantic_routing(question: str):
    intent = classify_query(question, role_is_clinical=True)
    assert intent.route == "semantic", f"{question!r} -> expected semantic, got {intent.route} ({intent.intent_kind})"


def test_multi_domain_question_never_takes_the_structured_fast_path():
    """A question naming two domains at once must fall back to semantic —
    the structured fast path only ever answers a single, unambiguous
    intent (see classify_query's own docstring on matched_kinds)."""
    intent = classify_query("What is his diagnosis and what does he owe?", role_is_clinical=True)
    assert intent.route == "semantic"
    assert set(intent.record_types or []) >= {"condition", "claim"}


def test_known_typo_tolerance_limit():
    """Documents a real, deliberate boundary rather than hiding it: a
    missing-letter typo like "alergic" (one L, not two) falls just under
    the fuzzy-match cutoff (ratio ~0.71 vs the 0.8 threshold) and is NOT
    recovered. The threshold is intentionally conservative — loosening it
    to catch this one case would risk false-positive reclassification
    elsewhere in the vocabulary. See progress/DECISIONS.md "Query
    classification robustness."""
    intent = classify_query("is he alergic to anything", role_is_clinical=True)
    assert intent.route == "semantic"  # falls through — a known, bounded gap, not a crash or wrong answer


def test_case_and_punctuation_insensitivity():
    a = classify_query("WHAT MEDICATIONS IS HE TAKING???", role_is_clinical=True)
    b = classify_query("what medications is he taking", role_is_clinical=True)
    assert a.route == b.route == "structured"
    assert a.record_types == b.record_types == ["medication"]
