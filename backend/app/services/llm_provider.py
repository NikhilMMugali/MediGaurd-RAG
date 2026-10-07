"""LLM provider abstraction (docs/RAG_DESIGN.md). Vendor-specific code lives
only here; app.rag.pipeline calls LLMProvider.generate() and never knows
which vendor answered.

If no API key is configured for the selected provider (common for an
offline hackathon demo box), ExtractiveFallbackProvider is used instead of
failing the request: it never invents text — it returns the single most
relevant authorized chunk's own content, verbatim, with its citation. That
keeps every answer strictly grounded even with zero external API calls.
"""
import httpx

from app.config import get_settings

SYSTEM_PROMPT = (
    "You are MediGaurd, a secure hospital information assistant.\n"
    "You may answer only from the authorized context supplied to you.\n"
    "Do not use outside knowledge to invent facts.\n"
    "Do not infer missing medical, financial, or personal information.\n"
    "Do not reveal restricted information.\n"
    "If the authorized context is insufficient, explicitly say that the "
    "requested information is not available in your authorized context.\n"
    "Every factual claim must include an exact source citation using the "
    "[SOURCE_n] markers given in the context.\n"
    "Never create a citation that is not present in the context.\n"
    "Never mention or describe restricted records that were not provided."
)


class LLMProvider:
    def generate(self, context_text: str, question: str) -> str:
        raise NotImplementedError


class ExtractiveFallbackProvider(LLMProvider):
    """No external LLM call: returns the top chunk's own text, cited. Used
    when no provider API key is configured."""

    def __init__(self, sources: list[dict]):
        self.sources = sources

    def generate(self, context_text: str, question: str) -> str:
        if not self.sources:
            return "I couldn't find enough authorized information to answer that question."
        top = self.sources[0]
        return f"{top['content'].strip()}\n[SOURCE_1]"


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


def get_llm_provider(sources: list[dict]) -> LLMProvider:
    settings = get_settings()
    key = settings.llm_api_key or settings.groq_api_key or settings.openai_api_key or settings.gemini_api_key
    if not key:
        return ExtractiveFallbackProvider(sources)

    if settings.llm_provider == "groq" and settings.groq_api_key:
        return GroqProvider(settings.groq_api_key, settings.llm_model)
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key, settings.llm_model)
    return ExtractiveFallbackProvider(sources)
