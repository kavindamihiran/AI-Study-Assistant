from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.models import router as models_router
from app.config import Settings
from app.llm.gateway import LLMGateway
from app.llm.registry import ModelProfileRegistry
from app.llm.transport import OpenAICompatibleTransport


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    registry = ModelProfileRegistry.from_json_file(settings.model_profiles_path)
    gateway = LLMGateway(
        registry=registry,
        transport=OpenAICompatibleTransport(
            timeout_seconds=settings.llm_request_timeout_seconds
        ),
        active_profile_id=settings.active_model_profile_id,
    )

    app = FastAPI(title="AI Study Assistant API", version="0.1.0")
    app.state.llm_gateway = gateway
    allowed_origins = {
        settings.frontend_url.rstrip("/"),
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3200",
        "http://127.0.0.1:3200",
    }
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(models_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["health"])
    async def ready() -> dict[str, str | bool]:
        profile = registry.get(gateway.active_profile_id)
        return {
            "status": "ready" if profile.is_configured else "configuration_required",
            "active_profile_id": profile.profile_id,
            "model_configured": profile.is_configured,
        }

    return app


app = create_app()
