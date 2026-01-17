from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.domain.ports.llm import LLMClient


class OllamaLLMClient(LLMClient):
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        model: str,
        temperature: float,
        timeout_seconds: float,
    ) -> None:
        self._client = http_client
        self._model = model
        self._temperature = float(temperature)
        self._timeout = float(timeout_seconds)

    async def chat(self, *, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self._temperature,
                "num_predict": 220,
            },
        }

        resp = await asyncio.wait_for(self._client.post("/api/chat", json=payload), timeout=self._timeout)
        resp.raise_for_status()

        data = resp.json()
        message = data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, dict):
            raise ValueError("invalid ollama response")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty ollama content")
        return content
