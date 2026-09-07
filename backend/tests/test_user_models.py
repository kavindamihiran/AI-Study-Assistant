from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from sqlalchemy import select

from app.database import Database, UserModel, UserModelSettingModel
from app.llm.user_models import (
    UserModelConfigError,
    UserModelStore,
    build_user_profile,
    normalize_base_url,
)
from app.security.secret_box import SecretBox, SecretDecryptionError, mask_secret


RUNTIME_DIR = Path(__file__).parent / ".runtime-data-user-models"


class SecretBoxTests(unittest.TestCase):
    def test_round_trips_a_secret(self) -> None:
        box = SecretBox("passphrase-for-tests")
        token = box.encrypt("nvapi-1234567890abcdef")
        self.assertNotIn("nvapi", token)
        self.assertEqual(box.decrypt(token), "nvapi-1234567890abcdef")

    def test_rejects_another_key_and_tampering(self) -> None:
        box = SecretBox("passphrase-for-tests")
        token = box.encrypt("nvapi-1234567890abcdef")
        with self.assertRaises(SecretDecryptionError):
            SecretBox("a-different-passphrase").decrypt(token)
        version, nonce, ciphertext, tag = token.split(".")
        flipped = ciphertext[:-1] + ("A" if ciphertext[-1] != "A" else "B")
        with self.assertRaises(SecretDecryptionError):
            box.decrypt(".".join((version, nonce, flipped, tag)))

    def test_masks_only_the_middle_of_a_key(self) -> None:
        self.assertEqual(mask_secret("nvapi-1234567890"), "nvap******7890")
        self.assertEqual(mask_secret("short"), "*****")


class BaseUrlTests(unittest.TestCase):
    def test_trims_completion_suffixes_and_adds_scheme(self) -> None:
        self.assertEqual(
            normalize_base_url("https://integrate.api.nvidia.com/v1/chat/completions"),
            "https://integrate.api.nvidia.com/v1",
        )
        self.assertEqual(
            normalize_base_url("api.openai.com/v1/"), "https://api.openai.com/v1"
        )

    def test_rejects_an_empty_url(self) -> None:
        with self.assertRaises(UserModelConfigError):
            normalize_base_url("   ")


class UserModelStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        self.database = Database(Database.sqlite_url(RUNTIME_DIR / "settings.db"))
        self.database.initialize()
        with self.database.session() as session:
            session.add(
                UserModel(
                    id="user-1",
                    email="learner@example.com",
                    display_name="Learner",
                    password_salt="salt",
                    password_hash="hash",
                )
            )
        self.store = UserModelStore(self.database, SecretBox("passphrase-for-tests"))

    def tearDown(self) -> None:
        self.database.engine.dispose()
        shutil.rmtree(RUNTIME_DIR, ignore_errors=True)

    def _save(self, **overrides) -> None:
        payload = {
            "user_id": "user-1",
            "display_name": "NVIDIA NIM",
            "provider_name": "nvidia",
            "base_url": "https://integrate.api.nvidia.com/v1/chat/completions",
            "model_id": "meta/llama-3.3-70b-instruct",
            "api_key": "nvapi-1234567890abcdef",
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": 1024,
            "max_context_tokens": 65536,
            "supports_streaming": True,
            "supports_system_message": True,
            "supports_json_mode": False,
            "fallback_to_managed": True,
            "is_enabled": True,
        }
        payload.update(overrides)
        self.store.save(**payload)

    def test_saves_encrypted_and_reads_back(self) -> None:
        self._save()
        config = self.store.get(user_id="user-1")
        assert config is not None
        self.assertEqual(config.base_url, "https://integrate.api.nvidia.com/v1")
        self.assertEqual(config.api_key, "nvapi-1234567890abcdef")
        self.assertEqual(config.api_key_hint, "nvap******cdef")
        with self.database.session() as session:
            row = session.execute(
                select(UserModelSettingModel)
            ).scalar_one()
            self.assertNotIn("nvapi-1234567890abcdef", row.api_key_encrypted)

    def test_public_dict_never_exposes_the_key(self) -> None:
        self._save()
        config = self.store.get(user_id="user-1")
        assert config is not None
        self.assertNotIn("api_key", config.public_dict())
        self.assertEqual(config.public_dict()["api_key_hint"], "nvap******cdef")

    def test_keeps_the_saved_key_when_none_is_supplied(self) -> None:
        self._save()
        self._save(api_key=None, model_id="meta/llama-3.1-8b-instruct")
        config = self.store.get(user_id="user-1")
        assert config is not None
        self.assertEqual(config.model_id, "meta/llama-3.1-8b-instruct")
        self.assertEqual(config.api_key, "nvapi-1234567890abcdef")

    def test_requires_a_key_on_first_save(self) -> None:
        with self.assertRaises(UserModelConfigError):
            self._save(api_key=None)

    def test_disabled_settings_are_not_usable(self) -> None:
        self._save(is_enabled=False)
        self.assertIsNotNone(self.store.get(user_id="user-1"))
        self.assertIsNone(self.store.get_usable(user_id="user-1"))

    def test_records_verification_and_deletes(self) -> None:
        self._save()
        failed = self.store.record_verification(user_id="user-1", error="HTTP 401")
        assert failed is not None
        self.assertEqual(failed.last_error, "HTTP 401")
        self.assertIsNone(failed.last_verified_at)
        passed = self.store.record_verification(user_id="user-1", error=None)
        assert passed is not None
        self.assertIsNone(passed.last_error)
        self.assertIsNotNone(passed.last_verified_at)
        self.assertTrue(self.store.delete(user_id="user-1"))
        self.assertIsNone(self.store.get(user_id="user-1"))

    def test_builds_a_profile_that_carries_the_key_and_fallback(self) -> None:
        self._save()
        config = self.store.get_usable(user_id="user-1")
        assert config is not None
        profile = build_user_profile(config, fallback_profile_id="study_ai_default")
        self.assertEqual(profile.api_key_value, "nvapi-1234567890abcdef")
        self.assertEqual(profile.api_key_env_name, "")
        self.assertTrue(profile.is_configured)
        self.assertEqual(profile.model_id, "meta/llama-3.3-70b-instruct")
        self.assertEqual(profile.defaults.temperature, 0.3)
        self.assertEqual(profile.fallback_model_profile_id, "study_ai_default")
        self.assertIn("response_format", profile.disallowed_request_fields)
        # Provider identity stays hidden from clients, as for server profiles.
        self.assertEqual(profile.public_dict()["model_id"], "managed")
        self.assertEqual(profile.public_dict()["provider_name"], "managed")

    def test_profile_drops_fallback_when_the_student_opts_out(self) -> None:
        self._save(fallback_to_managed=False, supports_json_mode=True)
        config = self.store.get_usable(user_id="user-1")
        assert config is not None
        profile = build_user_profile(config, fallback_profile_id="study_ai_default")
        self.assertIsNone(profile.fallback_model_profile_id)
        self.assertIn("response_format", profile.allowed_extra_body_fields)


if __name__ == "__main__":
    unittest.main()
