"""Intent taxonomy and rule-first classifier.

Three tiers, 23 intents. See docs/03-case-coverage.md.

  Tier 1 (5)  hero flows — full depth, demo path
  Tier 2 (9)  resolve end-to-end, thinner slot sets
  Tier 3 (9)  recognised and routed, deliberately not resolved

Breadth is cheap here on purpose: recognising an intent costs a row in a table, while
resolving one costs slots, policy rules and tests. The rule engine classifies in O(1)
against multilingual keyword sets (including romanised Hindi, since callers type and
speak Hinglish); an LLM fallback handles nuance only when the rules abstain.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Awaitable, Callable, Optional

from app.core.models import EscalationKind


@dataclass(frozen=True)
class FieldSpec:
    name: str
    critical: bool = True
    resolving_power: float = 0.5
    max_attempts: int = 3
    pattern: Optional[str] = None


@dataclass(frozen=True)
class IntentSpec:
    name: str
    tier: int
    # Alternative satisfying sets. The planner picks whichever is closest to complete,
    # which is how the question flow re-plans when a caller cannot produce an order ID.
    requires: tuple[tuple[str, ...], ...] = ()
    actions: tuple[str, ...] = ()
    escalation: Optional[EscalationKind] = None
    keywords: tuple[str, ...] = ()

    @property
    def resolvable(self) -> bool:
        return self.tier in (1, 2)


FIELDS: dict[str, FieldSpec] = {
    "order_id": FieldSpec("order_id", True, resolving_power=1.0, pattern=r"ORD-\d{4}"),
    "phone": FieldSpec("phone", True, resolving_power=0.7, pattern=r"\+?\d[\d\s-]{7,14}"),
    "email": FieldSpec("email", True, resolving_power=0.7, pattern=r"[^@\s]+@[^@\s]+\.\w+"),
    "order_date": FieldSpec("order_date", False, resolving_power=0.4),
    "product_name": FieldSpec("product_name", False, resolving_power=0.4),
    "issue_description": FieldSpec("issue_description", False, resolving_power=0.3),
    "new_address": FieldSpec("new_address", True, resolving_power=0.6),
    "preferred_resolution": FieldSpec("preferred_resolution", False, resolving_power=0.3),
}

_ID = (("order_id",),)
_ID_OR_LOOKUP = (("order_id",), ("phone", "order_date", "product_name"))


INTENTS: dict[str, IntentSpec] = {
    # ---- Tier 1 — hero flows -------------------------------------------------
    "damaged_item": IntentSpec(
        "damaged_item", 1, _ID_OR_LOOKUP, ("refund", "replacement"),
        keywords=("damaged", "broken", "cracked", "defective", "kharab", "toota", "tuta"),
    ),
    "not_delivered": IntentSpec(
        "not_delivered", 1, _ID_OR_LOOKUP, ("investigate", "refund", "replacement"),
        keywords=("not delivered", "never arrived", "missing", "nahi mila", "nahi aaya",
                  "marked delivered"),
    ),
    "return_refund": IntentSpec(
        "return_refund", 1, _ID_OR_LOOKUP, ("refund",),
        keywords=("return", "refund", "money back", "wapas", "paisa wapas", "return karna"),
    ),
    "cancel_order": IntentSpec(
        "cancel_order", 1, _ID, ("cancel",),
        keywords=("cancel", "cancel karna", "rad", "don't want"),
    ),
    "wrong_item": IntentSpec(
        "wrong_item", 1, _ID_OR_LOOKUP, ("replacement", "refund"),
        keywords=("wrong item", "different product", "galat", "wrong product", "not what i ordered"),
    ),
    # ---- Tier 2 — resolve end-to-end ----------------------------------------
    "order_status": IntentSpec(
        "order_status", 2, _ID, ("status_reply",),
        keywords=("where is my order", "track", "status", "kahan hai", "tracking"),
    ),
    "address_change": IntentSpec(
        "address_change", 2, (("order_id", "new_address"),), ("update_address",),
        keywords=("change address", "wrong address", "address badalna", "shift"),
    ),
    "exchange": IntentSpec(
        "exchange", 2, _ID_OR_LOOKUP, ("replacement",),
        keywords=("exchange", "different size", "size", "colour", "color", "badal"),
    ),
    "refund_status": IntentSpec(
        "refund_status", 2, _ID, ("status_reply",),
        keywords=("refund status", "where is my money", "paisa kab", "refund kab"),
    ),
    "payment_failed": IntentSpec(
        "payment_failed", 2, _ID_OR_LOOKUP, ("investigate", "refund"),
        keywords=("payment failed", "money deducted", "debited", "paisa kat", "transaction failed"),
    ),
    "warranty": IntentSpec(
        "warranty", 2, _ID_OR_LOOKUP, ("warranty_claim",),
        keywords=("warranty", "guarantee", "stopped working", "band ho gaya"),
    ),
    "promo_code": IntentSpec(
        "promo_code", 2, _ID, ("policy_reply",),
        keywords=("promo", "coupon", "discount", "code", "offer nahi laga"),
    ),
    "subscription": IntentSpec(
        "subscription", 2, (("email",),), ("update_subscription",),
        keywords=("subscription", "pause", "unsubscribe", "renew", "membership"),
    ),
    "invoice": IntentSpec(
        "invoice", 2, _ID, ("send_invoice",),
        keywords=("invoice", "bill", "receipt", "gst", "tax"),
    ),
    # ---- Tier 3 — recognised, routed to a human -----------------------------
    "account_access": IntentSpec(
        "account_access", 3, (), ("escalate",), EscalationKind.BY_DESIGN,
        keywords=("can't log in", "cannot login", "password", "locked out", "account blocked"),
    ),
    "fraud_chargeback": IntentSpec(
        "fraud_chargeback", 3, (), ("escalate",), EscalationKind.BY_DESIGN,
        keywords=("fraud", "chargeback", "unauthorised", "unauthorized", "stolen card", "dispute charge"),
    ),
    "seller_dispute": IntentSpec(
        "seller_dispute", 3, (), ("escalate",), EscalationKind.BY_DESIGN,
        keywords=("seller", "marketplace", "third party", "vendor"),
    ),
    "bulk_b2b": IntentSpec(
        "bulk_b2b", 3, (), ("escalate",), EscalationKind.BY_DESIGN,
        keywords=("bulk", "wholesale", "b2b", "corporate", "hundred units"),
    ),
    "legal_threat": IntentSpec(
        "legal_threat", 3, (), ("escalate",), EscalationKind.BY_DESIGN,
        keywords=("sue", "lawyer", "legal action", "consumer court", "case kar", "fir"),
    ),
    "delivery_agent_complaint": IntentSpec(
        "delivery_agent_complaint", 3, (), ("escalate",), EscalationKind.BY_DESIGN,
        keywords=("delivery boy", "courier was rude", "driver", "delivery agent"),
    ),
    "restock": IntentSpec(
        "restock", 3, (), ("policy_reply",), EscalationKind.BY_DESIGN,
        keywords=("out of stock", "restock", "when available", "kab aayega stock"),
    ),
    "policy_question": IntentSpec(
        "policy_question", 3, (), ("policy_reply",), EscalationKind.BY_DESIGN,
        keywords=("policy", "how many days", "terms", "return window", "kitne din"),
    ),
    "out_of_scope": IntentSpec(
        "out_of_scope", 3, (), ("escalate",), EscalationKind.BY_DESIGN,
    ),
}

TIER_1 = [i for i in INTENTS.values() if i.tier == 1]
TIER_2 = [i for i in INTENTS.values() if i.tier == 2]
TIER_3 = [i for i in INTENTS.values() if i.tier == 3]

LlmFallback = Callable[[str], Awaitable[Optional[str]]]


@dataclass
class Classification:
    intent: str
    confidence: float
    matched: list[str] = dc_field(default_factory=list)
    source: str = "rules"


class IntentClassifier:
    """Rule-first, LLM only for what the rules abstain on."""

    def __init__(self, llm_fallback: Optional[LlmFallback] = None) -> None:
        self._llm = llm_fallback

    async def classify(self, text: str) -> Classification:
        lowered = (text or "").lower()
        best: Optional[tuple[IntentSpec, list[str]]] = None

        for spec in INTENTS.values():
            hits = [kw for kw in spec.keywords if kw in lowered]
            if hits and (best is None or len(hits) > len(best[1])):
                best = (spec, hits)

        if best is not None:
            spec, hits = best
            # More distinct keyword hits means less ambiguity, but a single strong hit is
            # still a confident classification for this domain.
            confidence = min(0.95, 0.7 + 0.1 * (len(hits) - 1))
            return Classification(spec.name, confidence, hits, "rules")

        if self._llm is not None:
            guess = await self._llm(text)
            if guess and guess in INTENTS:
                return Classification(guess, 0.6, [], "llm")

        return Classification("out_of_scope", 0.3, [], "default")


def required_fields(intent: str) -> tuple[tuple[str, ...], ...]:
    spec = INTENTS.get(intent)
    return spec.requires if spec else ()


def is_escalate_by_design(intent: str) -> bool:
    spec = INTENTS.get(intent)
    return bool(spec and spec.escalation is EscalationKind.BY_DESIGN)
