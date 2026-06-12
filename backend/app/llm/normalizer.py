from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .json_parser import parse_json_tolerantly
from .models import NormalizedLLMResponse, NormalizedToolCall, TokenUsage


_THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)


def _read(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _first(value: Any) -> Any:
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def _extract_text_from_block(block: Any) -> str:
    if isinstance(block, str):
        return block
    block_type = _read(block, "type")
    if block_type not in {None, "text", "output_text"}:
        return ""
    text = _read(block, "text", "")
    if isinstance(text, str):
        return text
    if isinstance(text, Mapping):
        return str(text.get("value", ""))
    return str(text or "")


def _extract_content(content: Any) -> tuple[str, list[Any]]:
    if isinstance(content, str):
        return content, []
    if isinstance(content, (list, tuple)):
        blocks = list(content)
        text = "".join(_extract_text_from_block(block) for block in blocks)
        return text, blocks
    if content is None:
        return "", []
    return str(content), []


def _normalize_arguments(arguments: Any) -> Any:
    if not isinstance(arguments, str):
        return arguments
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return arguments


def _extract_tool_calls(message: Any, root: Any) -> list[NormalizedToolCall]:
    calls = _read(message, "tool_calls") or _read(root, "tool_calls") or []
    content = _read(message, "content") or []
    if isinstance(content, (list, tuple)):
        calls = list(calls) + [
            block
            for block in content
            if _read(block, "type") in {"tool_call", "tool_use"}
        ]
    normalized: list[NormalizedToolCall] = []
    for call in calls:
        function = _read(call, "function", {})
        name = (
            _read(function, "name")
            or _read(call, "name")
            or _read(call, "function_name", "")
        )
        arguments = _read(function, "arguments")
        if arguments is None:
            arguments = _read(
                call, "input", _read(call, "args", _read(call, "arguments"))
            )
        normalized.append(
            NormalizedToolCall(
                id=_read(call, "id"),
                name=str(name),
                arguments=_normalize_arguments(arguments),
                type=str(_read(call, "type", "function")),
            )
        )
    return normalized


def _extract_usage(root: Any) -> TokenUsage:
    metadata = _read(root, "response_metadata", {}) or {}
    usage = (
        _read(root, "usage")
        or _read(root, "usage_metadata")
        or _read(metadata, "token_usage", {})
    )
    input_tokens = _read(usage, "prompt_tokens")
    if input_tokens is None:
        input_tokens = _read(usage, "input_tokens")
    output_tokens = _read(usage, "completion_tokens")
    if output_tokens is None:
        output_tokens = _read(usage, "output_tokens")
    total_tokens = _read(usage, "total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return TokenUsage(input_tokens, output_tokens, total_tokens)


def _extract_reasoning(message: Any, root: Any) -> str | None:
    additional = _read(message, "additional_kwargs", {}) or {}
    for source in (message, additional, root):
        reasoning = (
            _read(source, "reasoning_content")
            or _read(source, "reasoning")
            or _read(source, "thinking")
        )
        if reasoning:
            return str(reasoning)
    content = _read(message, "content") or []
    if isinstance(content, (list, tuple)):
        parts = [
            str(
                _read(
                    block,
                    "text",
                    _read(block, "reasoning", _read(block, "thinking", "")),
                )
            )
            for block in content
            if _read(block, "type") in {"reasoning", "thinking"}
        ]
        joined = "\n\n".join(part for part in parts if part)
        if joined:
            return joined
    return None


def _strip_reasoning(text: str) -> tuple[str, str | None]:
    hidden = [match.group(1).strip() for match in _THINK_BLOCK.finditer(text)]
    clean = _THINK_BLOCK.sub("", text).strip()
    return clean, "\n\n".join(part for part in hidden if part) or None


def normalize_response(
    raw_response: Any,
    *,
    profile_id: str | None = None,
    model_id: str | None = None,
    parse_json: bool = False,
) -> NormalizedLLMResponse:
    choices = _read(raw_response, "choices")
    choice = _first(choices)
    message = _read(choice, "message") if choice is not None else raw_response
    if message is None:
        message = raw_response

    content = _read(message, "content")
    if content in (None, "", []):
        content = _read(message, "content_blocks", _read(raw_response, "content_blocks"))
    text, blocks = _extract_content(content)
    text, inline_reasoning = _strip_reasoning(text)
    reasoning = _extract_reasoning(message, raw_response) or inline_reasoning
    finish_reason = _read(choice, "finish_reason")
    if finish_reason is None:
        finish_reason = _read(
            _read(raw_response, "response_metadata", {}), "finish_reason"
        )

    parsed = None
    if parse_json and text:
        parsed = parse_json_tolerantly(text)

    return NormalizedLLMResponse(
        text=text,
        parsed_json=parsed,
        tool_calls=_extract_tool_calls(message, raw_response),
        reasoning_text_internal_only=reasoning,
        content_blocks=blocks,
        usage=_extract_usage(raw_response),
        model_id=_read(raw_response, "model", model_id),
        profile_id=profile_id,
        finish_reason=finish_reason,
        raw_response=raw_response,
    )
