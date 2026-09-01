"""Escalation packet builder.

PS5 requirement 8 — "human escalation with context preservation". The packet is what
makes the warm handoff work: the human agent inherits everything already confirmed, so
the caller never repeats themselves across the boundary.

Two properties matter more than completeness:

  1. **Confirmed and unconfirmed are kept apart.** Handing a human a flat summary invites
     them to trust a value the caller never actually confirmed. The console renders these
     differently for the same reason.
  2. **The kind of escalation is recorded.** BY_DESIGN and LOW_CONFIDENCE look identical
     in a summary and mean opposite things about the system.
"""

from __future__ import annotations

from typing import Optional

from app.core.models import (
    EscalationKind,
    EscalationPacket,
    PolicyVerdict,
    Turn,
)
from app.core.slots import SlotManager


class EscalationBuilder:
    def __init__(self, session_id: str, slots: SlotManager) -> None:
        self.session_id = session_id
        self.slots = slots

    def build(
        self,
        kind: EscalationKind,
        reason: str,
        intent: Optional[str],
        language: str,
        turns: list[Turn],
        attempted: Optional[list[str]] = None,
        blocked: Optional[list[PolicyVerdict]] = None,
    ) -> EscalationPacket:
        return EscalationPacket(
            session_id=self.session_id,
            kind=kind,
            reason=reason,
            intent=intent,
            confirmed=self.slots.confirmed(),
            unconfirmed=self.slots.unconfirmed(),
            attempted_actions=attempted or [],
            blocked_actions=blocked or [],
            caller_language=language,
            transcript_summary=summarise(turns),
        )


def summarise(turns: list[Turn], max_turns: int = 12) -> str:
    """A concise, faithful transcript summary.

    Deliberately extractive rather than model-generated: an escalation summary is read by
    a human who is about to make a decision, and a hallucinated detail there is worse
    than a verbose one. The model paraphrasing the caller is exactly the wrong place to
    save tokens.
    """
    if not turns:
        return "(no conversation yet)"

    recent = turns[-max_turns:]
    lines = []
    for t in recent:
        speaker = {"caller": "Caller", "agent": "AI", "human_agent": "Human"}.get(
            t.speaker, t.speaker
        )
        text = t.text.strip().replace("\n", " ")
        if len(text) > 160:
            text = text[:157] + "..."
        lines.append(f"{speaker}: {text}")

    prefix = "" if len(turns) <= max_turns else f"(earlier {len(turns) - max_turns} turns omitted)\n"
    return prefix + "\n".join(lines)


def brief_for_human(packet: EscalationPacket) -> str:
    """What the agent says aloud to the human when they join the channel.

    Spoken in the human agent's language, not the caller's — the point of interpreter mode
    is that these are two different languages.
    """
    confirmed = ", ".join(f"{k} {v}" for k, v in packet.confirmed.items()) or "nothing confirmed yet"
    blocked = "; ".join(
        f"{v.action} blocked by {v.rule}" for v in packet.blocked_actions if v.rule
    )

    parts = [
        f"Handing over. The caller is speaking {packet.caller_language}.",
        f"Issue: {packet.intent or 'not yet classified'}.",
        f"Confirmed: {confirmed}.",
    ]
    if packet.unconfirmed:
        parts.append(f"Not confirmed: {', '.join(packet.unconfirmed)}.")
    if blocked:
        parts.append(f"I could not proceed because {blocked}.")
    parts.append(f"Reason for handover: {packet.reason}")
    parts.append("I'll stay on the line and interpret.")
    return " ".join(parts)
