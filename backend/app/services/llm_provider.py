"""LLM provider abstraction (docs/RAG_DESIGN.md). Vendor-specific code lives
only here; app.rag.pipeline calls LLMProvider.generate() and never knows
which vendor answered.

If no API key is configured, or the configured call fails, DevModeProvider
is used instead of either crashing the request or silently handing the user
raw database rows as if they were a real answer (that was the previous
behavior — see docs/DECISIONS.md "RAG quality fix"). Its output always
clearly states that generation is unavailable, so a misconfigured demo box
fails loud, not pretty.
"""
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are MediGaurd, a secure hospital information assistant.\n"
    "Use only the authorized context supplied to you below. Never use "
    "outside knowledge.\n"
    "Answer the user's actual question directly and concisely — synthesize "
    "across multiple sources when the answer draws on more than one.\n"
    "Do not copy raw record text verbatim unless the user explicitly asks "
    "for the original record contents.\n"
    "Do not invent information and do not infer anything the context does "
    "not state.\n"
    "Do not reveal or describe any record that was not provided to you.\n"
    "If the supplied context is insufficient to answer, say so plainly "
    "instead of guessing.\n"
    "Every factual claim must carry a citation using only the [SOURCE_n] "
    "markers given in the context — never invent a source number or id.\n"
    "Prefer a short list over a long paragraph when the answer has more "
    "than one part."
)


class LLMProvider:
    def generate(self, context_text: str, question: str) -> str:
        raise NotImplementedError


class DevModeProvider(LLMProvider):
    """No working LLM call available (no key configured, or the call
    failed). Returns an explicit status message — never the raw chunk data
    — so a demo never mistakes "retrieval worked, generation didn't" for a
    real answer."""

    def __init__(self, sources: list[dict], reason: str = "LLM is not configured"):
        self.sources = sources
        self.reason = reason

    def generate(self, context_text: str, question: str) -> str:
        if not self.sources:
            return "I couldn't find enough authorized information to answer that question."
        return (
            f"[DEV MODE] {self.reason}.\n"
            f"The RAG pipeline retrieved {len(self.sources)} authorized source(s) successfully, "
            "but natural-language answer generation is currently unavailable. "
            "Configure GROQ_API_KEY (or another provider) in .env to enable real answers."
        )


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def generate(self, context_text: str, question: str) -> str:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Authorized context:\n{context_text}\n\nQuestion: {question}"},
                ],
                "temperature": 0,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def generate(self, context_text: str, question: str) -> str:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Authorized context:\n{context_text}\n\nQuestion: {question}"},
                ],
                "temperature": 0,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class _SafeProvider(LLMProvider):
    """Wraps a real provider so a vendor-side failure (bad key, decommissioned
    model, rate limit, network error) degrades to DevModeProvider's explicit
    status message instead of a 500 — a demo should never crash on a flaky
    external API."""

    def __init__(self, inner: LLMProvider, sources: list[dict]):
        self.inner = inner
        self.sources = sources

    def generate(self, context_text: str, question: str) -> str:
        try:
            return self.inner.generate(context_text, question)
        except Exception:  # noqa: BLE001 — any vendor failure degrades, never crashes the request
            logger.exception("LLM provider call failed; falling back to dev-mode message.")
            return DevModeProvider(self.sources, reason="The configured LLM call failed").generate(
                context_text, question
            )


def get_llm_provider(sources: list[dict]) -> LLMProvider:
    settings = get_settings()
    key = settings.llm_api_key or settings.groq_api_key or settings.openai_api_key or settings.gemini_api_key
    if not key:
        return DevModeProvider(sources)

    if settings.llm_provider == "groq" and settings.groq_api_key:
        return _SafeProvider(GroqProvider(settings.groq_api_key, settings.llm_model), sources)
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return _SafeProvider(OpenAIProvider(settings.openai_api_key, settings.llm_model), sources)
    return DevModeProvider(sources)
