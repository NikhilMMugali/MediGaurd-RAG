"""Deterministic, keyword-based query classification (docs/RAG_DESIGN.md
"retrieval pipeline"). Not an LLM call and not an agent — a plain lookup so
retrieval can narrow to the record types the question is actually about
*before* vector search runs, instead of handing the LLM a grab-bag of every
record type the role is allowed to see and hoping cosine similarity sorts it
out. Authorization still has the final word: app.rag.pipeline always
intersects record_types here with AuthorizationContext.allowed_record_types,
never uses this module's output on its own.
"""
import re
from dataclasses import dataclass

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

# Ordered most-specific-first: the first match wins, so "lab" before the
# generic "observation" catch-all, etc.
_RECORD_TYPE_RULES: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"\b(medication|drug|prescri\w*|dose|dosage)\b", re.IGNORECASE), ["medication"]),
    (re.compile(r"\b(allergy|allergies|allergic)\b", re.IGNORECASE), ["allergy"]),
    (re.compile(r"\b(diagnos\w*|condition)\b", re.IGNORECASE), ["condition"]),
    (
        re.compile(r"\b(encounter|visit|admission|admitted|appointment)\b", re.IGNORECASE),
        ["encounter"],
    ),
    (
        re.compile(r"\b(claim|bill\w*|invoice|outstanding|balance|payment|owe\w*|amount due|copay)\b", re.IGNORECASE),
        ["claim", "claim_transaction"],
    ),
    (
        re.compile(r"\b(lab|labs|laboratory|blood test|test result\w*)\b", re.IGNORECASE),
        ["observation"],
    ),
    (
        re.compile(r"\b(vital\w*|blood pressure|heart rate|pulse|temperature|bmi|body mass|height|weight|o2 sat\w*|oxygen saturation)\b", re.IGNORECASE),
        ["observation"],
    ),
    (re.compile(r"\bobservation\w*\b", re.IGNORECASE), ["observation"]),
]


@dataclass
class QueryIntent:
    label: str
    record_types: list[str] | None  # None = unclassified, no narrowing
    observation_categories: list[str] | None
    is_recency: bool


def classify_query(question: str, role_is_clinical: bool) -> QueryIntent:
    is_recency = bool(_RECENCY_RE.search(question))

    # A question can name more than one domain at once ("diagnosis and
    # claim balance") — union every rule that matches rather than stopping
    # at the first, so authorization (which intersects this with the role's
    # allowed types) can still answer from whichever part the role is
    # actually allowed to see, instead of the whole query being denied
    # because one unrelated keyword matched a domain the role can't access.
    record_types: list[str] | None = None
    label = "general"
    for pattern, types in _RECORD_TYPE_RULES:
        if pattern.search(question):
            if record_types is None:
                record_types = []
                label = types[0]
            for t in types:
                if t not in record_types:
                    record_types.append(t)

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
        elif role_is_clinical:
            # A bare "recent observations" from a clinical role means vitals/
            # labs/exam findings, not the socioeconomic survey rows Synthea
            # files under the same table (see module docstring).
            observation_categories = CLINICAL_OBSERVATION_CATEGORIES

    return QueryIntent(
        label=label,
        record_types=record_types,
        observation_categories=observation_categories,
        is_recency=is_recency,
    )
