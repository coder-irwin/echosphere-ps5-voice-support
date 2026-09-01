"""Live session registry and panel fan-out.

One process, one registry. Sessions are held in memory for the lifetime of a call; the
audit log is the durable record, not this.

Every session's audit stream is fanned out to whichever WebSocket clients are watching it,
which is how the transparency panel stays in step with the call without polling.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, Optional

from app.core.models import AuditEvent
from app.core.session import CallSession
from app.factory import build_session, get_store

AUDIT_DIR = Path("var/audit")


class PanelHub:
    """Broadcasts audit events and snapshots to connected panels."""

    def __init__(self) -> None:
        self._clients: dict[str, list[Any]] = {}

    def attach(self, session_id: str, websocket: Any) -> None:
        self._clients.setdefault(session_id, []).append(websocket)

    def detach(self, session_id: str, websocket: Any) -> None:
        clients = self._clients.get(session_id, [])
        if websocket in clients:
            clients.remove(websocket)

    async def publish(self, session_id: str, message: dict[str, Any]) -> None:
        dead = []
        for client in list(self._clients.get(session_id, [])):
            try:
                await client.send_json(message)
            except Exception:  # noqa: BLE001 — a dropped panel must not affect the call
                dead.append(client)
        for client in dead:
            self.detach(session_id, client)

    def watchers(self, session_id: str) -> int:
        return len(self._clients.get(session_id, []))


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, CallSession] = {}
        self._agents: dict[str, str] = {}  # session_id -> agora agent id
        self.hub = PanelHub()

    def create(self, session_id: Optional[str] = None) -> CallSession:
        session_id = session_id or f"call-{uuid.uuid4().hex[:8]}"
        get_store()  # ensure loaded
        session = build_session(session_id, audit_sink=AUDIT_DIR / f"{session_id}.jsonl")

        def on_event(event: AuditEvent) -> Any:
            return self._broadcast(session, event)

        session.audit.subscribe(on_event)
        self._sessions[session_id] = session
        session.open()
        return session

    async def _broadcast(self, session: CallSession, event: AuditEvent) -> None:
        await self.hub.publish(
            session.session_id,
            {
                "type": "event",
                "event": event.model_dump(),
                "snapshot": session.snapshot(),
            },
        )

    def get(self, session_id: str) -> Optional[CallSession]:
        return self._sessions.get(session_id)

    def require(self, session_id: str) -> CallSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def all(self) -> list[CallSession]:
        return list(self._sessions.values())

    def bind_agent(self, session_id: str, agent_id: str) -> None:
        self._agents[session_id] = agent_id

    def agent_for(self, session_id: str) -> Optional[str]:
        return self._agents.get(session_id)

    def close(self, session_id: str, outcome: str = "completed") -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.close(outcome)

    def drop(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._agents.pop(session_id, None)


registry = SessionRegistry()
