"""Policy engine — one test per named rule.

Every block must name exactly one rule. That is what the transparency panel renders, and
what the team has to be able to defend when a judge asks "why did it refuse?"
"""

from datetime import date

import pytest

from app.core.policy import (
    CaseContext,
    CustomerCtx,
    OrderCtx,
    PolicyConfig,
    PolicyEngine,
    ProductCtx,
)

CONFIG = PolicyConfig(today=date(2024, 3, 25), currency="INR", high_value_threshold=5000.0)


def ctx(**over) -> CaseContext:
    base = CaseContext(
        order=OrderCtx(
            found=True, order_id="ORD-4471", status="delivered", amount=1000.0,
            return_deadline="2024-04-21", refund_status=None,
        ),
        customer=CustomerCtx(found=True, tier="standard", risk_level="low"),
        product=ProductCtx(found=True, returnable=True),
        identity_confirmed=True,
    )
    for key, value in over.items():
        if key in {"order", "customer", "product"}:
            setattr(base, key, getattr(base, key).model_copy(update=value))
        else:
            setattr(base, key, value)
    return base


@pytest.fixture
def engine():
    return PolicyEngine(CONFIG)


def test_clean_case_is_allowed(engine):
    assert engine.adjudicate("refund", ctx()).allowed


def test_high_value_threshold_blocks(engine):
    verdict = engine.adjudicate("refund", ctx(order={"amount": 18400.0}))
    assert verdict.blocked
    assert verdict.rule == "high_value_threshold"
    assert "18,400" in verdict.reasons[0]


def test_idempotency_blocks_a_second_refund(engine):
    verdict = engine.adjudicate("refund", ctx(order={"refund_status": "refunded"}))
    assert verdict.rule == "refund_idempotency"


def test_return_window_blocks_when_closed(engine):
    verdict = engine.adjudicate("refund", ctx(order={"return_deadline": "2024-02-18"}))
    assert verdict.rule == "return_window"


def test_vip_override_bypasses_the_return_window(engine):
    verdict = engine.adjudicate(
        "refund",
        ctx(order={"return_deadline": "2024-01-24"}, customer={"tier": "vip"}),
    )
    assert verdict.allowed


def test_non_returnable_category_blocks(engine):
    verdict = engine.adjudicate("refund", ctx(product={"returnable": False}))
    assert verdict.rule == "non_returnable_product"


def test_unverified_identity_blocks_mutating_actions(engine):
    verdict = engine.adjudicate("refund", ctx(identity_confirmed=False))
    assert verdict.rule == "identity_unverified"


def test_fraud_flag_outranks_everything_else(engine):
    verdict = engine.adjudicate(
        "refund",
        ctx(flags=["high_fraud_risk"], order={"amount": 18400.0}, identity_confirmed=False),
    )
    assert verdict.rule == "fraud_risk"


def test_cancel_blocked_once_dispatched(engine):
    assert engine.adjudicate("cancel", ctx(order={"status": "shipped"})).rule == "cancel_state"


def test_cancel_allowed_while_processing(engine):
    assert engine.adjudicate("cancel", ctx(order={"status": "processing"})).allowed


def test_missing_order_blocks_mutating_actions(engine):
    verdict = engine.adjudicate("refund", ctx(order={"found": False}))
    assert verdict.rule == "order_not_found"


def test_informational_actions_are_always_allowed(engine):
    hostile = ctx(
        order={"found": False}, customer={"found": False},
        identity_confirmed=False, flags=["high_fraud_risk"],
    )
    for action in ("status_reply", "policy_reply", "escalate", "clarification_request"):
        assert engine.adjudicate(action, hostile).allowed, action


def test_escalation_is_never_blocked(engine):
    """If escalation could be blocked, a blocked case would have nowhere to go."""
    assert engine.adjudicate("escalate", ctx(flags=["high_fraud_risk"])).allowed


def test_every_block_names_exactly_one_rule(engine):
    cases = [
        ctx(order={"amount": 18400.0}),
        ctx(order={"refund_status": "refunded"}),
        ctx(order={"return_deadline": "2024-02-18"}),
        ctx(product={"returnable": False}),
        ctx(identity_confirmed=False),
        ctx(flags=["high_fraud_risk"]),
        ctx(order={"found": False}),
    ]
    for case in cases:
        verdict = engine.adjudicate("refund", case)
        assert verdict.blocked and verdict.rule and len(verdict.reasons) == 1
