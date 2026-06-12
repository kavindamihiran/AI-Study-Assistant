from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .exceptions import ProfileConfigurationError, ProfileNotFoundError
from .models import ModelCapabilities, ModelDefaults, ModelProfile


_ENV_PATTERN = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)(?::-(.*))?\}$")


def _expand_env(value: Any, env: Mapping[str, str]) -> Any:
    if not isinstance(value, str):
        return value
    match = _ENV_PATTERN.match(value)
    if not match:
        return value
    name, default = match.groups()
    return env.get(name, default or "")


class ModelProfileRegistry:
    def __init__(self, profiles: Iterable[ModelProfile]) -> None:
        self._profiles = {profile.profile_id: profile for profile in profiles}
        if not self._profiles:
            raise ProfileConfigurationError("At least one model profile is required")
        self._validate_fallbacks()

    @classmethod
    def from_json_file(
        cls,
        path: str | Path,
        *,
        env: Mapping[str, str] | None = None,
    ) -> "ModelProfileRegistry":
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ProfileConfigurationError("Model profiles file must contain a list")
        return cls.from_data(payload, env=env)

    @classmethod
    def from_data(
        cls,
        payload: Iterable[Mapping[str, Any]],
        *,
        env: Mapping[str, str] | None = None,
    ) -> "ModelProfileRegistry":
        environment = env if env is not None else os.environ
        return cls(cls._parse_profile(item, environment) for item in payload)

    @staticmethod
    def _parse_profile(
        data: Mapping[str, Any], env: Mapping[str, str]
    ) -> ModelProfile:
        capabilities = data.get("capabilities", {})
        defaults = data.get("defaults", {})
        allowed = frozenset(data.get("allowed_extra_body_fields", []))
        disallowed = frozenset(data.get("disallowed_request_fields", []))
        overlap = allowed & disallowed
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ProfileConfigurationError(
                f"Fields cannot be both allowed and disallowed: {names}"
            )

        try:
            return ModelProfile(
                profile_id=str(data["profile_id"]),
                display_name=str(data["display_name"]),
                provider_name=str(data["provider_name"]),
                base_url=str(_expand_env(data["base_url"], env)).rstrip("/"),
                model_id=str(_expand_env(data["model_id"], env)),
                api_key_env_name=str(data["api_key_env_name"]),
                max_context_tokens=int(data["max_context_tokens"]),
                capabilities=ModelCapabilities(**capabilities),
                defaults=ModelDefaults(**defaults),
                allowed_extra_body_fields=allowed,
                disallowed_request_fields=disallowed,
                output_parser_type=str(
                    data.get("output_parser_type", "openai_compatible")
                ),
                prompt_style=str(data.get("prompt_style", "default")),
                fallback_model_profile_id=data.get("fallback_model_profile_id"),
                enabled=bool(data.get("enabled", True)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            profile_id = data.get("profile_id", "<unknown>")
            raise ProfileConfigurationError(
                f"Invalid model profile {profile_id}: {exc}"
            ) from exc

    def _validate_fallbacks(self) -> None:
        for profile in self._profiles.values():
            fallback = profile.fallback_model_profile_id
            if fallback and fallback not in self._profiles:
                raise ProfileConfigurationError(
                    f"Profile {profile.profile_id} references missing fallback {fallback}"
                )
            if fallback == profile.profile_id:
                raise ProfileConfigurationError(
                    f"Profile {profile.profile_id} cannot fall back to itself"
                )

    def get(self, profile_id: str, *, require_enabled: bool = True) -> ModelProfile:
        try:
            profile = self._profiles[profile_id]
        except KeyError as exc:
            raise ProfileNotFoundError(
                f"Unknown model profile: {profile_id}"
            ) from exc
        if require_enabled and not profile.enabled:
            raise ProfileConfigurationError(
                f"Model profile is disabled: {profile_id}"
            )
        return profile

    def list_profiles(self, *, enabled_only: bool = False) -> list[ModelProfile]:
        profiles = self._profiles.values()
        if enabled_only:
            profiles = (profile for profile in profiles if profile.enabled)
        return sorted(profiles, key=lambda profile: profile.profile_id)
