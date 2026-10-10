"""Deterministic, keyword-based query classification (docs/RAG_DESIGN.md
"hybrid retrieval"). Not an LLM call and not an agent — a plain lookup that
decides two things before any retrieval happens:

  1. `route` — "structured" (an exact DB lookup answers it directly, no
     LLM/Qdrant involved — app.rag.structured_answers), "summary" (a
     deterministic cross-domain rollup, also no LLM), or "semantic" (needs
     Qdrant + LLM synthesis — open-ended/contextual questions).
  2. `record_types` — which record type(s) the question is about, always
     intersected with (never widening) AuthorizationContext.allowed_record_types
     by the caller (app.rag.pipeline) before either route touches data.

Per the PS: "use the database when the question requires an exact fact,
semantic RAG when it requires contextual understanding, both when it
requires both, and always apply authorization before either retrieval
path." This module answers only the first half of that sentence (which
route) — pipeline.py is the one that actually applies authorization before
calling either.
"""
import re
from dataclasses import dataclass
from difflib import get_close_matches

# Observation categories as Synthea itself labels them (see
# app.models.hospital.Observation.category). "Clinical" here means the
# categories a doctor/nurse would expect from a bare "recent observations"
# question — vitals, labs, and clinical exam/imaging/procedure findings —
# as opposed to the socioeconomic survey and social-history rows Synthea
# also files under the same observations table.
VITAL_SIGNS = ["vital-signs"]
LABORATORY = ["laboratory"]
CLINICAL_OBSERVATION_CATEGORIES = ["vital-signs", "laboratory", "exam", "imaging", "procedure", "therapy"]
SURVEY_SOCIAL_CATEGORIES = ["survey", "social-history"]

_RECENCY_RE = re.compile(r"\b(recent|latest|current|newest|most recent|lately|last few)\b", re.IGNORECASE)
_HISTORY_RE = re.compile(r"\b(history|all (visits|encounters)|every visit)\b", re.IGNORECASE)
_SUMMARY_RE = re.compile(
    r"\b(summary|summarize|tell me about|what do you have on|what information do you have|overview|everything (important|you know))\b",
    re.IGNORECASE,
)
# Covers "what is his name", "tell me his age", "how old is the patient",
# "what is P001's gender" — a bare "<pronoun/possessive> age" without a
# "what is" prefix is common in natural speech and must still classify as
# identity (section 34 "improve query understanding").
_IDENTITY_RE = re.compile(
    r"\b(patient'?s? name|what is (the |his |her )?name|how old|(his|her|their|patient'?s?) age|"
    r"\w+'s (name|age|gender|date of birth)|"
    r"what is (the |his |her )?age|date of birth|\bdob\b|what is (the |his |her )?gender)\b",
    re.IGNORECASE,
)

# Ordered most-specific-first within a tier; every matching rule's types are
# unioned (see classify_query) rather than the first match winning, so a
# question naming two domains at once still gets routed for both.
# (pattern, record_types, intent_kind)
## NOTE: every keyword below uses a `\w*` suffix (e.g. `medication\w*`), not
## a bare `\bmedication\b` — a trailing `\b` right after a singular noun
## never matches its own plural ("medications" has a word char, not a
## boundary, right after "medication"), which silently broke every plural
## phrasing a user actually types ("What medications...", "his
## conditions...", "recent encounters...").
_RECORD_TYPE_RULES: list[tuple[re.Pattern, list[str], str]] = [
    # "meds" is the single most common informal synonym for "medication(s)"
    # and shares no prefix with it, so the `\w*` suffix trick doesn't cover
    # it — added as its own alternative (section 5 "what meds is he taking").
    (re.compile(r"\b(medication\w*|medicine\w*|drug\w*|prescri\w*|dose\w*|dosage\w*|meds?)\b", re.IGNORECASE), ["medication"], "medication"),
    (re.compile(r"\b(allerg\w*)\b", re.IGNORECASE), ["allergy"], "allergy"),
    (re.compile(r"\b(diagnos\w*|condition\w*)\b", re.IGNORECASE), ["condition"], "condition"),
    (
        re.compile(
            r"\b(surgery|surgical|operation\w*|underwent|procedures? (performed|done|had)|what procedures?\b.*\b(have|had|undergo\w*))\b",
            re.IGNORECASE,
        ),
        ["procedure"],
        "procedure",
    ),
    (
        re.compile(
            r"\b(encounter\w*|visit\w*|admission\w*|admitted|appointment\w*|come to the hospital|came to the hospital|"
            r"come in|came in|been (seen|admitted))\b",
            re.IGNORECASE,
        ),
        ["encounter"],
        "encounter",
    ),
    (
        re.compile(r"\b(payer\w*|insurance|insurer\w*)\b", re.IGNORECASE),
        ["payer", "payer_transition"],
        "finance_payer",
    ),
    (
        re.compile(r"\b(claim\w*|bill\w*|invoice\w*|outstanding|balance\w*|payment\w*|owe\w*|amount due|copay\w*)\b", re.IGNORECASE),
        ["claim", "claim_transaction"],
        "finance_outstanding",
    ),
    (
        # "blood report"/"vitamin D" are the actual phrasings people use for
        # lab results, not just "lab test" (section 5 "what about his blood
        # report", "what was the value for vitamin D"). Synthea's own
        # Observation rows have a real value for these, so the structured
        # "recent observations" handler can genuinely answer them.
        re.compile(r"\b(lab\w*|laboratory|blood (test\w*|report\w*|work)|test result\w*|vitamin\w*)\b", re.IGNORECASE),
        ["observation"],
        "observation",
    ),
    (
        # "any flagged values"/"what's abnormal" — kept OFF the structured
        # fast path deliberately (intent_kind stays "general", not
        # "observation", so it never qualifies for _STRUCTURED_INTENTS
        # below): Synthea's Observation rows have no flag/abnormal concept
        # at all — that information only exists in a PDF's own printed
        # "NORMAL"/"LOW" text, which only the semantic path over the
        # document's narrative chunks can actually answer. Routing this to
        # answer_recent_observations() would silently ignore the real
        # evidence and risk a wrong or incomplete answer. record_types is
        # still narrowed to "observation" so retrieval stays scoped even on
        # the semantic path.
        re.compile(r"\b(flagged|abnormal\w*|out of range|outside (the )?(reference )?(range|interval))\b", re.IGNORECASE),
        ["observation"],
        "general",
    ),
    (
        re.compile(r"\b(vital\w*|blood pressure|heart rate|pulse|temperature|bmi|body mass|height|weight|o2 sat\w*|oxygen saturation)\b", re.IGNORECASE),
        ["observation"],
        "observation",
    ),
    (re.compile(r"\bobservation\w*\b", re.IGNORECASE), ["observation"], "observation"),
]

# These intents have a deterministic, no-LLM structured handler
# (app.rag.structured_answers.STRUCTURED_HANDLERS). Everything else that
# gets a record_type classification still narrows the *semantic* path.
_STRUCTURED_INTENTS = {
    "medication",
    "allergy",
    "condition",
    "procedure",
    "encounter",
    "finance_payer",
    "finance_outstanding",
    "observation",
}


# Last-resort typo tolerance (section 5 "reasonable variations in spelling,
# typos" — e.g. "wat medicatoin does she take"). Deliberately NOT a general
# fuzzy-match layer: it only runs when every regex rule above found nothing
# at all, and only accepts a close match against this small, specific
# vocabulary (never against patient names or arbitrary free text), so it
# can't override a real match or introduce a surprising reclassification —
# it only recovers the single, clear case where one domain word was
# misspelled and the question would otherwise have fallen through to an
# unscoped semantic search.
_TYPO_VOCAB: list[tuple[str, list[str], str]] = [
    ("medication", ["medication"], "medication"),
    ("allergy", ["allergy"], "allergy"),
    ("condition", ["condition"], "condition"),
    ("diagnosis", ["condition"], "condition"),
    ("procedure", ["procedure"], "procedure"),
    ("encounter", ["encounter"], "encounter"),
    ("observation", ["observation"], "observation"),
    ("laboratory", ["observation"], "observation"),
    ("claim", ["claim", "claim_transaction"], "finance_outstanding"),
    ("insurance", ["payer", "payer_transition"], "finance_payer"),
]
_TYPO_VOCAB_WORDS = [w for w, _, _ in _TYPO_VOCAB]
_WORD_RE = re.compile(r"[A-Za-z]+")


def _typo_tolerant_fallback(question: str) -> tuple[str, str, list[str]] | None:
    for word in _WORD_RE.findall(question.lower()):
        if len(word) < 5:
            continue  # too short for a reliable fuzzy match either way
        match = get_close_matches(word, _TYPO_VOCAB_WORDS, n=1, cutoff=0.8)
        if match:
            canonical = match[0]
            for vocab_word, types, kind in _TYPO_VOCAB:
                if vocab_word == canonical:
                    return types[0], kind, list(types)
    return None


@dataclass
class QueryIntent:
    label: str
    record_types: list[str] | None  # None = unclassified, no narrowing
    observation_categories: list[str] | None
    is_recency: bool
    intent_kind: str  # "patient_identity" | "summary" | one of _STRUCTURED_INTENTS | "general"
    route: str  # "structured" | "summary" | "semantic"
    history: bool = False


def classify_query(question: str, role_is_clinical: bool) -> QueryIntent:
    if _IDENTITY_RE.search(question):
        return QueryIntent(
            label="patient_identity",
            record_types=None,
            observation_categories=None,
            is_recency=False,
            intent_kind="patient_identity",
            route="structured",
        )

    if _SUMMARY_RE.search(question):
        return QueryIntent(
            label="summary",
            record_types=None,
            observation_categories=None,
            is_recency=False,
            intent_kind="summary",
            route="summary",
        )

    is_recency = bool(_RECENCY_RE.search(question))
    history = bool(_HISTORY_RE.search(question))

    # A question can name more than one domain at once ("diagnosis and
    # claim balance") — union every rule that matches rather than stopping
    # at the first, so authorization (which intersects this with the role's
    # allowed types) can still answer from whichever part the role is
    # actually allowed to see, instead of the whole query being denied
    # because one unrelated keyword matched a domain the role can't access.
    record_types: list[str] | None = None
    label = "general"
    intent_kind = "general"
    matched_kinds: list[str] = []
    for pattern, types, kind in _RECORD_TYPE_RULES:
        if pattern.search(question):
            if record_types is None:
                record_types = []
                label = types[0]
                intent_kind = kind
            for t in types:
                if t not in record_types:
                    record_types.append(t)
            if kind not in matched_kinds:
                matched_kinds.append(kind)

    if record_types is None:
        label, intent_kind, record_types = _typo_tolerant_fallback(question) or (label, intent_kind, record_types)
        if record_types is not None:
            matched_kinds.append(intent_kind)

    observation_categories: list[str] | None = None
    if record_types == ["observation"]:
        lowered = question.lower()
        if re.search(r"\blab\w*\b", lowered):
            observation_categories = LABORATORY
        elif re.search(r"\bvital\w*\b", lowered):
            observation_categories = VITAL_SIGNS
        elif re.search(r"\b(survey|social|socioeconomic|living situation|housing|food insecurity)\b", lowered):
            observation_categories = SURVEY_SOCIAL_CATEGORIES
            label = "social_observation"
            intent_kind = "general"  # social-history isn't a structured handler — route semantic
        elif role_is_clinical:
            # A bare "recent observations" from a clinical role means vitals/
            # labs/exam findings, not the socioeconomic survey rows Synthea
            # files under the same table (see module docstring).
            observation_categories = CLINICAL_OBSERVATION_CATEGORIES

    # Only a single, unambiguous structured intent gets the no-LLM fast
    # path — a question spanning multiple domains ("diagnosis and claim
    # balance") is exactly the kind of multi-source question the semantic
    # path's context assembly already handles correctly.
    route = "structured" if len(matched_kinds) == 1 and intent_kind in _STRUCTURED_INTENTS else "semantic"

    return QueryIntent(
        label=label,
        record_types=record_types,
        observation_categories=observation_categories,
        is_recency=is_recency,
        intent_kind=intent_kind if route == "structured" else "general",
        route=route,
        history=history,
    )
