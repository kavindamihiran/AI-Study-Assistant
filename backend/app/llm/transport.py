from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from typing import Any, Protocol

from .exceptions import ProfileConfigurationError, ProviderRequestError
from .models import ModelProfile


class LLMTransport(Protocol):
    async def complete(
        self, profile: ModelProfile, request_body: dict[str, Any]
    ) -> Any: ...

    async def stream(
        self, profile: ModelProfile, request_body: dict[str, Any]
    ) -> AsyncIterator[Any]: ...


class OpenAICompatibleTransport:
    def __init__(self, *, timeout_seconds: float = 90.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _api_key(self, profile: ModelProfile) -> str:
        api_key = os.getenv(profile.api_key_env_name)
        if not api_key:
            raise ProfileConfigurationError(
                f"Missing API key environment variable: {profile.api_key_env_name}"
            )
        return api_key

    def _request(
        self, profile: ModelProfile, body: dict[str, Any]
    ) -> urllib.request.Request:
        return urllib.request.Request(
            f"{profile.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key(profile)}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if body.get("stream") else "application/json",
            },
            method="POST",
        )

    def _complete_sync(
        self, profile: ModelProfile, body: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            with self._opener.open(
                self._request(profile, body), timeout=self.timeout_seconds
            ) as response:
                response_body = response.read().decode("utf-8")
                try:
                    return json.loads(response_body)
                except json.JSONDecodeError as exc:
                    raise ProviderRequestError(
                        "Provider returned malformed JSON",
                        status_code=502,
                        body=response_body,
                    ) from exc
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise ProviderRequestError(
                f"Provider returned HTTP {exc.code}",
                status_code=exc.code,
                body=response_body,
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderRequestError(str(exc), status_code=503) from exc

    async def complete(
        self, profile: ModelProfile, request_body: dict[str, Any]
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._complete_sync, profile, request_body)

    async def stream(
        self, profile: ModelProfile, request_body: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        finished = object()

        def read_events() -> None:
            try:
                with self._opener.open(
                    self._request(profile, request_body),
                    timeout=self.timeout_seconds,
                ) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8").strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            event = json.loads(payload)
                        except json.JSONDecodeError as exc:
                            raise ProviderRequestError(
                                "Provider returned malformed streaming JSON",
                                status_code=502,
                                body=payload,
                            ) from exc
                        loop.call_soon_threadsafe(queue.put_nowait, event)
            except urllib.error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="replace")
                error = ProviderRequestError(
                    f"Provider returned HTTP {exc.code}",
                    status_code=exc.code,
                    body=response_body,
                )
                loop.call_soon_threadsafe(queue.put_nowait, error)
            except (urllib.error.URLError, TimeoutError) as exc:
                error = ProviderRequestError(str(exc), status_code=503)
                loop.call_soon_threadsafe(queue.put_nowait, error)
            except ProviderRequestError as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, finished)

        reader = asyncio.create_task(asyncio.to_thread(read_events))
        try:
            while True:
                item = await queue.get()
                if item is finished:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            await reader
