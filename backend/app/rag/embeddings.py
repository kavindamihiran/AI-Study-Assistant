from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from typing import Protocol, Sequence


_TOKEN = re.compile(r"[a-z0-9]{2,}")


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


class EmbeddingProvider(Protocol):
    model_id: str
    dimension: int

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class HashingEmbeddingProvider:
    model_id = "local-hashing-v1"

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        tokens = _TOKEN.findall(text.lower())
        features = tokens + [
            f"{left}_{right}" for left, right in zip(tokens, tokens[1:])
        ]
        vector = [0.0] * self.dimension
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimension
            sign = 1.0 if value & 1 else -1.0
            vector[index] += sign
        return _normalize(vector)

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class NvidiaEmbeddingProvider:
    def __init__(
        self,
        *,
        model_id: str,
        dimension: int,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        api_key_env_name: str = "NVIDIA_API_KEY",
        timeout_seconds: float = 90,
    ) -> None:
        self.model_id = model_id
        self.dimension = dimension
        self.base_url = base_url.rstrip("/")
        self.api_key_env_name = api_key_env_name
        self.timeout_seconds = timeout_seconds

    def _embed_sync(
        self, texts: Sequence[str], *, input_type: str
    ) -> list[list[float]]:
        api_key = os.getenv(self.api_key_env_name)
        if not api_key:
            raise RuntimeError(
                f"Missing API key environment variable: {self.api_key_env_name}"
            )
        body = {
            "model": self.model_id,
            "input": list(texts),
            "input_type": input_type,
            "encoding_format": "float",
        }
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"NVIDIA embeddings returned HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"NVIDIA embeddings request failed: {exc}") from exc

        ordered = sorted(payload.get("data", []), key=lambda item: item["index"])
        vectors = [item["embedding"] for item in ordered]
        if len(vectors) != len(texts):
            raise RuntimeError("NVIDIA embeddings returned an unexpected result count")
        if vectors:
            self.dimension = len(vectors[0])
        return vectors

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 32):
            batch = texts[start : start + 32]
            vectors.extend(
                await asyncio.to_thread(
                    self._embed_sync, batch, input_type="passage"
                )
            )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (
            await asyncio.to_thread(
                self._embed_sync, [text], input_type="query"
            )
        )[0]

