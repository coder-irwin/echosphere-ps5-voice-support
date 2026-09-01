"""Assembly. One place where the pieces get wired together.

Kept out of the core modules so that each of them stays independently testable, and so
that the transport adapters have a single obvious way to obtain a live session.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.confidence import ConfidenceGate, EXISTS, MALFORMED, WELL_FORMED, GateThresholds
from app.core.intents import FIELDS
from app.core.policy import PolicyConfig, PolicyEngine
from app.core.session import CallSession
from app.tools.data import DataStore
from app.tools.ecommerce import EcommerceTools
from app.tools.registry import ToolRunner
from app.tools.ticketing import TicketingService

_store: Optional[DataStore] = None


def get_store() -> DataStore:
    """Process-wide store. The demo runs against one shared system of record."""
    global _store
    if _store is None:
        _store = DataStore()
    return _store


def build_gate(store: DataStore) -> ConfidenceGate:
    """Wire semantic plausibility to the system of record.

    This is the half of low-confidence detection that a prompt cannot do: a cleanly
    transcribed order ID that matches nothing is still not something to act on.
    """

    async def order_exists(value: str) -> float:
        return EXISTS if store.order(value) else MALFORMED

    async def phone_exists(value: str) -> float:
        return EXISTS if store.customer_by_phone(value) else WELL_FORMED

    async def email_exists(value: str) -> float:
        return EXISTS if store.customer_by_email(value) else WELL_FORMED

    gate = ConfidenceGate(
        thresholds=GateThresholds(),
        patterns={k: v.pattern for k, v in FIELDS.items() if v.pattern},
    )
    gate.register_validator("order_id", order_exists)
    gate.register_validator("phone", phone_exists)
    gate.register_validator("email", email_exists)
    return gate


def build_session(
    session_id: str,
    store: Optional[DataStore] = None,
    audit_sink: Optional[Path] = None,
    policy_config: Optional[PolicyConfig] = None,
) -> CallSession:
    store = store or get_store()
    ecommerce = EcommerceTools(store)
    session_ref: dict[str, CallSession] = {}

    async def on_escalate(reason: str) -> dict:
        session = session_ref.get("session")
        if session is None:
            return {"success": False, "error": "no session"}
        from app.core.models import EscalationKind

        packet = session.escalation or session.escalate(EscalationKind.CALLER_REQUEST, reason)
        result = await TicketingService().create_from_escalation(packet)
        if result.get("success"):
            from app.core.audit import Kind

            session.audit.record(
                Kind.TICKET_CREATED,
                ticket_id=result.get("ticket_id"),
                backend=result.get("backend"),
            )
        return result

    runner = ToolRunner(ecommerce, on_escalate=on_escalate)
    session = CallSession(
        session_id=session_id,
        tool_executor=runner,
        policy=PolicyEngine(policy_config),
        gate=build_gate(store),
        audit_sink=audit_sink,
    )
    session_ref["session"] = session
    return session
