"""Provider abstraction over an OpenAI-compatible interface.

Implements Requirements 7.1 (single interface), 7.4 (Ollama routing), 7.6 (30s
timeout -> provider unreachable, backend stays up), 7.7 (auth failure, no retry).
"""

from __future__ import annotations

import httpx

from .config import ProviderConfig
from .errors import GenerationFailed, ProviderAuthFailed, ProviderUnreachable
from .memory import ChatMsg

REQUEST_TIMEOUT_SECONDS = 30.0


class LLMClient:
    def __init__(self, config: ProviderConfig, client: httpx.AsyncClient | None = None):
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {config.api_credential}"}
        # OpenRouter recommends app-attribution headers for hosted usage.
        if "openrouter.ai" in self._base_url:
            self._headers["HTTP-Referer"] = "https://character-chat.app"
            self._headers["X-Title"] = "Character Chat AI"
        self._client = client  # injectable for tests

    async def _post(self, path: str, payload: dict) -> dict:
        url = f"{self._base_url}{path}"
        try:
            if self._client is not None:
                resp = await self._client.post(url, json=payload, headers=self._headers)
            else:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                    resp = await client.post(url, json=payload, headers=self._headers)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProviderUnreachable("The model provider is unreachable") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnreachable("The model provider request failed") from exc

        if resp.status_code in (401, 403):
            # Do not retry on auth failure (Requirement 7.7).
            raise ProviderAuthFailed("Provider rejected the credentials")
        if resp.status_code >= 400:
            raise GenerationFailed(f"Provider returned status {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:
            raise GenerationFailed("Provider returned a non-JSON response") from exc

    async def chat_completion(self, messages: list[ChatMsg], **opts) -> str:
        payload = {
            "model": self._config.chat_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        payload.update(opts)
        data = await self._post("/chat/completions", payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GenerationFailed("Provider response missing chat content") from exc

    async def embeddings(self, text: str) -> list[float]:
        payload = {"model": self._config.embed_model, "input": text}
        data = await self._post("/embeddings", payload)
        try:
            return data["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise GenerationFailed("Provider response missing embedding") from exc
