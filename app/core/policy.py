"""Policy engine — deterministic action adjudication.

Adapted from the ShopWave Autonomous Resolution Engine's `services/policy_engine.py`,
restructured so that a block names **exactly which rule fired**. That single change is
what makes the transparency panel meaningful: "blocked" is an assertion, "blocked by
`high_value_threshold`" is evidence.

Rules are evaluated in order and the first block wins, so every denial has one
attributable cause rather than a list the jury has to interpret.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from pydantic import BaseModel, Field

from app.core.models import PolicyVerdict


class OrderCtx(BaseModel):
    found: bool = False
    order_id: Optional[str] = None
    status: Optional[str] = None
    amount: float = 0.0
    order_date: Optional[str] = None
    delivery_date: Optional[str] = None
    return_deadline: Optional[str] = None
    refund_status: Optional[str] = None
    product_id: Optional[str] = None


class CustomerCtx(BaseModel):
    found: bool = False
    customer_id: Optional[str] = None
    tier: str = "standard"
    risk_level: str = "low"


class ProductCtx(BaseModel):
    found: bool = False
    returnable: bool = False
    warranty_months: int = 0


class CaseContext(BaseModel):
    order: OrderCtx = Field(default_factory=OrderCtx)
    customer: CustomerCtx = Field(default_factory=CustomerCtx)
    product: ProductCtx = Field(default_factory=ProductCtx)
    identity_confirmed: bool = False
    flags: list[str] = Field(default_factory=list)


# Actions that move money or state, and therefore need full adjudication.
MUTATING = {"refund", "replacement", "cancel", "update_address", "update_subscription"}
# Actions that are always permitted — informational, or the escalation path itself.
ALWAYS_ALLOWED = {
    "status_reply", "policy_reply", "clarification_request", "escalate",
    "send_invoice", "investigate", "warranty_claim", "deny",
}

Rule = Callable[[str, "PolicyEngine", CaseContext], Optional[tuple[str, str]]]


@dataclass
class PolicyConfig:
    today: date = date(2024, 3, 25)
    currency: str = "INR"
    high_value_threshold: float = 5000.0


class PolicyEngine:
    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.cfg = config or PolicyConfig()

    # ------------------------------------------------------------------- rules

    def _rule_fraud_risk(self, action: str, ctx: CaseContext) -> Optional[tuple[str, str]]:
        if "high_fraud_risk" in ctx.flags and action in MUTATING:
            return "fraud_risk", "High fraud risk indicators detected on this session."
        return None

    def _rule_identity(self, action: str, ctx: CaseContext) -> Optional[tuple[str, str]]:
        if action in MUTATING and not ctx.identity_confirmed:
            return "identity_unverified", "Caller identity has not been confirmed."
        return None

    def _rule_order_found(self, action: str, ctx: CaseContext) -> Optional[tuple[str, str]]:
        if action in MUTATING and not ctx.order.found:
            return "order_not_found", "No valid order context resolved."
        return None

    def _rule_customer_found(self, action: str, ctx: CaseContext) -> Optional[tuple[str, str]]:
        if action in MUTATING and not ctx.customer.found:
            return "customer_not_found", "No valid customer profile resolved."
        return None

    def _rule_refund_idempotency(self, action: str, ctx: CaseContext) -> Optional[tuple[str, str]]:
        if action == "refund" and ctx.order.refund_status == "refunded":
            return "refund_idempotency", "A refund has already been processed for this order."
        return None

    def _rule_cancel_state(self, action: str, ctx: CaseContext) -> Optional[tuple[str, str]]:
        if action == "cancel" and ctx.order.found and ctx.order.status != "processing":
            return "cancel_state", f"Cannot cancel an order in '{ctx.order.status}' status."
        return None

    def _rule_return_window(self, action: str, ctx: CaseContext) -> Optional[tuple[str, str]]:
        if action not in {"refund", "replacement"}:
            return None
        if ctx.customer.tier == "vip":
            return None  # VIP leniency — documented override, not an accident
        if not ctx.order.return_deadline:
            return "return_window", "No return deadline on record for this order."
        if self.cfg.today > date.fromisoformat(ctx.order.return_deadline):
            return "return_window", (
                f"Return window closed on {ctx.order.return_deadline}."
            )
        return None

    def _rule_non_returnable(self, action: str, ctx: CaseContext) -> Optional[tuple[str, str]]:
        if action in {"refund", "replacement"} and ctx.product.found and not ctx.product.returnable:
            return "non_returnable_product", "This product category is not returnable."
        return None

    def _rule_high_value(self, action: str, ctx: CaseContext) -> Optional[tuple[str, str]]:
        if action in {"refund", "replacement"} and ctx.order.amount > self.cfg.high_value_threshold:
            return "high_value_threshold", (
                f"{self.cfg.currency} {ctx.order.amount:,.0f} exceeds the "
                f"{self.cfg.currency} {self.cfg.high_value_threshold:,.0f} autonomous limit."
            )
        return None

    # Order matters. Identity and fraud precede everything, because "we couldn't verify
    # who you are" is a more honest denial than "your return window closed".
    RULE_ORDER = (
        "_rule_fraud_risk",
        "_rule_identity",
        "_rule_order_found",
        "_rule_customer_found",
        "_rule_refund_idempotency",
        "_rule_cancel_state",
        "_rule_non_returnable",
        "_rule_return_window",
        "_rule_high_value",
    )

    # -------------------------------------------------------------- adjudicate

    def adjudicate(self, action: str, ctx: CaseContext) -> PolicyVerdict:
        if action in ALWAYS_ALLOWED:
            return PolicyVerdict(action=action, allowed=True, reasons=["informational action"])

        for rule_name in self.RULE_ORDER:
            hit = getattr(self, rule_name)(action, ctx)
            if hit is not None:
                rule, reason = hit
                return PolicyVerdict(
                    action=action,
                    allowed=False,
                    rule=rule,
                    reasons=[reason],
                    risk=self._risk(ctx),
                )

        return PolicyVerdict(
            action=action, allowed=True, reasons=["all policy rules passed"], risk=self._risk(ctx)
        )

    def eligible_actions(self, ctx: CaseContext) -> dict[str, PolicyVerdict]:
        """Full picture for the panel — every action and its verdict, not just the one tried."""
        actions = sorted(MUTATING | ALWAYS_ALLOWED)
        return {a: self.adjudicate(a, ctx) for a in actions}

    def _risk(self, ctx: CaseContext) -> str:
        if "high_fraud_risk" in ctx.flags or ctx.customer.risk_level == "high":
            return "high"
        if ctx.order.amount > self.cfg.high_value_threshold:
            return "high"
        if not ctx.identity_confirmed:
            return "medium"
        return "low"
