from __future__ import annotations

import time
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from .capabilities import CapabilityChecker
from .exceptions import (
    InvalidRequestError,
    LLMGatewayError,
    ProfileConfigurationError,
    ProviderRequestError,
    StructuredOutputError,
)
from .json_parser import parse_json_tolerantly
from .models import (
    ChatMessage,
    ModelProfile,
    NormalizedLLMResponse,
    coerce_messages,
)
from .normalizer import normalize_response
from .registry import ModelProfileRegistry
from .transport import LLMTransport


_MINIMAL_REQUEST_FIELDS = {"model", "messages", "temperature", "max_tokens"}


class _StreamingReasoningFilter:
    _open_tag = "<think>"
    _close_tag = "</think>"

    def __init__(self) -> None:
        self._buffer = ""
        self._inside_reasoning = False

    def feed(self, chunk: str) -> list[str]:
        self._buffer += chunk
        visible: list[str] = []
        while self._buffer:
            lowered = self._buffer.lower()
            if self._inside_reasoning:
                closing = lowered.find(self._close_tag)
                if closing < 0:
                    self._buffer = self._buffer[-(len(self._close_tag) - 1) :]
                    break
                self._buffer = self._buffer[closing + len(self._close_tag) :]
                self._inside_reasoning = False
                continue

            opening = lowered.find(self._open_tag)
            if opening >= 0:
                if opening:
                    visible.append(self._buffer[:opening])
                self._buffer = self._buffer[opening + len(self._open_tag) :]
                self._inside_reasoning = True
                continue

            safe_length = max(0, len(self._buffer) - len(self._open_tag) + 1)
            if safe_length:
                visible.append(self._buffer[:safe_length])
                self._buffer = self._buffer[safe_length:]
            break
        return [part for part in visible if part]

    def finish(self) -> list[str]:
        if self._inside_reasoning or not self._buffer:
            self._buffer = ""
            return []
        remaining = self._buffer
        self._buffer = ""
        return [remaining]


class LLMGateway:
    def __init__(
        self,
        *,
        registry: ModelProfileRegistry,
        transport: LLMTransport,
        active_profile_id: str,
    ) -> None:
        self.registry = registry
        self.transport = transport
        self.active_profile_id = active_profile_id

    def resolve_profile(self, profile_id: str | None = None) -> ModelProfile:
        profile = self.registry.get(profile_id or self.active_profile_id)
        if not profile.is_configured:
            raise ProfileConfigurationError(
                f"Model profile {profile.profile_id} is missing its model ID or base URL"
            )
        return profile

    def _request_body(
        self,
        profile: ModelProfile,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        temperature: float | None,
        top_p: float | None,
        max_tokens: int | None,
        stream: bool,
        extra_body: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            normalized_messages = coerce_messages(messages)
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc

        body: dict[str, Any] = {
            "model": profile.model_id,
            "messages": CapabilityChecker.adapt_messages(
                profile, normalized_messages
            ),
            "temperature": (
                profile.defaults.temperature if temperature is None else temperature
            ),
            "top_p": profile.defaults.top_p if top_p is None else top_p,
            "max_tokens": (
                profile.defaults.max_tokens if max_tokens is None else max_tokens
            ),
            "stream": stream,
        }
        if extra_body:
            CapabilityChecker.validate_extra_body(profile, extra_body)
            body.update(extra_body)

        for field in profile.disallowed_request_fields:
            body.pop(field, None)
        return {key: value for key, value in body.items() if value is not None}

    @staticmethod
    def _minimal_body(body: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in body.items()
            if key in _MINIMAL_REQUEST_FIELDS
        }

    async def _complete_with_retry(
        self, profile: ModelProfile, body: dict[str, Any]
    ) -> tuple[Any, int]:
        try:
            return await self.transport.complete(profile, body), 0
        except ProviderRequestError as exc:
            if not exc.is_parameter_compatibility_error:
                raise
        minimal_body = self._minimal_body(body)
        return await self.transport.complete(profile, minimal_body), 1

    async def generate_text(
        self,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        profile_id: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        extra_body: Mapping[str, Any] | None = None,
        use_fallback: bool = True,
    ) -> NormalizedLLMResponse:
        started = time.perf_counter()
        profile: ModelProfile | None = None
        retry_count = 0
        try:
            profile = self.resolve_profile(profile_id)
            body = self._request_body(
                profile,
                messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stream=False,
                extra_body=extra_body,
            )
            try:
                raw_response, retry_count = await self._complete_with_retry(
                    profile, body
                )
            except ProviderRequestError as exc:
                fallback_id = profile.fallback_model_profile_id
                if not (use_fallback and fallback_id and exc.is_fallback_candidate):
                    raise
                profile = self.resolve_profile(fallback_id)
                body = self._request_body(
                    profile,
                    messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    stream=False,
                    extra_body=None,
                )
                raw_response, fallback_retries = await self._complete_with_retry(
                    profile, body
                )
                retry_count += 1 + fallback_retries

            result = normalize_response(
                raw_response,
                profile_id=profile.profile_id,
                model_id=profile.model_id,
            )
            result.retry_count = retry_count
        except LLMGatewayError as exc:
            result = NormalizedLLMResponse(
                profile_id=profile.profile_id if profile else profile_id,
                model_id=profile.model_id if profile else None,
                error_type=exc.error_type,
                error_message=str(exc),
                retry_count=retry_count,
            )
        result.latency_ms = round((time.perf_counter() - started) * 1000, 3)
        return result

    async def generate_json(
        self,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        profile_id: str | None = None,
        max_tokens: int | None = None,
    ) -> NormalizedLLMResponse:
        try:
            profile = self.resolve_profile(profile_id)
        except LLMGatewayError as exc:
            return NormalizedLLMResponse(
                profile_id=profile_id,
                error_type=exc.error_type,
                error_message=str(exc),
            )
        first_messages = list(messages)
        first_messages.append(
            ChatMessage(
                role="user",
                content=(
                    "Return only valid JSON. Do not use markdown fences or add commentary."
                ),
            )
        )
        extra_body = (
            {"response_format": {"type": "json_object"}}
            if profile.capabilities.json_mode
            and "response_format" in profile.allowed_extra_body_fields
            else None
        )
        result = await self.generate_text(
            first_messages,
            profile_id=profile.profile_id,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
        if not result.ok:
            return result
        try:
            result.parsed_json = parse_json_tolerantly(result.text)
            return result
        except StructuredOutputError:
            pass

        strict_messages = list(messages)
        strict_messages.append(
            ChatMessage(
                role="user",
                content=(
                    "Your previous response was not valid JSON. Respond again with one "
                    "JSON object or array only. Use double-quoted keys and strings."
                ),
            )
        )
        retried = await self.generate_text(
            strict_messages,
            profile_id=profile.profile_id,
            temperature=0,
            max_tokens=max_tokens,
        )
        retried.retry_count += result.retry_count + 1
        if not retried.ok:
            return retried
        try:
            retried.parsed_json = parse_json_tolerantly(retried.text)
        except StructuredOutputError as exc:
            retried.error_type = exc.error_type
            retried.error_message = str(exc)
        return retried

    async def generate_stream(
        self,
        messages: Sequence[ChatMessage | Mapping[str, Any]],
        *,
        profile_id: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        profile = self.resolve_profile(profile_id)
        if not profile.capabilities.streaming:
            response = await self.generate_text(
                messages, profile_id=profile.profile_id, max_tokens=max_tokens
            )
            if response.ok and response.text:
                yield response.text
            return

        body = self._request_body(
            profile,
            messages,
            temperature=None,
            top_p=None,
            max_tokens=max_tokens,
            stream=True,
            extra_body=None,
        )
        reasoning_filter = _StreamingReasoningFilter()
        async for event in self.transport.stream(profile, body):
            choices = event.get("choices", []) if isinstance(event, dict) else []
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            content = delta.get("content")
            if isinstance(content, str) and content:
                for visible in reasoning_filter.feed(content):
                    yield visible
        for visible in reasoning_filter.finish():
            yield visible

    async def classify_intent(
        self, prompt: str, *, profile_id: str | None = None
    ) -> NormalizedLLMResponse:
        return await self.generate_json(
            [
                ChatMessage("system", "Classify the user's study request."),
                ChatMessage("user", prompt),
            ],
            profile_id=profile_id,
            max_tokens=256,
        )

    async def rewrite_query(
        self, prompt: str, *, profile_id: str | None = None
    ) -> NormalizedLLMResponse:
        return await self.generate_text(
            [
                ChatMessage(
                    "system",
                    "Rewrite the query for document retrieval. Return only the query.",
                ),
                ChatMessage("user", prompt),
            ],
            profile_id=profile_id,
            temperature=0,
            max_tokens=256,
        )

    async def generate_answer(
        self, prompt: str, *, profile_id: str | None = None
    ) -> NormalizedLLMResponse:
        return await self.generate_text(
            [ChatMessage("user", prompt)], profile_id=profile_id
        )

    async def generate_summary(
        self, prompt: str, *, profile_id: str | None = None
    ) -> NormalizedLLMResponse:
        return await self.generate_text(
            [ChatMessage("user", prompt)], profile_id=profile_id
        )

    async def generate_mcqs(
        self, prompt: str, *, profile_id: str | None = None
    ) -> NormalizedLLMResponse:
        return await self.generate_json(
            [ChatMessage("user", prompt)], profile_id=profile_id
        )

    async def grade_groundedness(
        self, prompt: str, *, profile_id: str | None = None
    ) -> NormalizedLLMResponse:
        return await self.generate_json(
            [ChatMessage("user", prompt)],
            profile_id=profile_id,
            max_tokens=256,
        )
