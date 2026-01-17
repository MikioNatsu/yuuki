from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    async def chat(self, *, system_prompt: str, user_prompt: str) -> str:
        ...
