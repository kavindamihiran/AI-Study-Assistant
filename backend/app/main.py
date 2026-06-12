from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.study import router as study_router
from app.api.study_sessions import router as study_sessions_router
from app.config import Settings
from app.database import Database
from app.documents.store import DocumentStore
from app.llm.gateway import LLMGateway
from app.llm.registry import ModelProfileRegistry
from app.llm.transport import OpenAICompatibleTransport
from app.rag.embeddings import HashingEmbeddingProvider, HostedEmbeddingProvider
from app.rag.vector_store import LocalSQLVectorStore, PineconeVectorStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    registry = ModelProfileRegistry.from_json_file(settings.model_profiles_path)
    gateway = LLMGateway(
        registry=registry,
        transport=OpenAICompatibleTransport(
            timeout_seconds=settings.llm_request_timeout_seconds
        ),
        active_profile_id=settings.active_model_profile_id,
    )
    database_url = settings.database_url or Database.sqlite_url(
        settings.data_dir / "study_assistant.db"
    )
    database = Database(database_url)
    database.initialize()

    if settings.embedding_provider == "hosted":
        embedder = HostedEmbeddingProvider(
            model_id=settings.hosted_embedding_model_id,
            dimension=settings.embedding_dimension,
            base_url=os.getenv("AI_BASE_URL", ""),
            timeout_seconds=settings.llm_request_timeout_seconds,
        )
    else:
        embedder = HashingEmbeddingProvider(settings.embedding_dimension)

    if settings.vector_store_provider == "pinecone":
        if not settings.pinecone_api_key or not settings.pinecone_index_host:
            raise RuntimeError(
                "PINECONE_API_KEY and PINECONE_INDEX_HOST are required "
                "when VECTOR_STORE_PROVIDER=pinecone"
            )
        vector_store = PineconeVectorStore(
            api_key=settings.pinecone_api_key,
            index_host=settings.pinecone_index_host,
            namespace=settings.pinecone_namespace,
        )
    else:
        vector_store = LocalSQLVectorStore(database)

    document_store = DocumentStore(
        settings.data_dir,
        database=database,
        embedder=embedder,
        vector_store=vector_store,
    )

    app = FastAPI(title="AI Study Assistant API", version="0.1.0")
    app.state.llm_gateway = gateway
    app.state.database = database
    app.state.document_store = document_store
    app.state.max_upload_bytes = settings.max_upload_mb * 1024 * 1024
    frontend_url = settings.frontend_url.rstrip("/")
    if frontend_url and not frontend_url.startswith(("http://", "https://")):
        frontend_url = f"https://{frontend_url}"
    allowed_origins = {
        frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3200",
        "http://127.0.0.1:3200",
    }
    allowed_origins.discard("")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(documents_router)
    app.include_router(chat_router)
    app.include_router(study_router)
    app.include_router(study_sessions_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["health"])
    async def ready() -> dict:
        profile = registry.get(gateway.active_profile_id)
        data_ready = database.health() and document_store.vector_store.health()
        ai_ready = profile.is_configured
        return {
            "status": "ready" if ai_ready and data_ready else "setup_required",
            "ai_ready": ai_ready,
            "data_ready": data_ready,
            "database": "connected" if database.health() else "unavailable",
        }

    return app


app = create_app()
