from __future__ import annotations

import unittest

from app.llm.exceptions import ProviderRequestError
from app.llm.gateway import LLMGateway
from app.llm.models import ChatMessage, ModelCapabilities
from app.llm.registry import ModelProfileRegistry
from tests.helpers import FakeTransport, make_profile


def completion(text: str, model: str = "models/primary") -> dict:
    return {
        "model": model,
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
    }


class LLMGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_with_minimal_body_after_parameter_rejection(self) -> None:
        profile = make_profile(
            capabilities=ModelCapabilities(json_mode=True),
            allowed_extra_body_fields=frozenset({"response_format"}),
        )
        transport = FakeTransport(
            [
                ProviderRequestError(
                    "unsupported response_format",
                    status_code=400,
                ),
                completion('{"ok": true}'),
            ]
        )
        gateway = LLMGateway(
            registry=ModelProfileRegistry([profile]),
            transport=transport,
            active_profile_id="primary",
        )

        result = await gateway.generate_text(
            [ChatMessage("user", "test")],
            extra_body={"response_format": {"type": "json_object"}},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.retry_count, 1)
        self.assertIn("response_format", transport.requests[0][1])
        self.assertNotIn("response_format", transport.requests[1][1])
        self.assertNotIn("top_p", transport.requests[1][1])
        self.assertNotIn("stream", transport.requests[1][1])

    async def test_uses_configured_fallback_on_provider_unavailability(self) -> None:
        primary = make_profile("primary", fallback_model_profile_id="fallback")
        fallback = make_profile("fallback")
        transport = FakeTransport(
            [
                ProviderRequestError("rate limited", status_code=429),
                completion("fallback answer", model="models/fallback"),
            ]
        )
        gateway = LLMGateway(
            registry=ModelProfileRegistry([primary, fallback]),
            transport=transport,
            active_profile_id="primary",
        )

        result = await gateway.generate_text([ChatMessage("user", "test")])

        self.assertEqual(result.text, "fallback answer")
        self.assertEqual(result.profile_id, "fallback")
        self.assertEqual(result.retry_count, 1)

    async def test_json_generation_repairs_locally_without_second_call(self) -> None:
        profile = make_profile()
        transport = FakeTransport([completion('Here: {"items": [1, 2,],}')])
        gateway = LLMGateway(
            registry=ModelProfileRegistry([profile]),
            transport=transport,
            active_profile_id="primary",
        )

        result = await gateway.generate_json([ChatMessage("user", "Make JSON")])

        self.assertEqual(result.parsed_json, {"items": [1, 2]})
        self.assertEqual(len(transport.requests), 1)

    async def test_json_generation_retries_with_stricter_prompt(self) -> None:
        profile = make_profile()
        transport = FakeTransport(
            [completion("not json"), completion('{"intent": "summary"}')]
        )
        gateway = LLMGateway(
            registry=ModelProfileRegistry([profile]),
            transport=transport,
            active_profile_id="primary",
        )

        result = await gateway.generate_json([ChatMessage("user", "Classify")])

        self.assertEqual(result.parsed_json, {"intent": "summary"})
        self.assertEqual(result.retry_count, 1)
        self.assertEqual(len(transport.requests), 2)

    async def test_stream_falls_back_to_non_streaming_for_profile(self) -> None:
        profile = make_profile(capabilities=ModelCapabilities(streaming=False))
        transport = FakeTransport([completion("whole response")])
        gateway = LLMGateway(
            registry=ModelProfileRegistry([profile]),
            transport=transport,
            active_profile_id="primary",
        )

        chunks = [
            chunk
            async for chunk in gateway.generate_stream(
                [ChatMessage("user", "test")]
            )
        ]

        self.assertEqual(chunks, ["whole response"])
        self.assertFalse(transport.requests[0][1]["stream"])

    async def test_stream_filters_split_reasoning_tags(self) -> None:
        profile = make_profile()
        transport = FakeTransport(
            stream_events=[
                {"choices": [{"delta": {"content": "<thi"}}]},
                {"choices": [{"delta": {"content": "nk>private"}}]},
                {"choices": [{"delta": {"content": " work</thi"}}]},
                {"choices": [{"delta": {"content": "nk>Visible"}}]},
                {"choices": [{"delta": {"content": " answer"}}]},
            ]
        )
        gateway = LLMGateway(
            registry=ModelProfileRegistry([profile]),
            transport=transport,
            active_profile_id="primary",
        )

        chunks = [
            chunk
            async for chunk in gateway.generate_stream(
                [ChatMessage("user", "test")]
            )
        ]

        self.assertEqual("".join(chunks), "Visible answer")
        self.assertNotIn("private", "".join(chunks))

    async def test_adapts_system_message_when_unsupported(self) -> None:
        profile = make_profile(
            capabilities=ModelCapabilities(system_message=False)
        )
        transport = FakeTransport([completion("ok")])
        gateway = LLMGateway(
            registry=ModelProfileRegistry([profile]),
            transport=transport,
            active_profile_id="primary",
        )

        await gateway.generate_text(
            [
                ChatMessage("system", "Be concise."),
                ChatMessage("user", "Explain indexes."),
            ]
        )

        messages = transport.requests[0][1]["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn("Be concise.", messages[0]["content"])
