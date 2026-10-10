from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MediGaurd RAG"
    app_env: str = "development"
    app_secret_key: str = "change-me"
    app_debug: bool = True

    access_token_expire_minutes: int = 120
    jwt_algorithm: str = "HS256"

    database_url: str = "postgresql+psycopg://medigaurd:medigaurd@localhost:5432/medigaurd"

    # "local" uses qdrant-client's embedded on-disk mode (no server process
    # needed — important on a machine where Docker isn't available); "server"
    # connects to qdrant_url instead.
    qdrant_mode: str = "local"
    qdrant_path: str = "./data/qdrant"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "mediguard_knowledge"
    qdrant_api_key: str | None = None

    embedding_provider: str = "sentence_transformers"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_batch_size: int = 200

    llm_provider: str = "groq"
    # llama-3.1-70b-versatile was decommissioned by Groq; verified against
    # this account's /v1/models listing as a currently active text model.
    llm_model: str = "openai/gpt-oss-120b"
    llm_api_key: str | None = None
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    openai_api_key: str | None = None

    # rag_top_k: how many candidate knowledge records retrieval considers
    # (post metadata-filter, pre final ranking). rag_context_k: how many of
    # those actually get sent to the LLM as context — kept smaller so the
    # prompt stays small and the answer stays focused (docs/RAG_DESIGN.md
    # "retrieval pipeline").
    rag_top_k: int = 8
    rag_context_k: int = 5
    # Cosine similarity floor (embeddings are normalized — see
    # services/embedding_provider.py) below which a retrieved chunk is
    # treated as "not actually relevant" rather than attached as a citation.
    # Was 0.0 — which combined with a since-fixed `or None` bug in
    # VectorStore.search() meant no threshold was ever really applied, so an
    # unrelated top-k chunk (wrong patient, wrong topic) was always shown as
    # if it supported the answer (docs/DECISIONS.md "relevance floor").
    rag_score_threshold: float = 0.35

    max_upload_size_mb: int = 20
    upload_dir: str = "./data/uploads"

    # OCR image upload (app.ingestion.image_pipeline). The pixel cap is a
    # decompression-bomb guard: a tiny, highly compressed file can declare
    # billions of pixels and exhaust memory on decode. The side cap bounds
    # CPU time per image — larger images are downscaled for OCR only (the
    # stored original is untouched and box coordinates are mapped back).
    ocr_max_image_pixels: int = 40_000_000
    ocr_max_side_px: int = 2600
    # Below either threshold the result is "needs review", never "ready":
    # a confident-looking answer built on garbled text is worse than none.
    ocr_min_mean_confidence: float = 0.55
    ocr_min_text_chars: int = 15

    # The app imports from the clean, deterministic 100-patient dataset
    # (docs/CLEAN_DATASET.md), not the raw Synthea export directly.
    synthea_csv_dir: str = "./data/clean"


@lru_cache
def get_settings() -> Settings:
    return Settings()
