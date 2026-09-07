from __future__ import annotations

from fastapi import HTTPException, Request

from app.llm.exceptions import LLMGatewayError
from app.llm.models import ModelProfile
from app.llm.user_models import UserModelStore, build_user_profile


def managed_fallback_profile_id(request: Request) -> str | None:
    """The server-managed profile id, but only when it is actually usable."""
    gateway = request.app.state.llm_gateway
    profile_id = gateway.active_profile_id
    registry = getattr(gateway, "registry", None)
    if registry is None:
        # A gateway without a registry (a test double) manages its own model.
        return profile_id
    try:
        profile = registry.get(profile_id, require_enabled=False)
    except LLMGatewayError:
        return None
    return profile_id if profile.is_configured else None


def user_model_profile(request: Request, user_id: str) -> ModelProfile | None:
    """Build the caller's own model profile, or ``None`` to use the managed one."""
    store: UserModelStore | None = getattr(
        request.app.state, "user_model_store", None
    )
    if store is None:
        return None
    config = store.get_usable(user_id=user_id)
    if config is None:
        return None
    return build_user_profile(
        config, fallback_profile_id=managed_fallback_profile_id(request)
    )


def resolve_model_for_user(
    request: Request, user_id: str
) -> tuple[ModelProfile | None, str]:
    """Pick the model for this request and fail loudly when none is configured.

    Returns the per-user profile override (or ``None`` when the managed model
    should be used) together with the profile id to record on the model run.
    """
    override = user_model_profile(request, user_id)
    if override is not None:
        return override, override.profile_id
    managed_id = managed_fallback_profile_id(request)
    if managed_id is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No AI model is configured yet. Open Settings and add your own "
                "OpenAI-compatible API key, base URL, and model ID."
            ),
        )
    return None, managed_id
