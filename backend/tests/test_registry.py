from __future__ import annotations

import unittest

from app.llm.exceptions import ProfileConfigurationError
from app.llm.registry import ModelProfileRegistry


class ModelProfileRegistryTests(unittest.TestCase):
    def test_loads_environment_backed_profile(self) -> None:
        payload = [
            {
                "profile_id": "nim",
                "display_name": "NIM",
                "provider_name": "nvidia_nim",
                "base_url": "${NVIDIA_BASE_URL:-https://default.test/v1}",
                "model_id": "${NVIDIA_MODEL_ID}",
                "api_key_env_name": "NVIDIA_API_KEY",
                "max_context_tokens": 32000,
            }
        ]
        registry = ModelProfileRegistry.from_data(
            payload, env={"NVIDIA_MODEL_ID": "vendor/model"}
        )

        profile = registry.get("nim")
        self.assertEqual(profile.base_url, "https://default.test/v1")
        self.assertEqual(profile.model_id, "vendor/model")

    def test_rejects_missing_fallback(self) -> None:
        payload = [
            {
                "profile_id": "nim",
                "display_name": "NIM",
                "provider_name": "nvidia_nim",
                "base_url": "https://example.test/v1",
                "model_id": "vendor/model",
                "api_key_env_name": "NVIDIA_API_KEY",
                "max_context_tokens": 32000,
                "fallback_model_profile_id": "missing",
            }
        ]
        with self.assertRaises(ProfileConfigurationError):
            ModelProfileRegistry.from_data(payload)
