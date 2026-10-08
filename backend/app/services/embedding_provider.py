"""Embedding provider abstraction (docs/ARCHITECTURE.md). Today this wraps a
local Sentence Transformers model so the prototype needs no external API key
to embed; the model is configurable via EMBEDDING_MODEL and the interface is
narrow enough to swap in a hosted embedding API later without touching
callers.
"""
from functools import lru_cache

from app.config import get_settings


class EmbeddingProvider:
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @property
    def dimension(self) -> int:
        raise NotImplementedError


class SentenceTransformersProvider(EmbeddingProvider):
    def __init__(self, model_name: str):
        import os

        # Once the model is cached locally, every subsequent load otherwise
        # still makes several HEAD/GET round-trips to huggingface.co just to
        # check for updates (visible in the logs as 10-40s of network calls
        # before the model actually loads). Skip that network dependency —
        # we always want the model that was cached at install time anyway.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._dimension = self._model.get_sentence_embedding_dimension()

    def embed_text(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()

    @property
    def dimension(self) -> int:
        return self._dimension


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "sentence_transformers":
        return SentenceTransformersProvider(settings.embedding_model)
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {settings.embedding_provider}")
