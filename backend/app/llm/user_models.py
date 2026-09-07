from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.database import Database, UserModelSettingModel
from app.database.models import utc_now
from app.security.secret_box import SecretBox, SecretDecryptionError, mask_secret

from .models import ModelCapabilities, ModelDefaults, ModelProfile


USER_PROFILE_ID = "user_custom"
USER_PROVIDER_NAME = "user_provided"
DEFAULT_MAX_CONTEXT_TOKENS = 32768


class UserModelConfigError(ValueError):
    """Raised when a student's provider settings are not usable."""


@dataclass(frozen=True, slots=True)
class UserModelConfig:
    user_id: str
    display_name: str
    provider_name: str
    base_url: str
    model_id: str
    api_key: str
    api_key_hint: str
    temperature: float = 0.2
    top_p: float = 0.95
    max_tokens: int = 2048
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
    supports_streaming: bool = True
    supports_system_message: bool = True
    supports_json_mode: bool = False
    fallback_to_managed: bool = True
    is_enabled: bool = True
    last_verified_at: datetime | None = None
    last_error: str | None = None

    def public_dict(self) -> dict[str, Any]:
        """Settings as shown back to their owner, with the API key redacted."""
        return {
            "configured": True,
            "display_name": self.display_name,
            "provider_name": self.provider_name,
            "base_url": self.base_url,
            "model_id": self.model_id,
            "api_key_hint": self.api_key_hint,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "max_context_tokens": self.max_context_tokens,
            "supports_streaming": self.supports_streaming,
            "supports_system_message": self.supports_system_message,
            "supports_json_mode": self.supports_json_mode,
            "fallback_to_managed": self.fallback_to_managed,
            "is_enabled": self.is_enabled,
            "last_verified_at": (
                self.last_verified_at.isoformat()
                if self.last_verified_at
                else None
            ),
            "last_error": self.last_error,
        }


def normalize_base_url(raw: str) -> str:
    """Accept the URL forms providers document and reduce them to an API root."""
    value = (raw or "").strip().rstrip("/")
    if not value:
        raise UserModelConfigError("A provider base URL is required")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    for suffix in ("/chat/completions", "/completions"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value.rstrip("/")


def build_user_profile(
    config: UserModelConfig,
    *,
    fallback_profile_id: str | None = None,
) -> ModelProfile:
    """Turn saved settings into a single-user, OpenAI-compatible model profile."""
    disallowed = {"tools", "tool_choice", "parallel_tool_calls"}
    allowed: set[str] = set()
    if config.supports_json_mode:
        allowed.add("response_format")
    else:
        disallowed.add("response_format")
    return ModelProfile(
        profile_id=USER_PROFILE_ID,
        display_name=config.display_name or "My model",
        provider_name=USER_PROVIDER_NAME,
        base_url=config.base_url,
        model_id=config.model_id,
        api_key_env_name="",
        api_key_value=config.api_key,
        max_context_tokens=config.max_context_tokens,
        capabilities=ModelCapabilities(
            streaming=config.supports_streaming,
            json_mode=config.supports_json_mode,
            tool_calling=False,
            reasoning_mode=False,
            vision=False,
            system_message=config.supports_system_message,
            structured_output=False,
        ),
        defaults=ModelDefaults(
            temperature=config.temperature,
            top_p=config.top_p,
            max_tokens=config.max_tokens,
        ),
        allowed_extra_body_fields=frozenset(allowed),
        disallowed_request_fields=frozenset(disallowed),
        output_parser_type="openai_compatible",
        prompt_style="default",
        fallback_model_profile_id=(
            fallback_profile_id if config.fallback_to_managed else None
        ),
        enabled=config.is_enabled,
    )


class UserModelStore:
    """Reads and writes each student's own provider credentials and model choice."""

    def __init__(self, database: Database, secret_box: SecretBox) -> None:
        self._database = database
        self._secret_box = secret_box

    def _to_config(self, row: UserModelSettingModel) -> UserModelConfig:
        try:
            api_key = self._secret_box.decrypt(row.api_key_encrypted)
        except SecretDecryptionError:
            api_key = ""
        return UserModelConfig(
            user_id=row.user_id,
            display_name=row.display_name,
            provider_name=row.provider_name,
            base_url=row.base_url,
            model_id=row.model_id,
            api_key=api_key,
            api_key_hint=row.api_key_hint,
            temperature=row.temperature,
            top_p=row.top_p,
            max_tokens=row.max_tokens,
            max_context_tokens=row.max_context_tokens,
            supports_streaming=row.supports_streaming,
            supports_system_message=row.supports_system_message,
            supports_json_mode=row.supports_json_mode,
            fallback_to_managed=row.fallback_to_managed,
            is_enabled=row.is_enabled,
            last_verified_at=row.last_verified_at,
            last_error=row.last_error,
        )

    def get(self, *, user_id: str) -> UserModelConfig | None:
        with self._database.session() as session:
            row = session.get(UserModelSettingModel, user_id)
            return self._to_config(row) if row else None

    def get_usable(self, *, user_id: str) -> UserModelConfig | None:
        """Return settings only when they can actually drive a request."""
        config = self.get(user_id=user_id)
        if config is None or not config.is_enabled:
            return None
        if not (config.base_url and config.model_id and config.api_key):
            return None
        return config

    def save(
        self,
        *,
        user_id: str,
        display_name: str,
        provider_name: str,
        base_url: str,
        model_id: str,
        api_key: str | None,
        temperature: float,
        top_p: float,
        max_tokens: int,
        max_context_tokens: int,
        supports_streaming: bool,
        supports_system_message: bool,
        supports_json_mode: bool,
        fallback_to_managed: bool,
        is_enabled: bool,
    ) -> UserModelConfig:
        normalized_url = normalize_base_url(base_url)
        model_id = (model_id or "").strip()
        if not model_id:
            raise UserModelConfigError("A model ID is required")
        with self._database.session() as session:
            row = session.get(UserModelSettingModel, user_id)
            if row is None:
                if not api_key:
                    raise UserModelConfigError("An API key is required")
                row = UserModelSettingModel(user_id=user_id)
                session.add(row)
            if api_key:
                row.api_key_encrypted = self._secret_box.encrypt(api_key)
                row.api_key_hint = mask_secret(api_key)
            row.display_name = (display_name or "My model").strip()[:120]
            row.provider_name = (provider_name or "custom").strip()[:64]
            row.base_url = normalized_url
            row.model_id = model_id
            row.temperature = temperature
            row.top_p = top_p
            row.max_tokens = max_tokens
            row.max_context_tokens = max_context_tokens
            row.supports_streaming = supports_streaming
            row.supports_system_message = supports_system_message
            row.supports_json_mode = supports_json_mode
            row.fallback_to_managed = fallback_to_managed
            row.is_enabled = is_enabled
            row.last_error = None
            session.flush()
            return self._to_config(row)

    def record_verification(
        self, *, user_id: str, error: str | None
    ) -> UserModelConfig | None:
        with self._database.session() as session:
            row = session.get(UserModelSettingModel, user_id)
            if row is None:
                return None
            row.last_error = error
            if error is None:
                row.last_verified_at = utc_now()
            session.flush()
            return self._to_config(row)

    def delete(self, *, user_id: str) -> bool:
        with self._database.session() as session:
            row = session.get(UserModelSettingModel, user_id)
            if row is None:
                return False
            session.delete(row)
            return True

    def list_all(self) -> list[UserModelConfig]:
        with self._database.session() as session:
            rows = session.execute(select(UserModelSettingModel)).scalars().all()
            return [self._to_config(row) for row in rows]


def config_with_api_key(
    config: UserModelConfig, api_key: str | None
) -> UserModelConfig:
    """Overlay an unsaved API key so a connection can be tested before saving."""
    if not api_key:
        return config
    return replace(config, api_key=api_key, api_key_hint=mask_secret(api_key))
