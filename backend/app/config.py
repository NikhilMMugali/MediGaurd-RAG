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

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "medigaurd_knowledge"
    qdrant_api_key: str | None = None

    embedding_provider: str = "sentence_transformers"
    embedding_model: str = "all-MiniLM-L6-v2"

    llm_provider: str = "groq"
    llm_model: str = "llama-3.1-70b-versatile"
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    openai_api_key: str | None = None

    max_upload_size_mb: int = 20
    upload_dir: str = "./data/uploads"

    synthea_csv_dir: str = "./data/synthea"


@lru_cache
def get_settings() -> Settings:
    return Settings()
