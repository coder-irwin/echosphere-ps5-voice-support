"""Gemini client for the cascade path.

Only used when `AGENT_MODE=cascade`. In MLLM mode Agora talks to Gemini Live directly and
this module is idle.

Kept deliberately thin: the reasoning model proposes tool calls, and everything about
whether a proposed call is permitted happens in `CallSession.propose_action`. This module
never decides anything.

Two backends, picked automatically:

  Vertex AI     Used when `GCP_PROJECT_ID` is set (it is, on Cloud Run). Authenticates as
                the Cloud Run service account via Application Default Credentials and bills
                through the project's own GCP billing account — no separate API-key wallet.
  AI Studio key Used otherwise (local dev without `gcloud auth application-default login`,
                or any deployment target that isn't GCP). Simple `x-goog-api-key` auth
                against a Gemini Developer API key, which has its own separate prepay
                billing — see R8 in docs/04-risks-and-open-questions.md.

Both speak the same request/response shape (`contents`, `systemInstruction`, `tools`,
`candidates[0].content.parts`), confirmed against the live APIs — only the URL and auth
header differ.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import httpx

AI_STUDIO_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_AI_STUDIO_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.6-flash")
DEFAULT_VERTEX_MODEL = os.getenv("GEMINI_VERTEX_MODEL", "gemini-2.5-flash")

_vertex_credentials: Any = None


def _load_vertex_credentials() -> Any:
    global _vertex_credentials
    if _vertex_credentials is None:
        import google.auth

        _vertex_credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    return _vertex_credentials


async def _vertex_access_token() -> str:
    import google.auth.transport.requests

    creds = _load_vertex_credentials()
    if not creds.valid:
        await asyncio.to_thread(creds.refresh, google.auth.transport.requests.Request())
    return creds.token


class GeminiClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 20.0,
        project: Optional[str] = None,
        location: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.project = project or os.getenv("GCP_PROJECT_ID", "")
        self.location = location or os.getenv("GCP_LOCATION", "us-central1")
        self.model = model or (DEFAULT_VERTEX_MODEL if self.project else DEFAULT_AI_STUDIO_MODEL)
        self.timeout = timeout

    @property
    def use_vertex(self) -> bool:
        return bool(self.project)

    @property
    def configured(self) -> bool:
        return bool(self.project or self.api_key)

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

        try:
            if self.use_vertex:
                token = await _vertex_access_token()
                url = (
                    f"https://{self.location}-aiplatform.googleapis.com/v1/projects/"
                    f"{self.project}/locations/{self.location}/publishers/google/models/"
                    f"{self.model}:generateContent"
                )
                headers = {"Authorization": f"Bearer {token}"}
            else:
                url = f"{AI_STUDIO_BASE}/models/{self.model}:generateContent"
                headers = {"x-goog-api-key": self.api_key}

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            return {
                "text": "",
                "tool_calls": [],
                "error": "gemini_request_failed",
                "detail": f"{type(exc).__name__}: {exc}",
            }
        except Exception as exc:  # google-auth credential errors, misconfigured ADC, etc.
            return {
                "text": "",
                "tool_calls": [],
                "error": "gemini_auth_failed",
                "detail": f"{type(exc).__name__}: {exc}",
            }

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
