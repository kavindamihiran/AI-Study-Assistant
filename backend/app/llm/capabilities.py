from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .exceptions import CapabilityNotSupportedError
from .models import ModelProfile


_FIELD_CAPABILITIES = {
    "response_format": "json_mode",
    "tools": "tool_calling",
    "tool_choice": "tool_calling",
    "parallel_tool_calls": "tool_calling",
    "reasoning": "reasoning_mode",
    "reasoning_effort": "reasoning_mode",
    "thinking": "reasoning_mode",
}


class CapabilityChecker:
    @staticmethod
    def validate_extra_body(
        profile: ModelProfile, extra_body: Mapping[str, Any]
    ) -> None:
        rejected = set(extra_body) - profile.allowed_extra_body_fields
        if rejected:
            fields = ", ".join(sorted(rejected))
            raise CapabilityNotSupportedError(
                f"Profile {profile.profile_id} does not allow fields: {fields}"
            )

        for field in extra_body:
            capability = _FIELD_CAPABILITIES.get(field)
            if capability and not getattr(profile.capabilities, capability):
                raise CapabilityNotSupportedError(
                    f"Profile {profile.profile_id} does not support {capability}"
                )

    @staticmethod
    def adapt_messages(
        profile: ModelProfile, messages: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if profile.capabilities.system_message:
            return [dict(message) for message in messages]

        system_parts = [
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "system"
        ]
        non_system = [
            dict(message) for message in messages if message.get("role") != "system"
        ]
        if not system_parts:
            return non_system

        instruction = "\n\n".join(part for part in system_parts if part)
        if non_system and non_system[0].get("role") == "user":
            existing = str(non_system[0].get("content", ""))
            non_system[0]["content"] = (
                f"Instructions:\n{instruction}\n\nUser request:\n{existing}"
            )
        else:
            non_system.insert(
                0, {"role": "user", "content": f"Instructions:\n{instruction}"}
            )
        return non_system

