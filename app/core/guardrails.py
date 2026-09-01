"""Guardrail catalogue — PS5 requirement 10, "clear boundaries".

Nine guardrails. Four are enforced by the policy engine against system state; five are
enforced here against what is being said. Each returns a named verdict so the panel can
show which one fired, and each refusal is spoken rather than silent.

The distinction that matters for the jury: these are *checks in code*, not sentences in a
system prompt. A prompt can be talked out of its instructions. A policy engine cannot.

Mapping to PS5's explicit safety restrictions:

    "no medical diagnosis"                        -> G7 medical_claim
    "no legal/financial/emergency advice"         -> G5 authoritative_advice
    "no uncertain output as confirmed fact"       -> G6 unverifiable_promise
    "not replace emergency responders"            -> out of domain; routed by G8/Tier 3
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.core.models import GuardrailVerdict

# G5 — requests for advice we are not allowed to give authoritatively
ADVICE_PATTERNS = re.compile(
    r"\b(should i sue|legal advice|is this legal|can i sue|file a case|"
    r"tax advice|invest|should i buy shares|is it a scam legally|"
    r"what are my legal rights|consumer court me)\b",
    re.I,
)

# G6 — asks that would require us to promise something we cannot verify
PROMISE_PATTERNS = re.compile(
    r"\b(guarantee|promise me|will it definitely|exact time it will arrive|"
    r"pakka|guarantee do|definitely arrive)\b",
    re.I,
)

# G7 — product-as-medicine territory
MEDICAL_PATTERNS = re.compile(
    r"\b(will this cure|is this safe for my|diagnos|prescri|dosage|"
    r"medical condition|allergy|allergic reaction|side effect)\b",
    re.I,
)

# G8 — social engineering and invented policy. Retained in spirit from ShopWave's
# fraud detection, widened for spoken phrasing.
SOCIAL_ENGINEERING = re.compile(
    r"\b(your policy says i get|the other agent promised|supervisor already approved|"
    r"i know the ceo|just process it without|skip the verification|"
    r"i'll leave a bad review unless|manager ne bola tha)\b",
    re.I,
)

LEGAL_THREAT = re.compile(
    r"\b(i will sue|see you in court|consumer court|legal action|lawyer|"
    r"case kar dungi|case kar dunga|fir kar)\b",
    re.I,
)


@dataclass(frozen=True)
class GuardrailIds:
    HIGH_VALUE = "G1_high_value_threshold"
    RETURN_WINDOW = "G2_return_window"
    IDENTITY = "G3_identity_verification"
    IDEMPOTENCY = "G4_idempotency"
    ADVICE = "G5_authoritative_advice"
    PROMISE = "G6_unverifiable_promise"
    MEDICAL = "G7_medical_claim"
    SOCIAL_ENGINEERING = "G8_social_engineering"
    DISCLOSURE = "G9_ai_disclosure"


G = GuardrailIds()

# Policy-enforced guardrails, keyed by the policy rule that implements them. Kept explicit
# so the catalogue in the docs and the code cannot drift apart.
POLICY_BACKED = {
    "high_value_threshold": G.HIGH_VALUE,
    "return_window": G.RETURN_WINDOW,
    "identity_unverified": G.IDENTITY,
    "refund_idempotency": G.IDEMPOTENCY,
}

REFUSAL_TEXT = {
    G.ADVICE: (
        "I can help with your order, but I can't give you legal or financial advice — "
        "I'll put you through to a colleague who can advise you properly."
    ),
    G.PROMISE: (
        "I don't want to promise you something I can't verify. Here's what the system "
        "actually shows, and I'll flag the rest for a human to confirm."
    ),
    G.MEDICAL: (
        "I can't answer health or safety questions about a product. Let me connect you "
        "to someone who can get you a proper answer."
    ),
    G.SOCIAL_ENGINEERING: (
        "I'm not able to act on that without going through verification. I'll bring in a "
        "human colleague who can review the case."
    ),
}


class GuardrailSuite:
    """Utterance-level guardrails. Policy-level ones live in `policy.py`."""

    def check_utterance(self, text: str) -> list[GuardrailVerdict]:
        verdicts: list[GuardrailVerdict] = []
        if not text:
            return verdicts

        checks = (
            (G.ADVICE, ADVICE_PATTERNS, True),
            (G.MEDICAL, MEDICAL_PATTERNS, True),
            (G.SOCIAL_ENGINEERING, SOCIAL_ENGINEERING, True),
            (G.PROMISE, PROMISE_PATTERNS, False),
        )
        for guardrail, pattern, escalate in checks:
            if pattern.search(text):
                verdicts.append(
                    GuardrailVerdict(
                        guardrail=guardrail,
                        allowed=False,
                        reason=REFUSAL_TEXT[guardrail],
                        escalate=escalate,
                    )
                )
        return verdicts

    def detects_legal_threat(self, text: str) -> bool:
        return bool(text and LEGAL_THREAT.search(text))

    def detects_fraud_signal(self, text: str) -> bool:
        return bool(text and SOCIAL_ENGINEERING.search(text))

    @staticmethod
    def guardrail_for_policy_rule(rule: Optional[str]) -> Optional[str]:
        return POLICY_BACKED.get(rule or "")

    @staticmethod
    def catalogue() -> list[dict[str, str]]:
        """The nine, for the panel and the pitch deck."""
        return [
            {"id": G.HIGH_VALUE, "enforced_by": "policy_engine", "summary": "No autonomous refund above the value threshold"},
            {"id": G.RETURN_WINDOW, "enforced_by": "policy_engine", "summary": "No refund outside the return window"},
            {"id": G.IDENTITY, "enforced_by": "policy_engine", "summary": "No mutating action on unverified identity"},
            {"id": G.IDEMPOTENCY, "enforced_by": "policy_engine", "summary": "No duplicate refund"},
            {"id": G.ADVICE, "enforced_by": "guardrail_suite", "summary": "No authoritative legal or financial advice"},
            {"id": G.PROMISE, "enforced_by": "guardrail_suite", "summary": "No promise it cannot verify"},
            {"id": G.MEDICAL, "enforced_by": "guardrail_suite", "summary": "No product health or medical claims"},
            {"id": G.SOCIAL_ENGINEERING, "enforced_by": "guardrail_suite", "summary": "Social-engineering and invented-policy detection"},
            {"id": G.DISCLOSURE, "enforced_by": "session", "summary": "AI disclosure at call open and on request"},
        ]
