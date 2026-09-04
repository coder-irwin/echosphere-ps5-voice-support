"""A human agent, once on the call, can approve an action the policy engine blocked —
the missing piece behind the demo script's "operator approves in the console" beat.
"""

import pytest

from app.core.audit import Kind
from app.core.models import ProposedAction

pytestmark = pytest.mark.asyncio


async def _identify(session, order_id="ORD-4471", phone="+91-98100-44711"):
    await session.observe_slot("phone", phone, 0.97)
    session.confirm_slot("phone")
    await session.observe_slot("order_id", order_id, 0.95)
    session.confirm_slot("order_id")
    await session.propose_action(ProposedAction(tool="get_customer", args={"phone": phone}))
    await session.propose_action(ProposedAction(tool="get_order", args={"order_id": order_id}))
    return session.context.order


async def test_override_refused_without_a_human_on_the_call(session):
    await _identify(session)
    outcome = await session.human_override(
        ProposedAction(tool="issue_refund", args={"order_id": "ORD-4471", "amount": 18400.0}),
        approved_by="Rahul",
    )
    assert outcome.executed is False
    assert outcome.policy.rule == "override_requires_human_present"


async def test_override_still_enforces_slot_backing(session):
    session.human_joined("Rahul")
    outcome = await session.human_override(
        ProposedAction(tool="issue_refund", args={"order_id": "ORD-9999", "amount": 18400.0}),
        approved_by="Rahul",
    )
    assert outcome.executed is False
    assert outcome.policy.rule == "unconfirmed_slot"


async def test_override_executes_a_high_value_refund_the_policy_blocked(session):
    order = await _identify(session)
    assert order.amount == 18400.0

    blocked = await session.propose_action(
        ProposedAction(tool="issue_refund", args={"order_id": "ORD-4471", "amount": 18400.0})
    )
    assert blocked.executed is False
    assert session.escalation is not None

    session.human_joined("Rahul")
    outcome = await session.human_override(
        ProposedAction(tool="issue_refund", args={"order_id": "ORD-4471", "amount": 18400.0}),
        approved_by="Rahul",
    )

    assert outcome.executed is True
    assert outcome.result["success"] is True
    assert session.audit.of_kind(Kind.HUMAN_OVERRIDE)
    override_event = session.audit.of_kind(Kind.HUMAN_OVERRIDE)[0]
    assert override_event.payload["approved_by"] == "Rahul"
