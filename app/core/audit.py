"""Append-only audit log.

Retained in spirit from ShopWave's forensic trace, narrowed to a single append-only
stream so that every decision in a call has a sequence number and can be replayed in
order. Subscribers (the transparency panel over WebSocket) receive events as they land.

Nothing here mutates. If a decision was wrong, the record of it having been made stays.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.models import AuditEvent


class AuditLog:
    def __init__(self, session_id: str, sink: Optional[Path] = None) -> None:
        self.session_id = session_id
        self._events: list[AuditEvent] = []
        self._seq = 0
        self._subscribers: list[Callable[[AuditEvent], Any]] = []
        self._sink = sink

    def subscribe(self, callback: Callable[[AuditEvent], Any]) -> None:
        self._subscribers.append(callback)

    def record(
        self, kind: str, turn_id: Optional[int] = None, /, **payload: Any
    ) -> AuditEvent:
        """Append an event.

        `kind` and `turn_id` are positional-only so that a payload key of the same name
        (an escalation has its own `kind`, for instance) cannot collide with them.
        """
        self._seq += 1
        event = AuditEvent(
            seq=self._seq,
            session_id=self.session_id,
            kind=kind,
            turn_id=turn_id,
            payload=payload,
        )
        self._events.append(event)
        self._persist(event)
        self._fanout(event)
        return event

    def _fanout(self, event: AuditEvent) -> None:
        for callback in self._subscribers:
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    # Fire-and-forget: a slow panel must never stall the call.
                    asyncio.ensure_future(result)
            except Exception:  # noqa: BLE001 - a broken subscriber cannot break the call
                continue

    def _persist(self, event: AuditEvent) -> None:
        if self._sink is None:
            return
        self._sink.parent.mkdir(parents=True, exist_ok=True)
        with self._sink.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")

    # ----------------------------------------------------------------- readers

    @property
    def events(self) -> list[AuditEvent]:
        return list(self._events)

    def of_kind(self, kind: str) -> list[AuditEvent]:
        return [e for e in self._events if e.kind == kind]

    def to_json(self) -> str:
        return json.dumps([e.model_dump() for e in self._events], indent=2, ensure_ascii=False)


# Event kinds, named once so the panel and the tests agree with the emitter.
class Kind:
    SESSION_OPEN = "session_open"
    DISCLOSURE = "ai_disclosure"
    TURN = "turn"
    LANGUAGE = "language"
    CODE_SWITCH = "code_switch"
    INTERRUPTION = "interruption"
    SLOT_OBSERVED = "slot_observed"
    SLOT_CONFIRMED = "slot_confirmed"
    SLOT_CORRECTED = "slot_corrected"
    LOW_CONFIDENCE = "low_confidence"
    REPLAN = "question_replan"
    INTENT = "intent_classified"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    POLICY_BLOCK = "policy_block"
    GUARDRAIL_BLOCK = "guardrail_block"
    ESCALATION = "escalation"
    HUMAN_JOINED = "human_joined"
    INTERPRETER_MODE = "interpreter_mode"
    HUMAN_OVERRIDE = "human_override"
    TICKET_CREATED = "ticket_created"
    SESSION_CLOSE = "session_close"
