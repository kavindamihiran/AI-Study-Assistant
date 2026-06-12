from __future__ import annotations

from typing import Any


class LLMGatewayError(Exception):
    error_type = "llm_gateway_error"


class ProfileNotFoundError(LLMGatewayError):
    error_type = "profile_not_found"


class ProfileConfigurationError(LLMGatewayError):
    error_type = "profile_configuration_error"


class CapabilityNotSupportedError(LLMGatewayError):
    error_type = "capability_not_supported"


class InvalidRequestError(LLMGatewayError):
    error_type = "invalid_request"


class ProviderRequestError(LLMGatewayError):
    error_type = "provider_request_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body

    @property
    def is_parameter_compatibility_error(self) -> bool:
        if self.status_code not in {400, 404, 415, 422}:
            return False
        text = f"{self} {self.body}".lower()
        markers = (
            "unsupported",
            "unknown parameter",
            "unrecognized",
            "extra field",
            "not permitted",
            "invalid parameter",
            "response_format",
            "tool_choice",
            "reasoning",
        )
        return any(marker in text for marker in markers)

    @property
    def is_fallback_candidate(self) -> bool:
        return self.status_code in {404, 408, 409, 429, 500, 502, 503, 504}


class StructuredOutputError(LLMGatewayError):
    error_type = "structured_output_error"
