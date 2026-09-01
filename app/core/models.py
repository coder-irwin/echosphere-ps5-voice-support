"""Core domain models.

Transport-agnostic: nothing in this module knows about Agora, Gemini, HTTP or audio.
That separation is what lets the same brain sit behind either the MLLM tool bridge or
the OpenAI-compatible cascade adapter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- slots


class SlotState(str, Enum):
    """The confirmation ladder. A tool call may only read CONFIRMED slots."""

    UNHEARD = "unheard"
    HEARD = "heard"
    READ_BACK = "read_back"
    CONFIRMED = "confirmed"


class Decision(str, Enum):
    ACCEPT = "accept"
    READ_BACK = "read_back"
    REASK = "reask"


class SlotObservation(BaseModel):
    value: str
    transcript_confidence: float
    turn_id: int
    at: str = Field(default_factory=_now)


class Slot(BaseModel):
    field: str
    critical: bool = True
    state: SlotState = SlotState.UNHEARD
    value: Optional[str] = None
    confidence: float = 0.0
    attempts: int = 0
    exhausted: bool = False
    observations: list[SlotObservation] = Field(default_factory=list)

    @property
    def is_confirmed(self) -> bool:
        return self.state is SlotState.CONFIRMED


class ConfidenceVerdict(BaseModel):
    field: str
    value: Optional[str]
    transcript_confidence: float
    plausibility: float
    combined: float
    decision: Decision
    reason: str


# ---------------------------------------------------------------------- guardrails


class GuardrailVerdict(BaseModel):
    guardrail: str
    allowed: bool
    reason: str
    escalate: bool = False


class PolicyVerdict(BaseModel):
    action: str
    allowed: bool
    rule: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    risk: str = "low"

    @property
    def blocked(self) -> bool:
        return not self.allowed


# --------------------------------------------------------------------- escalation


class EscalationKind(str, Enum):
    """The distinction that reframes escalation rate as a design position.

    BY_DESIGN  — this class of case is defined as requiring human judgement.
    LOW_CONFIDENCE — the agent tried and was not sure enough.
    """

    BY_DESIGN = "by_design"
    LOW_CONFIDENCE = "low_confidence"
    POLICY_BLOCK = "policy_block"
    CALLER_REQUEST = "caller_request"


class EscalationPacket(BaseModel):
    session_id: str
    kind: EscalationKind
    reason: str
    intent: Optional[str] = None
    confirmed: dict[str, str] = Field(default_factory=dict)
    unconfirmed: dict[str, Optional[str]] = Field(default_factory=dict)
    attempted_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[PolicyVerdict] = Field(default_factory=list)
    caller_language: str = "en-IN"
    transcript_summary: str = ""
    created_at: str = Field(default_factory=_now)


# -------------------------------------------------------------------------- audit


class AuditEvent(BaseModel):
    seq: int
    session_id: str
    kind: str
    turn_id: Optional[int] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    at: str = Field(default_factory=_now)


# --------------------------------------------------------------------------- turn


class Turn(BaseModel):
    turn_id: int
    speaker: str  # "caller" | "agent" | "human_agent"
    text: str
    language: Optional[str] = None
    transcript_confidence: float = 1.0
    interrupted_agent: bool = False
    at: str = Field(default_factory=_now)


class LanguageReading(BaseModel):
    language: str
    switched_from: Optional[str] = None
    code_switch_in_turn: bool = False


# ------------------------------------------------------------------------ actions


class ProposedAction(BaseModel):
    """What the model wants to do, before anything has adjudicated it."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    intent: Optional[str] = None


class ActionOutcome(BaseModel):
    tool: str
    executed: bool
    result: Optional[dict[str, Any]] = None
    policy: Optional[PolicyVerdict] = None
    guardrails: list[GuardrailVerdict] = Field(default_factory=list)
    escalation: Optional[EscalationPacket] = None
    latency_ms: int = 0
    spoken_reason: Optional[str] = None
