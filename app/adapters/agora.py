"""Agora adapter — RTC tokens and the Conversational AI Engine REST API.

Two agent configurations are produced here, from one set of inputs:

  MLLM     `mllm.vendor: "gemini"` — native speech-to-speech. Better code-switching,
           interruption and prosody. Function calling through Agora's MLLM integration is
           undocumented (risk R1), so this path is verified by a spike before it is relied on.
  CASCADE  `asr -> llm.vendor: "custom" -> tts` — Agora calls our OpenAI-compatible
           endpoint, so ShopWave Core *is* the LLM. Function calling is documented here.

`remote_rtc_uids: ["*"]` on both, so the agent keeps hearing everyone once the human
support agent joins — that is what makes interpreter mode possible at all.

Endpoint paths and the exact MLLM tool-declaration shape must be checked against the live
API before the sprint; see docs/04-risks-and-open-questions.md.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Literal, Optional

import httpx

from app.adapters.prompts import base_instruction
from app.tools.registry import gemini_tools, openai_tools

API_BASE = "https://api.agora.io/api/conversational-ai-agent/v2/projects"
PUBLISHER_ROLE = 1

Mode = Literal["mllm", "cascade"]


@dataclass
class AgoraConfig:
    app_id: str
    app_certificate: str
    customer_key: str
    customer_secret: str
    mode: Mode = "mllm"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-live-preview"
    gemini_voice: str = "Charon"
    llm_base_url: str = ""  # our own endpoint, for the cascade path
    asr_vendor: str = "microsoft"
    asr_language: str = "en-IN"
    tts_vendor: str = "microsoft"
    idle_timeout: int = 60

    @classmethod
    def from_env(cls) -> "AgoraConfig":
        return cls(
            app_id=os.getenv("AGORA_APP_ID", ""),
            app_certificate=os.getenv("AGORA_APP_CERTIFICATE", ""),
            customer_key=os.getenv("AGORA_CUSTOMER_KEY", ""),
            customer_secret=os.getenv("AGORA_CUSTOMER_SECRET", ""),
            mode=os.getenv("AGENT_MODE", "mllm"),  # type: ignore[arg-type]
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-live-preview"),
            gemini_voice=os.getenv("GEMINI_VOICE", "Charon"),
            llm_base_url=os.getenv("PUBLIC_BASE_URL", ""),
            idle_timeout=int(os.getenv("AGORA_IDLE_TIMEOUT", "60")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.customer_key and self.customer_secret)


def build_rtc_token(cfg: AgoraConfig, channel: str, uid: int, ttl_seconds: int = 3600) -> str:
    """RTC token for a browser client.

    Uses Agora's own token builder rather than a hand-rolled AccessToken2 implementation —
    a subtly wrong signature fails in ways that are painful to diagnose on demo day.
    """
    if not cfg.app_certificate:
        return ""  # certificate-less projects accept the App ID alone
    from agora_token_builder import RtcTokenBuilder

    expires_at = int(time.time()) + ttl_seconds
    return RtcTokenBuilder.buildTokenWithUid(
        cfg.app_id, cfg.app_certificate, channel, uid, PUBLISHER_ROLE, expires_at
    )


# --------------------------------------------------------------- agent configs


def _mllm_properties(cfg: AgoraConfig, instruction: str) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "vendor": "gemini",
        "params": {
            "api_key": cfg.gemini_api_key,
            "model": cfg.gemini_model,
        },
        "instructions": instruction,
        "voice": cfg.gemini_voice,
        "input_modalities": ["audio"],
        "output_modalities": ["audio"],
        # Load-bearing: these are how transcripts reach the panel and the audit log at all
        # in speech-to-speech mode, where there is no separate ASR to read from.
        "transcribe_user": True,
        "transcribe_agent": True,
        "turn_detection": {"type": "agora_vad", "interrupt_mode": "interrupt"},
    }
    # Unverified against the live API (R1). Sent optimistically: if Agora ignores the key
    # the agent still runs and we fall back to cascade, rather than failing to start.
    properties["tools"] = gemini_tools()
    return properties


def _cascade_llm(cfg: AgoraConfig, instruction: str) -> dict[str, Any]:
    return {
        "vendor": "custom",
        "url": f"{cfg.llm_base_url.rstrip('/')}/v1/chat/completions",
        "system_messages": [{"role": "system", "content": instruction}],
        "tools": openai_tools(),
        "max_history": 32,
        "greeting_message": "",
    }


def build_agent_payload(
    cfg: AgoraConfig,
    channel: str,
    agent_uid: str = "1000",
    instruction: Optional[str] = None,
    name: Optional[str] = None,
) -> dict[str, Any]:
    instruction = instruction or base_instruction()
    payload: dict[str, Any] = {
        "name": name or f"shopwave-{channel}",
        "properties": {
            "channel": channel,
            "token": build_rtc_token(cfg, channel, int(agent_uid)),
            "agent_rtc_uid": agent_uid,
            # Subscribe to everyone: the human agent joins mid-call and the agent must
            # hear them to interpret.
            "remote_rtc_uids": ["*"],
            "enable_string_uid": False,
            "idle_timeout": cfg.idle_timeout,
            "advanced_features": {"enable_aivad": True},
        },
    }

    if cfg.mode == "mllm":
        payload["properties"]["mllm"] = _mllm_properties(cfg, instruction)
    else:
        payload["properties"]["asr"] = {
            "vendor": cfg.asr_vendor,
            "language": cfg.asr_language,
        }
        payload["properties"]["llm"] = _cascade_llm(cfg, instruction)
        payload["properties"]["tts"] = {"vendor": cfg.tts_vendor}
        payload["properties"]["turn_detection"] = {
            "type": "agora_vad",
            "interrupt_mode": "interrupt",
        }

    return payload


# ------------------------------------------------------------------ REST client


class AgoraConvoAI:
    def __init__(self, cfg: Optional[AgoraConfig] = None, timeout: float = 15.0) -> None:
        self.cfg = cfg or AgoraConfig.from_env()
        self.timeout = timeout

    @property
    def _auth(self) -> tuple[str, str]:
        return (self.cfg.customer_key, self.cfg.customer_secret)

    def _url(self, suffix: str = "") -> str:
        return f"{API_BASE}/{self.cfg.app_id}{suffix}"

    async def start_agent(self, channel: str, **kwargs: Any) -> dict[str, Any]:
        payload = build_agent_payload(self.cfg, channel, **kwargs)
        return await self._post(self._url("/join"), payload)

    async def stop_agent(self, agent_id: str) -> dict[str, Any]:
        return await self._post(self._url(f"/agents/{agent_id}/leave"), {})

    async def update_agent(self, agent_id: str, instruction: str) -> dict[str, Any]:
        """Switch the running agent's instruction mid-call.

        This is how interpreter mode is entered when the human joins, without dropping the
        channel or the caller's audio.
        """
        body: dict[str, Any] = (
            {"mllm": {"instructions": instruction}}
            if self.cfg.mode == "mllm"
            else {"llm": {"system_messages": [{"role": "system", "content": instruction}]}}
        )
        return await self._post(self._url(f"/agents/{agent_id}/update"), body)

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.cfg.configured:
            return {
                "ok": False,
                "error": "agora_not_configured",
                "detail": "Set AGORA_APP_ID, AGORA_CUSTOMER_KEY and AGORA_CUSTOMER_SECRET.",
                "would_have_sent": payload,
            }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, auth=self._auth)
        if response.status_code >= 400:
            return {
                "ok": False,
                "error": f"agora_http_{response.status_code}",
                "detail": response.text[:400],
            }
        return {"ok": True, **response.json()}
