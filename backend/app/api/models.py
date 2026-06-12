from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.llm.exceptions import LLMGatewayError
from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage


router = APIRouter(prefix="/api/models", tags=["models"])


class ModelSwitchRequest(BaseModel):
    profile_id: str


class ModelTestRequest(BaseModel):
    profile_id: str | None = None
    prompt: str = Field(
        default="Reply with exactly: model connection successful",
        min_length=1,
        max_length=2000,
    )


def _gateway(request: Request) -> LLMGateway:
    return request.app.state.llm_gateway


@router.get("/profiles")
async def list_model_profiles(request: Request) -> dict:
    gateway = _gateway(request)
    return {
        "profiles": [
            profile.public_dict() for profile in gateway.registry.list_profiles()
        ]
    }


@router.get("/active")
async def get_active_model(request: Request) -> dict:
    gateway = _gateway(request)
    profile = gateway.registry.get(gateway.active_profile_id)
    return profile.public_dict()


@router.post("/switch")
async def switch_active_model(
    payload: ModelSwitchRequest, request: Request
) -> dict:
    gateway = _gateway(request)
    try:
        profile = gateway.resolve_profile(payload.profile_id)
    except LLMGatewayError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    gateway.active_profile_id = profile.profile_id
    return profile.public_dict()


@router.post("/test")
async def test_model(payload: ModelTestRequest, request: Request) -> dict:
    gateway = _gateway(request)
    response = await gateway.generate_text(
        [ChatMessage("user", payload.prompt)],
        profile_id=payload.profile_id,
        max_tokens=128,
        use_fallback=False,
    )
    if not response.ok:
        raise HTTPException(status_code=502, detail=response.public_dict())
    return response.public_dict()

