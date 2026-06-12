from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ACTIVE_PROFILE_ID = "nvidia_nemotron_default"
DEFAULT_PROFILES_PATH = Path(__file__).with_name("llm") / "profiles.json"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 90.0
DEFAULT_FRONTEND_URL = "http://localhost:3000"


@dataclass(frozen=True, slots=True)
class Settings:
    active_model_profile_id: str = DEFAULT_ACTIVE_PROFILE_ID
    model_profiles_path: Path = DEFAULT_PROFILES_PATH
    llm_request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    frontend_url: str = DEFAULT_FRONTEND_URL

    @classmethod
    def from_env(cls) -> "Settings":
        profiles_path = os.getenv("MODEL_PROFILES_PATH")
        return cls(
            active_model_profile_id=os.getenv(
                "ACTIVE_MODEL_PROFILE_ID", DEFAULT_ACTIVE_PROFILE_ID
            ),
            model_profiles_path=(
                Path(profiles_path) if profiles_path else DEFAULT_PROFILES_PATH
            ),
            llm_request_timeout_seconds=float(
                os.getenv(
                    "LLM_REQUEST_TIMEOUT_SECONDS",
                    str(DEFAULT_REQUEST_TIMEOUT_SECONDS),
                )
            ),
            frontend_url=os.getenv("FRONTEND_URL", DEFAULT_FRONTEND_URL),
        )
