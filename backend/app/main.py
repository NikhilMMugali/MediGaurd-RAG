import logging

# Trust the operating system's certificate store (macOS Keychain, Windows
# store) the way a browser does, instead of only Python's bundled certifi
# list. A VPN, antivirus, or corporate proxy that re-signs HTTPS traffic
# installs its root CA in the OS store; without this, outbound calls (the
# Groq LLM call) fail with CERTIFICATE_VERIFY_FAILED while the browser works.
# Verification stays fully on: self-signed, expired, and untrusted-root
# certificates are still rejected. Must run before any httpx client is built.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # optional: falls back to certifi, never blocks startup
    pass

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, auth, health, image_upload, insights, patients, rag, upload
from app.config import get_settings
from app.utils.logging import configure_logging

settings = get_settings()
configure_logging(debug=settings.app_debug)

app = FastAPI(title=settings.app_name)

logger = logging.getLogger(__name__)


@app.on_event("startup")
def preload_rag_dependencies() -> None:
    """Loads the embedding model and opens the Qdrant collection once, at
    server boot, instead of on whichever request happens to be first. This
    is the difference between the demo's first chat message paying a
    multi-second cold-load cost live in front of a jury, versus paying it
    here before anyone's watching."""
    from app.services.embedding_provider import get_embedding_provider
    from app.services.vector_store import get_vector_store

    try:
        embedder = get_embedding_provider()
        store = get_vector_store()
        store.ensure_collection(embedder.dimension)
        logger.info("RAG dependencies preloaded (collection count: %s)", store.count())
    except Exception:  # noqa: BLE001 — never block startup over this; first request will retry
        logger.exception("Failed to preload RAG dependencies; will load lazily on first request.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(image_upload.router)
app.include_router(patients.router)
app.include_router(admin.router)
app.include_router(rag.router)
app.include_router(insights.router)
