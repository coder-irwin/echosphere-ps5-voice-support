"""Gemini client for the cascade path.

Only used when `AGENT_MODE=cascade`. In MLLM mode Agora talks to Gemini Live directly and
this module is idle.

Kept deliberately thin: the reasoning model proposes tool calls, and everything about
whether a proposed call is permitted happens in `CallSession.propose_action`. This module
never decides anything.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3-flash")


class GeminiClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def generate(
        self,
        contents: list[dict[str, Any]],
        system_instruction: str,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Returns {"text": str, "tool_calls": [{"name":..., "args":...}]}."""
        if not self.configured:
            return {
                "text": "",
                "tool_calls": [],
                "error": "gemini_not_configured",
            }

        payload: dict[str, Any] = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"temperature": 0.3},
        }
        if tools:
            payload["tools"] = tools

        url = f"{GEMINI_BASE}/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url, json=payload, headers={"x-goog-api-key": self.api_key}
            )

        if response.status_code >= 400:
            return {
                "text": "",
                "tool_calls": [],
                "error": f"gemini_http_{response.status_code}",
                "detail": response.text[:300],
            }

        return _parse(response.json())


def _parse(body: dict[str, Any]) -> dict[str, Any]:
    candidates = body.get("candidates") or []
    if not candidates:
        return {"text": "", "tool_calls": []}

    parts = candidates[0].get("content", {}).get("parts", []) or []
    text = "".join(p["text"] for p in parts if "text" in p)
    tool_calls = [
        {"name": p["functionCall"].get("name"), "args": p["functionCall"].get("args", {})}
        for p in parts
        if "functionCall" in p
    ]
    return {"text": text.strip(), "tool_calls": tool_calls}


def messages_to_contents(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Convert OpenAI-format messages (what Agora's custom LLM path sends) to Gemini's."""
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []

    for message in messages:
        role = message.get("role")
        content = message.get("content") or ""
        if role == "system":
            system_parts.append(content)
        elif role in {"user", "assistant"}:
            contents.append(
                {"role": "user" if role == "user" else "model", "parts": [{"text": content}]}
            )
        elif role == "tool":
            contents.append(
                {"role": "user", "parts": [{"text": f"[tool result] {content}"}]}
            )

    return contents, "\n\n".join(system_parts)
