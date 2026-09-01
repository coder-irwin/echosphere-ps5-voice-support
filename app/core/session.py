"""Call session — the decision API.

This is the brain's only public surface. Both transport adapters (the Gemini Live tool
bridge and the OpenAI-compatible cascade endpoint) drive the same methods, which is what
makes the architecture survivable if function calling turns out to be unavailable in
Agora's MLLM mode.

Everything the model might otherwise be trusted to remember lives here instead:
slot state, language, confirmed identity, what has already been attempted. Server-side
state is the source of truth, so a reconnection does not cost the caller their progress.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from app.core.audit import AuditLog, Kind
from app.core.confidence import ConfidenceGate
from app.core.escalation import EscalationBuilder, brief_for_human
from app.core.guardrails import GuardrailSuite
from app.core.intents import FIELDS, INTENTS, IntentClassifier, is_escalate_by_design
from app.core.language import LanguageState
from app.core.models import (
    ActionOutcome,
    Decision,
    EscalationKind,
    EscalationPacket,
    GuardrailVerdict,
    PolicyVerdict,
    ProposedAction,
    SlotState,
    Turn,
)
from app.core.planner import NextStep, QuestionPlanner, StepKind
from app.core.policy import CaseContext, PolicyEngine
from app.core.slots import SlotManager

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

# Which policy action each tool represents. Tools absent from this map are informational.
TOOL_ACTION = {
    "issue_refund": "refund",
    "cancel_order": "cancel",
    "create_replacement": "replacement",
    "update_address": "update_address",
    "update_subscription": "update_subscription",
    "get_order": "status_reply",
    "get_customer": "status_reply",
    "get_product": "status_reply",
    "check_refund_eligibility": "status_reply",
    "search_knowledge_base": "policy_reply",
    "send_invoice": "send_invoice",
    "escalate": "escalate",
}

# Tool arguments that must be backed by a CONFIRMED slot of the same name.
SLOT_BACKED_ARGS = {"order_id", "phone", "email", "new_address"}

DISCLOSURE = (
    "Hello, you're speaking with an AI assistant from ShopWave support. "
    "I can help with orders, returns and refunds, and I'll bring in a human colleague "
    "whenever you'd like one."
)


class CallSession:
    def __init__(
        self,
        session_id: str,
        tool_executor: ToolExecutor,
        policy: Optional[PolicyEngine] = None,
        gate: Optional[ConfidenceGate] = None,
        classifier: Optional[IntentClassifier] = None,
        audit_sink: Optional[Path] = None,
    ) -> None:
        self.session_id = session_id
        self.slots = SlotManager()
        self.language = LanguageState()
        self.policy = policy or PolicyEngine()
        self.gate = gate or ConfidenceGate(
            patterns={k: v.pattern for k, v in FIELDS.items() if v.pattern}
        )
        self.classifier = classifier or IntentClassifier()
        self.guardrails = GuardrailSuite()
        self.planner = QuestionPlanner(self.slots)
        self.audit = AuditLog(session_id, sink=audit_sink)
        self.escalations = EscalationBuilder(session_id, self.slots)

        self._execute = tool_executor
        self.context = CaseContext()
        self.turns: list[Turn] = []
        self.intent: Optional[str] = None
        self.attempted_actions: list[str] = []
        self.blocked_verdicts: list[PolicyVerdict] = []
        self.escalation: Optional[EscalationPacket] = None
        self.human_present = False
        self.interpreter_mode = False
        self._turn_seq = 0
        self._closed = False

    # ------------------------------------------------------------------- open

    def open(self) -> str:
        self.audit.record(Kind.SESSION_OPEN, language=self.language.current)
        self.audit.record(Kind.DISCLOSURE, text=DISCLOSURE, guardrail="G9_ai_disclosure")
        return DISCLOSURE

    # ------------------------------------------------------------------ turns

    async def observe_turn(
        self,
        text: str,
        speaker: str = "caller",
        transcript_confidence: float = 1.0,
        language_hint: Optional[str] = None,
        interrupted_agent: bool = False,
    ) -> Turn:
        self._turn_seq += 1
        reading = self.language.observe(text, language_hint) if speaker == "caller" else None

        turn = Turn(
            turn_id=self._turn_seq,
            speaker=speaker,
            text=text,
            language=reading.language if reading else None,
            transcript_confidence=transcript_confidence,
            interrupted_agent=interrupted_agent,
        )
        self.turns.append(turn)
        self.audit.record(
            Kind.TURN, turn.turn_id, speaker=speaker, text=text,
            confidence=round(transcript_confidence, 3),
        )

        if interrupted_agent:
            self.audit.record(Kind.INTERRUPTION, turn.turn_id, speaker=speaker)

        if reading is not None:
            if reading.switched_from:
                self.audit.record(
                    Kind.LANGUAGE, turn.turn_id,
                    language=reading.language, switched_from=reading.switched_from,
                )
            if reading.code_switch_in_turn:
                self.audit.record(Kind.CODE_SWITCH, turn.turn_id, language=reading.language)

        if speaker == "caller":
            await self._classify_if_needed(text, turn.turn_id)
            self._apply_utterance_guardrails(text, turn.turn_id)

        return turn

    async def _classify_if_needed(self, text: str, turn_id: int) -> None:
        # Re-classify while the intent is still weak or unset; once a hero flow is under
        # way, a passing mention of another topic should not hijack the call.
        if self.intent is not None and self.intent != "out_of_scope":
            return
        result = await self.classifier.classify(text)
        if result.intent == "out_of_scope" and self.intent is not None:
            return
        self.intent = result.intent
        for field_name in {f for group in INTENTS[result.intent].requires for f in group}:
            spec = FIELDS.get(field_name)
            self.slots.register(field_name, spec.critical if spec else True)
        self.audit.record(
            Kind.INTENT, turn_id,
            intent=result.intent, confidence=result.confidence,
            matched=result.matched, source=result.source,
            tier=INTENTS[result.intent].tier,
        )

    def _apply_utterance_guardrails(self, text: str, turn_id: int) -> None:
        for verdict in self.guardrails.check_utterance(text):
            self.audit.record(
                Kind.GUARDRAIL_BLOCK, turn_id,
                guardrail=verdict.guardrail, reason=verdict.reason,
            )
            if verdict.escalate and self.escalation is None:
                self.escalate(
                    EscalationKind.BY_DESIGN,
                    f"guardrail {verdict.guardrail} fired",
                )

        if self.guardrails.detects_legal_threat(text):
            self.context.flags.append("legal_threat")
            if self.escalation is None:
                self.escalate(EscalationKind.BY_DESIGN, "legal threat detected")

        if self.guardrails.detects_fraud_signal(text):
            if "high_fraud_risk" not in self.context.flags:
                self.context.flags.append("high_fraud_risk")

    # ------------------------------------------------------------------ slots

    async def observe_slot(
        self, field: str, value: str, transcript_confidence: float = 1.0
    ) -> Decision:
        spec = FIELDS.get(field)
        critical = spec.critical if spec else True
        self.slots.register(field, critical)

        verdict = await self.gate.assess(field, value, transcript_confidence, critical)
        self.slots.observe(field, value, transcript_confidence, self._turn_seq, verdict.decision)

        self.audit.record(
            Kind.SLOT_OBSERVED, self._turn_seq,
            field=field, value=value, decision=verdict.decision.value,
            transcript_confidence=verdict.transcript_confidence,
            plausibility=verdict.plausibility, combined=verdict.combined,
            reason=verdict.reason,
        )

        if verdict.decision is Decision.REASK:
            self.audit.record(
                Kind.LOW_CONFIDENCE, self._turn_seq,
                field=field, combined=verdict.combined, reason=verdict.reason,
            )
            if self.planner.register_attempt_limit(field):
                self.audit.record(
                    Kind.REPLAN, self._turn_seq,
                    field=field, reason="attempt limit reached — routing around this field",
                )

        return verdict.decision

    def confirm_slot(self, field: str) -> None:
        self.slots.confirm(field)
        self.audit.record(
            Kind.SLOT_CONFIRMED, self._turn_seq, field=field, value=self.slots.get(field).value
        )
        if field in {"phone", "email"}:
            self.context.identity_confirmed = True

    def correct_slot(self, field: str, value: str) -> None:
        previous = self.slots.get(field)
        self.slots.correct(field, value, self._turn_seq)
        self.audit.record(
            Kind.SLOT_CORRECTED, self._turn_seq,
            field=field, previous=previous.value if previous else None, corrected=value,
        )

    def next_step(self) -> NextStep:
        if self.intent is None:
            return NextStep(StepKind.ASK, None, "intent not yet established")

        step = self.planner.next_step(self.intent)
        if step.kind is StepKind.NO_VIABLE_PATH and self.escalation is None:
            self.escalate(
                EscalationKind.LOW_CONFIDENCE,
                "could not identify the order through any available route",
            )
        return step

    # ---------------------------------------------------------------- actions

    async def propose_action(self, action: ProposedAction) -> ActionOutcome:
        """Adjudicate, then execute only if allowed. This is the whole point of the design."""
        started = time.perf_counter()
        policy_action = TOOL_ACTION.get(action.tool, "status_reply")
        self.attempted_actions.append(action.tool)
        self.audit.record(Kind.TOOL_CALL, self._turn_seq, tool=action.tool, args=action.args)

        # 1. Slot backing — a mutating tool may only read CONFIRMED values.
        unbacked = self._unbacked_args(action)
        if unbacked:
            verdict = PolicyVerdict(
                action=policy_action, allowed=False, rule="unconfirmed_slot",
                reasons=[f"{', '.join(unbacked)} not confirmed by the caller"],
            )
            return self._blocked(action, verdict, started, spoken=(
                "I want to make sure I have that right before I do anything — "
                "let me confirm it with you first."
            ))

        # 2. Policy adjudication.
        verdict = self.policy.adjudicate(policy_action, self.context)
        if verdict.blocked:
            guardrail = GuardrailSuite.guardrail_for_policy_rule(verdict.rule)
            spoken = self._spoken_refusal(verdict)
            outcome = self._blocked(action, verdict, started, spoken=spoken, guardrail=guardrail)
            if policy_action in {"refund", "replacement", "cancel"} and self.escalation is None:
                self.escalate(
                    EscalationKind.POLICY_BLOCK,
                    f"{policy_action} blocked by {verdict.rule}",
                )
                outcome.escalation = self.escalation
            return outcome

        # 3. Execute.
        result = await self._execute(action.tool, action.args)
        latency = int((time.perf_counter() - started) * 1000)
        self.audit.record(
            Kind.TOOL_RESULT, self._turn_seq,
            tool=action.tool, result=result, latency_ms=latency, executed=True,
        )
        self._absorb_result(action.tool, result)

        return ActionOutcome(
            tool=action.tool, executed=True, result=result,
            policy=verdict, latency_ms=latency,
        )

    def _unbacked_args(self, action: ProposedAction) -> list[str]:
        if TOOL_ACTION.get(action.tool) not in {
            "refund", "replacement", "cancel", "update_address", "update_subscription"
        }:
            return []
        unbacked = []
        for key in SLOT_BACKED_ARGS & set(action.args):
            slot = self.slots.get(key)
            if slot is None or not slot.is_confirmed or slot.value != str(action.args[key]):
                unbacked.append(key)
        return unbacked

    def _blocked(
        self,
        action: ProposedAction,
        verdict: PolicyVerdict,
        started: float,
        spoken: str,
        guardrail: Optional[str] = None,
    ) -> ActionOutcome:
        latency = int((time.perf_counter() - started) * 1000)
        self.blocked_verdicts.append(verdict)
        self.audit.record(
            Kind.POLICY_BLOCK, self._turn_seq,
            tool=action.tool, action=verdict.action, rule=verdict.rule,
            reasons=verdict.reasons, guardrail=guardrail, latency_ms=latency,
        )
        guardrails = (
            [GuardrailVerdict(guardrail=guardrail, allowed=False, reason=verdict.reasons[0])]
            if guardrail else []
        )
        return ActionOutcome(
            tool=action.tool, executed=False, policy=verdict,
            guardrails=guardrails, latency_ms=latency, spoken_reason=spoken,
        )

    def _spoken_refusal(self, verdict: PolicyVerdict) -> str:
        reason = verdict.reasons[0] if verdict.reasons else "a policy check did not pass"
        if verdict.rule == "high_value_threshold":
            return (
                "I'm not able to approve a refund of this size myself — that needs a human "
                "colleague. Let me bring one in now. I'm not promising the refund; they'll decide."
            )
        if verdict.rule == "refund_idempotency":
            return "This one has already been refunded, so I won't process it twice."
        if verdict.rule == "return_window":
            return f"I can't process a return here — {reason} A colleague can review it though."
        if verdict.rule == "identity_unverified":
            return "Before I make any change to the order, I need to confirm who I'm speaking with."
        return f"I can't do that: {reason}"

    def _absorb_result(self, tool: str, result: dict[str, Any]) -> None:
        """Fold tool results into the case context so policy sees current state."""
        if result.get("error"):
            return
        if tool == "get_order":
            self.context.order = self.context.order.model_copy(
                update={"found": True, **{
                    k: v for k, v in result.items()
                    if k in type(self.context.order).model_fields
                }}
            )
        elif tool == "get_customer":
            self.context.customer = self.context.customer.model_copy(
                update={"found": True, **{
                    k: v for k, v in result.items()
                    if k in type(self.context.customer).model_fields
                }}
            )
        elif tool == "get_product":
            self.context.product = self.context.product.model_copy(
                update={"found": True, **{
                    k: v for k, v in result.items()
                    if k in type(self.context.product).model_fields
                }}
            )
        elif tool == "issue_refund" and result.get("success"):
            self.context.order = self.context.order.model_copy(
                update={"refund_status": "refunded"}
            )

    # ------------------------------------------------------------- escalation

    def escalate(self, kind: EscalationKind, reason: str) -> EscalationPacket:
        packet = self.escalations.build(
            kind=kind, reason=reason, intent=self.intent,
            language=self.language.current, turns=self.turns,
            attempted=self.attempted_actions, blocked=self.blocked_verdicts,
        )
        self.escalation = packet
        self.audit.record(
            Kind.ESCALATION,
            self._turn_seq,
            kind=kind.value,
            reason=reason,
            confirmed=packet.confirmed,
            unconfirmed=list(packet.unconfirmed),
            by_design=kind is EscalationKind.BY_DESIGN,
        )
        return packet

    def human_joined(self, agent_name: str = "human agent") -> str:
        self.human_present = True
        self.interpreter_mode = True
        self.audit.record(Kind.HUMAN_JOINED, self._turn_seq, agent=agent_name)
        self.audit.record(
            Kind.INTERPRETER_MODE, self._turn_seq,
            caller_language=self.language.current, active=True,
        )
        if self.escalation is None:
            self.escalate(EscalationKind.CALLER_REQUEST, "human agent joined the call")
        return brief_for_human(self.escalation)

    def close(self, outcome: str = "completed") -> None:
        if self._closed:
            return
        self._closed = True
        self.audit.record(
            Kind.SESSION_CLOSE, self._turn_seq,
            outcome=outcome, turns=len(self.turns),
            confirmed=self.slots.confirmed(),
            escalated=self.escalation is not None,
        )

    # ------------------------------------------------------------------ panel

    def snapshot(self) -> dict[str, Any]:
        """Everything the transparency panel renders."""
        step = self.next_step() if self.intent else None
        return {
            "session_id": self.session_id,
            "intent": self.intent,
            "intent_tier": INTENTS[self.intent].tier if self.intent else None,
            "escalate_by_design": is_escalate_by_design(self.intent) if self.intent else False,
            "language": self.language.snapshot(),
            "slots": self.slots.snapshot(),
            "next_step": {"kind": step.kind.value, "field": step.field, "reason": step.reason}
            if step else None,
            "identity_confirmed": self.context.identity_confirmed,
            "flags": self.context.flags,
            "attempted_actions": self.attempted_actions,
            "blocked": [v.model_dump() for v in self.blocked_verdicts],
            "escalation": self.escalation.model_dump() if self.escalation else None,
            "human_present": self.human_present,
            "interpreter_mode": self.interpreter_mode,
            "turns": len(self.turns),
        }
