"""Ticketing integration — PS5 requirement 9.

Two backends behind one interface. The Zendesk client is the real integration for the
submission; the local one keeps the whole system runnable (and the tests deterministic)
with no credentials, which matters because the demo must not depend on a third party
being reachable from a conference hall.

Escalated cases carry the escalation packet into the ticket body, so the context
preservation survives past the end of the call as well as across the handoff.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

import httpx

from app.core.models import EscalationPacket


class TicketBackend(Protocol):
    name: str

    async def create(self, subject: str, body: str, tags: list[str]) -> dict[str, Any]: ...


class LocalTicketBackend:
    """Append-only JSONL. Always available, used when no credentials are configured."""

    name = "local"

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or Path("var/tickets.jsonl")
        self._seq = 0

    async def create(self, subject: str, body: str, tags: list[str]) -> dict[str, Any]:
        self._seq += 1
        ticket = {
            "id": f"LOCAL-{self._seq:04d}",
            "subject": subject,
            "body": body,
            "tags": tags,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ticket, ensure_ascii=False) + "\n")
        return {"success": True, "backend": self.name, "ticket_id": ticket["id"]}


class ZendeskBackend:
    """Zendesk Support API. Requires ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN."""

    name = "zendesk"

    def __init__(self, subdomain: str, email: str, token: str, timeout: float = 8.0) -> None:
        self.base = f"https://{subdomain}.zendesk.com/api/v2"
        self.auth = (f"{email}/token", token)
        self.timeout = timeout

    async def create(self, subject: str, body: str, tags: list[str]) -> dict[str, Any]:
        payload = {"ticket": {"subject": subject, "comment": {"body": body}, "tags": tags}}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base}/tickets.json", json=payload, auth=self.auth)
        if response.status_code >= 400:
            return {
                "success": False,
                "backend": self.name,
                "error": f"{response.status_code}: {response.text[:200]}",
            }
        ticket_id = response.json().get("ticket", {}).get("id")
        return {"success": True, "backend": self.name, "ticket_id": str(ticket_id)}


class TicketingService:
    def __init__(self, backend: Optional[TicketBackend] = None) -> None:
        self.backend = backend or _backend_from_env()

    async def create_from_escalation(self, packet: EscalationPacket) -> dict[str, Any]:
        subject = f"[{packet.kind.value}] {packet.intent or 'unclassified'} — {packet.session_id}"
        body = _render(packet)
        tags = ["voice", "ai-assistant", packet.kind.value]
        if packet.intent:
            tags.append(packet.intent)
        return await self.backend.create(subject, body, tags)

    async def create(self, subject: str, body: str, tags: list[str]) -> dict[str, Any]:
        return await self.backend.create(subject, body, tags)


def _render(packet: EscalationPacket) -> str:
    confirmed = "\n".join(f"  - {k}: {v}" for k, v in packet.confirmed.items()) or "  (none)"
    unconfirmed = "\n".join(f"  - {k}: {v or '—'}" for k, v in packet.unconfirmed.items()) or "  (none)"
    blocked = "\n".join(
        f"  - {v.action} blocked by {v.rule}: {'; '.join(v.reasons)}"
        for v in packet.blocked_actions
    ) or "  (none)"

    return "\n".join([
        f"Escalation kind: {packet.kind.value}",
        f"Reason: {packet.reason}",
        f"Caller language: {packet.caller_language}",
        "",
        "CONFIRMED BY CALLER",
        confirmed,
        "",
        "NOT CONFIRMED — treat as unverified",
        unconfirmed,
        "",
        "BLOCKED ACTIONS",
        blocked,
        "",
        "TRANSCRIPT",
        packet.transcript_summary,
    ])


def _backend_from_env() -> TicketBackend:
    subdomain = os.getenv("ZENDESK_SUBDOMAIN")
    email = os.getenv("ZENDESK_EMAIL")
    token = os.getenv("ZENDESK_API_TOKEN")
    if subdomain and email and token:
        return ZendeskBackend(subdomain, email, token)
    return LocalTicketBackend()
