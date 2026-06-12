from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ACTIVE_PROFILE_ID = "study_ai_default"
DEFAULT_PROFILES_PATH = Path(__file__).with_name("llm") / "profiles.json"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 90.0
DEFAULT_FRONTEND_URL = "http://localhost:3000"
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_MAX_UPLOAD_MB = 25
DEFAULT_VECTOR_STORE_PROVIDER = "local"
DEFAULT_EMBEDDING_PROVIDER = "local"
DEFAULT_EMBEDDING_DIMENSION = 384
DEFAULT_HOSTED_EMBEDDING_MODEL_ID = ""


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def load_local_env_files() -> None:
    """Load local env files without overriding real process environment."""
    backend_dir = Path(__file__).resolve().parents[1]
    project_dir = backend_dir.parent
    env_values: dict[str, str] = {}
    for env_path in (
        project_dir / ".env",
        project_dir / ".env.local",
        backend_dir / ".env",
        backend_dir / ".env.local",
    ):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(line)
            if parsed is not None:
                key, value = parsed
                env_values[key] = value
    for key, value in env_values.items():
        os.environ.setdefault(key, value)


@dataclass(frozen=True, slots=True)
class Settings:
    active_model_profile_id: str = DEFAULT_ACTIVE_PROFILE_ID
    model_profiles_path: Path = DEFAULT_PROFILES_PATH
    llm_request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    frontend_url: str = DEFAULT_FRONTEND_URL
    data_dir: Path = DEFAULT_DATA_DIR
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB
    database_url: str | None = None
    vector_store_provider: str = DEFAULT_VECTOR_STORE_PROVIDER
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION
    hosted_embedding_model_id: str = DEFAULT_HOSTED_EMBEDDING_MODEL_ID
    pinecone_api_key: str | None = None
    pinecone_index_host: str | None = None
    pinecone_namespace: str = "study-assistant"

    @classmethod
    def from_env(cls) -> "Settings":
        load_local_env_files()
        profiles_path = os.getenv("MODEL_PROFILES_PATH")
        data_dir = os.getenv("DATA_DIR")
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
            data_dir=Path(data_dir) if data_dir else DEFAULT_DATA_DIR,
            max_upload_mb=int(
                os.getenv("MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
            ),
            database_url=os.getenv("DATABASE_URL"),
            vector_store_provider=os.getenv(
                "VECTOR_STORE_PROVIDER", DEFAULT_VECTOR_STORE_PROVIDER
            ),
            embedding_provider=os.getenv(
                "EMBEDDING_PROVIDER", DEFAULT_EMBEDDING_PROVIDER
            ),
            embedding_dimension=int(
                os.getenv(
                    "EMBEDDING_DIMENSION",
                    str(DEFAULT_EMBEDDING_DIMENSION),
                )
            ),
            hosted_embedding_model_id=os.getenv(
                "AI_EMBEDDING_MODEL_ID",
                DEFAULT_HOSTED_EMBEDDING_MODEL_ID,
            ),
            pinecone_api_key=os.getenv("PINECONE_API_KEY"),
            pinecone_index_host=os.getenv("PINECONE_INDEX_HOST"),
            pinecone_namespace=os.getenv(
                "PINECONE_NAMESPACE", "study-assistant"
            ),
        )
