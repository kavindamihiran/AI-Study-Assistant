from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import current_auth, require_authenticated_request
from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage
from app.llm.user_models import (
    UserModelConfig,
    UserModelConfigError,
    UserModelStore,
    build_user_profile,
    config_with_api_key,
    normalize_base_url,
)

from .model_context import managed_fallback_profile_id


router = APIRouter(
    prefix="/api/settings/model",
    tags=["settings"],
    dependencies=[Depends(require_authenticated_request)],
)

TEST_PROMPT = "Reply with exactly: connection successful"

# Documented API roots for providers that speak the OpenAI chat-completions
# protocol. They are hints for the settings form only; any other compatible
# endpoint can be typed in by hand.
PROVIDER_PRESETS: list[dict[str, str]] = [
    {
        "id": "nvidia",
        "label": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "example_model_id": "meta/llama-3.3-70b-instruct",
        "api_key_url": "https://build.nvidia.com/",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "example_model_id": "gpt-4o-mini",
        "api_key_url": "https://platform.openai.com/api-keys",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "example_model_id": "meta-llama/llama-3.3-70b-instruct",
        "api_key_url": "https://openrouter.ai/keys",
    },
    {
        "id": "groq",
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "example_model_id": "llama-3.3-70b-versatile",
        "api_key_url": "https://console.groq.com/keys",
    },
    {
        "id": "together",
        "label": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "example_model_id": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "api_key_url": "https://api.together.ai/settings/api-keys",
    },
    {
        "id": "mistral",
        "label": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "example_model_id": "mistral-large-latest",
        "api_key_url": "https://console.mistral.ai/api-keys/",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "example_model_id": "deepseek-chat",
        "api_key_url": "https://platform.deepseek.com/api_keys",
    },
    {
        "id": "ollama",
        "label": "Ollama (local)",
        "base_url": "http://127.0.0.1:11434/v1",
        "example_model_id": "llama3.1",
        "api_key_url": "",
    },
    {
        "id": "custom",
        "label": "Other OpenAI-compatible endpoint",
        "base_url": "",
        "example_model_id": "",
        "api_key_url": "",
    },
]


class ModelSettingsPayload(BaseModel):
    display_name: str = Field(default="My model", max_length=120)
    provider_name: str = Field(default="custom", max_length=64)
    base_url: str = Field(min_length=1, max_length=512)
    model_id: str = Field(min_length=1, max_length=255)
    api_key: str | None = Field(default=None, max_length=512)
    temperature: float = Field(default=0.2, ge=0, le=2)
    top_p: float = Field(default=0.95, gt=0, le=1)
    max_tokens: int = Field(default=2048, ge=64, le=32000)
    max_context_tokens: int = Field(default=32768, ge=1024, le=2_000_000)
    supports_streaming: bool = True
    supports_system_message: bool = True
    supports_json_mode: bool = False
    fallback_to_managed: bool = True
    is_enabled: bool = True


class ModelTestPayload(BaseModel):
    """Test either the saved settings or a form the student has not saved yet."""

    base_url: str | None = Field(default=None, max_length=512)
    model_id: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, max_length=512)
    supports_system_message: bool = True
    prompt: str = Field(default=TEST_PROMPT, min_length=1, max_length=500)


class ModelCatalogPayload(BaseModel):
    base_url: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=512)


def _store(request: Request) -> UserModelStore:
    store: UserModelStore | None = getattr(
        request.app.state, "user_model_store", None
    )
    if store is None:
        raise HTTPException(
            status_code=503, detail="Model settings storage is unavailable"
        )
    return store


def _managed_state(request: Request) -> dict[str, Any]:
    managed_id = managed_fallback_profile_id(request)
    return {
        "configured": managed_id is not None,
        "display_name": "Shared study assistant",
        "description": (
            "The model the server operator configured. Used when you have not "
            "added your own, and as a fallback when yours is unavailable."
        ),
    }


def _settings_response(
    request: Request, config: UserModelConfig | None
) -> dict[str, Any]:
    return {
        "managed": _managed_state(request),
        "custom": (
            config.public_dict()
            if config
            else {"configured": False, "is_enabled": False}
        ),
        "presets": PROVIDER_PRESETS,
        "active_source": "custom" if config and config.is_enabled else "managed",
    }


@router.get("")
async def read_model_settings(request: Request) -> dict[str, Any]:
    user_id = current_auth(request).user_id
    return _settings_response(request, _store(request).get(user_id=user_id))


@router.put("")
async def save_model_settings(
    payload: ModelSettingsPayload, request: Request
) -> dict[str, Any]:
    user_id = current_auth(request).user_id
    try:
        config = _store(request).save(
            user_id=user_id,
            display_name=payload.display_name,
            provider_name=payload.provider_name,
            base_url=payload.base_url,
            model_id=payload.model_id,
            api_key=(payload.api_key or "").strip() or None,
            temperature=payload.temperature,
            top_p=payload.top_p,
            max_tokens=payload.max_tokens,
            max_context_tokens=payload.max_context_tokens,
            supports_streaming=payload.supports_streaming,
            supports_system_message=payload.supports_system_message,
            supports_json_mode=payload.supports_json_mode,
            fallback_to_managed=payload.fallback_to_managed,
            is_enabled=payload.is_enabled,
        )
    except UserModelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _settings_response(request, config)


@router.delete("")
async def delete_model_settings(request: Request) -> dict[str, Any]:
    user_id = current_auth(request).user_id
    _store(request).delete(user_id=user_id)
    return _settings_response(request, None)


@router.post("/test")
async def test_model_settings(
    payload: ModelTestPayload, request: Request
) -> dict[str, Any]:
    user_id = current_auth(request).user_id
    store = _store(request)
    saved = store.get(user_id=user_id)

    base_url = (payload.base_url or (saved.base_url if saved else "")).strip()
    model_id = (payload.model_id or (saved.model_id if saved else "")).strip()
    api_key = (payload.api_key or "").strip() or (saved.api_key if saved else "")
    if not (base_url and model_id and api_key):
        raise HTTPException(
            status_code=400,
            detail="A base URL, model ID, and API key are required to test the connection.",
        )

    try:
        candidate = UserModelConfig(
            user_id=user_id,
            display_name=saved.display_name if saved else "My model",
            provider_name=saved.provider_name if saved else "custom",
            base_url=normalize_base_url(base_url),
            model_id=model_id,
            api_key=api_key,
            api_key_hint="",
            temperature=saved.temperature if saved else 0.2,
            top_p=saved.top_p if saved else 0.95,
            max_tokens=256,
            max_context_tokens=(
                saved.max_context_tokens if saved else 32768
            ),
            supports_streaming=saved.supports_streaming if saved else True,
            supports_system_message=payload.supports_system_message,
            supports_json_mode=saved.supports_json_mode if saved else False,
            fallback_to_managed=False,
        )
    except UserModelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    gateway: LLMGateway = request.app.state.llm_gateway
    result = await gateway.generate_text(
        [ChatMessage("user", payload.prompt)],
        profile_override=build_user_profile(
            config_with_api_key(candidate, api_key), fallback_profile_id=None
        ),
        max_tokens=64,
        use_fallback=False,
    )
    if saved is not None:
        store.record_verification(
            user_id=user_id, error=None if result.ok else result.error_message
        )
    if not result.ok:
        return {
            "ok": False,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "latency_ms": result.latency_ms,
        }
    return {
        "ok": True,
        "text": result.text.strip()[:500],
        "latency_ms": result.latency_ms,
        "usage": result.usage.as_dict(),
    }


def _fetch_models(base_url: str, api_key: str, timeout: float) -> list[str]:
    request_object = urllib.request.Request(
        f"{base_url}/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request_object, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    entries = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    model_ids: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            model_ids.append(entry)
        elif isinstance(entry, dict):
            identifier = entry.get("id") or entry.get("name")
            if isinstance(identifier, str) and identifier:
                model_ids.append(identifier)
    return sorted(dict.fromkeys(model_ids))


@router.post("/catalog")
async def list_provider_models(
    payload: ModelCatalogPayload, request: Request
) -> dict[str, Any]:
    """List the models the provider exposes, so the student can pick one."""
    user_id = current_auth(request).user_id
    saved = _store(request).get(user_id=user_id)
    base_url = (payload.base_url or (saved.base_url if saved else "")).strip()
    api_key = (payload.api_key or "").strip() or (saved.api_key if saved else "")
    if not (base_url and api_key):
        raise HTTPException(
            status_code=400,
            detail="A base URL and API key are required to list models.",
        )
    timeout = float(
        getattr(request.app.state.settings, "llm_request_timeout_seconds", 30.0)
    )
    try:
        models = await asyncio.to_thread(
            _fetch_models, normalize_base_url(base_url), api_key, min(timeout, 30.0)
        )
    except UserModelConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except urllib.error.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"The provider returned HTTP {exc.code} for its model list. "
                "You can still type the model ID by hand."
            ),
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "The provider did not return a usable model list. "
                "You can still type the model ID by hand."
            ),
        ) from exc
    return {"models": models}
