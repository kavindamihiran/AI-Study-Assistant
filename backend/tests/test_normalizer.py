from __future__ import annotations

import unittest

from app.llm.normalizer import normalize_response


class FakeAIMessage:
    def __init__(self) -> None:
        self.content = [
            {"type": "reasoning", "text": "private chain"},
            {"type": "text", "text": "Visible answer"},
            {
                "type": "tool_use",
                "id": "call-1",
                "name": "lookup",
                "input": {"topic": "indexes"},
            },
        ]
        self.usage_metadata = {"input_tokens": 10, "output_tokens": 4}
        self.response_metadata = {"finish_reason": "stop"}


class ResponseNormalizerTests(unittest.TestCase):
    def test_normalizes_openai_response_and_strips_think_block(self) -> None:
        raw = {
            "model": "vendor/reasoner",
            "choices": [
                {
                    "message": {
                        "content": "<think>hidden work</think>\nFinal answer",
                        "reasoning_content": "separate reasoning",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "search",
                                    "arguments": '{"query":"B trees"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 8,
                "total_tokens": 20,
            },
        }

        result = normalize_response(raw, profile_id="deepseek")

        self.assertEqual(result.text, "Final answer")
        self.assertEqual(result.reasoning_text_internal_only, "separate reasoning")
        self.assertEqual(result.tool_calls[0].arguments, {"query": "B trees"})
        self.assertEqual(result.usage.total_tokens, 20)
        self.assertNotIn("raw_response", result.public_dict())
        self.assertNotIn("reasoning_text_internal_only", result.public_dict())

    def test_normalizes_langchain_style_content_blocks(self) -> None:
        result = normalize_response(FakeAIMessage(), profile_id="kimi")

        self.assertEqual(result.text, "Visible answer")
        self.assertEqual(result.reasoning_text_internal_only, "private chain")
        self.assertEqual(result.tool_calls[0].name, "lookup")
        self.assertEqual(result.usage.input_tokens, 10)
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(
            result.public_dict()["content_blocks"],
            [{"type": "text", "text": "Visible answer"}],
        )

    def test_parses_json_inside_fences_and_commentary(self) -> None:
        raw = {
            "choices": [
                {
                    "message": {
                        "content": 'Result:\n```json\n{"intent":"mcq",}\n```'
                    }
                }
            ]
        }
        result = normalize_response(raw, parse_json=True)
        self.assertEqual(result.parsed_json, {"intent": "mcq"})
