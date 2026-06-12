from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping, Sequence


MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: MessageRole
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    streaming: bool = False
    json_mode: bool = False
    tool_calling: bool = False
    reasoning_mode: bool = False
    vision: bool = False
    system_message: bool = True
    structured_output: bool = False


@dataclass(frozen=True, slots=True)
class ModelDefaults:
    temperature: float = 0.2
    top_p: float = 0.95
    max_tokens: int = 2048


@dataclass(frozen=True, slots=True)
class ModelProfile:
    profile_id: str
    display_name: str
    provider_name: str
    base_url: str
    model_id: str
    api_key_env_name: str
    max_context_tokens: int
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    defaults: ModelDefaults = field(default_factory=ModelDefaults)
    allowed_extra_body_fields: frozenset[str] = field(default_factory=frozenset)
    disallowed_request_fields: frozenset[str] = field(default_factory=frozenset)
    output_parser_type: str = "openai_compatible"
    prompt_style: str = "default"
    fallback_model_profile_id: str | None = None
    enabled: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.model_id and self.api_key_env_name)

    def public_dict(self) -> dict[str, Any]:
        return {
            "profile_id": _public_profile_id(self.profile_id),
            "display_name": _public_display_name(self.profile_id),
            "provider_name": "managed",
            "model_id": "managed",
            "max_context_tokens": self.max_context_tokens,
            "capabilities": asdict(self.capabilities),
            "defaults": asdict(self.defaults),
            "prompt_style": self.prompt_style,
            "enabled": self.enabled,
            "configured": self.is_configured,
        }


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return asdict(self)


@dataclass(slots=True)
class NormalizedToolCall:
    id: str | None
    name: str
    arguments: Any
    type: str = "function"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NormalizedLLMResponse:
    text: str = ""
    parsed_json: Any = None
    tool_calls: list[NormalizedToolCall] = field(default_factory=list)
    reasoning_text_internal_only: str | None = None
    content_blocks: list[Any] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    model_id: str | None = None
    profile_id: str | None = None
    finish_reason: str | None = None
    raw_response: Any = None
    error_type: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    latency_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error_type is None

    def public_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "parsed_json": self.parsed_json,
            "tool_calls": [call.as_dict() for call in self.tool_calls],
            "content_blocks": _public_content_blocks(self.content_blocks),
            "usage": self.usage.as_dict(),
            "model_id": None,
            "profile_id": "study_ai",
            "finish_reason": self.finish_reason,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "latency_ms": self.latency_ms,
        }


def _public_content_blocks(blocks: Sequence[Any]) -> list[Any]:
    public: list[Any] = []
    for block in blocks:
        if isinstance(block, str):
            public.append(block)
            continue
        if not isinstance(block, Mapping):
            continue
        block_type = block.get("type")
        if block_type in {"reasoning", "thinking", "tool_call", "tool_use"}:
            continue
        if block_type in {None, "text", "output_text"}:
            text = block.get("text", "")
            if isinstance(text, Mapping):
                text = text.get("value", "")
            public.append({"type": "text", "text": str(text)})
    return public


def coerce_messages(
    messages: Sequence[ChatMessage | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, ChatMessage):
            result.append(message.as_dict())
            continue
        if "role" not in message or "content" not in message:
            raise ValueError("Every message must contain role and content")
        result.append(dict(message))
    return result


def _public_profile_id(profile_id: str) -> str:
    lowered = profile_id.lower()
    if "flash" in lowered:
        return "study_ai_fast"
    if "advanced" in lowered:
        return "study_ai_advanced"
    if "balanced" in lowered:
        return "study_ai_balanced"
    if "long" in lowered:
        return "study_ai_long_context"
    if "fast" in lowered:
        return "study_ai_fast"
    return "study_ai_default"


def _public_display_name(profile_id: str) -> str:
    public_id = _public_profile_id(profile_id)
    return {
        "study_ai_fast": "Fast study assistant",
        "study_ai_advanced": "Advanced study assistant",
        "study_ai_balanced": "Balanced study assistant",
        "study_ai_long_context": "Long-notes study assistant",
        "study_ai_default": "Study assistant",
    }[public_id]
