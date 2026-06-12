from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.llm.models import ModelCapabilities, ModelDefaults, ModelProfile


def make_profile(
    profile_id: str = "primary",
    *,
    fallback_model_profile_id: str | None = None,
    capabilities: ModelCapabilities | None = None,
    allowed_extra_body_fields: frozenset[str] = frozenset(),
    disallowed_request_fields: frozenset[str] = frozenset(),
) -> ModelProfile:
    return ModelProfile(
        profile_id=profile_id,
        display_name=profile_id.title(),
        provider_name="test",
        base_url="https://example.test/v1",
        model_id=f"models/{profile_id}",
        api_key_env_name="TEST_API_KEY",
        max_context_tokens=32000,
        capabilities=capabilities or ModelCapabilities(streaming=True),
        defaults=ModelDefaults(),
        allowed_extra_body_fields=allowed_extra_body_fields,
        disallowed_request_fields=disallowed_request_fields,
        fallback_model_profile_id=fallback_model_profile_id,
    )


class FakeTransport:
    def __init__(
        self,
        responses: list[Any] | None = None,
        stream_events: list[Any] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.stream_events = list(stream_events or [])
        self.requests: list[tuple[ModelProfile, dict[str, Any]]] = []

    async def complete(
        self, profile: ModelProfile, request_body: dict[str, Any]
    ) -> Any:
        self.requests.append((profile, request_body))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def stream(
        self, profile: ModelProfile, request_body: dict[str, Any]
    ) -> AsyncIterator[Any]:
        self.requests.append((profile, request_body))
        for event in self.stream_events:
            yield event

