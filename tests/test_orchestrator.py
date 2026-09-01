"""Cascade orchestration loop, driven with a stub Gemini client so it's deterministic and
needs no network or API key.
"""

import pytest

from app.core.orchestrator import run_turn

pytestmark = pytest.mark.asyncio


class StubGemini:
    configured = True

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = 0

    async def generate(self, contents, instruction, tools=None):
        self.calls += 1
        return self._turns.pop(0)


async def test_not_configured_gives_a_clear_message_instead_of_failing(session):
    from app.adapters.llm import GeminiClient

    outcome = await run_turn(session, "hello", gemini=GeminiClient(api_key=""))
    assert outcome["configured"] is False
    assert "GEMINI_API_KEY" in outcome["spoken"]


async def test_tool_call_is_adjudicated_then_result_fed_back(session):
    await session.observe_slot("phone", "+91-98100-44711", 0.97)
    session.confirm_slot("phone")

    stub = StubGemini(
        [
            {"text": "", "tool_calls": [{"name": "get_customer", "args": {"phone": "+91-98100-44711"}}]},
            {"text": "Found your account. How can I help?", "tool_calls": []},
        ]
    )

    outcome = await run_turn(session, "hi, it's about my order", gemini=stub)

    assert outcome["configured"] is True
    assert outcome["spoken"] == "Found your account. How can I help?"
    assert stub.calls == 2
    assert "get_customer" in session.attempted_actions


async def test_blocked_tool_call_result_is_fed_back_not_executed(session):
    stub = StubGemini(
        [
            {
                "text": "",
                "tool_calls": [
                    {"name": "issue_refund", "args": {"order_id": "ORD-4471", "amount": 18400.0}}
                ],
            },
            {"text": "I can't process that myself — bringing in a colleague.", "tool_calls": []},
        ]
    )

    outcome = await run_turn(session, "refund my order ORD-4471 please", gemini=stub)

    assert outcome["spoken"] == "I can't process that myself — bringing in a colleague."
    assert len(session.blocked_verdicts) == 1
    assert session.blocked_verdicts[0].rule == "unconfirmed_slot"


async def test_loop_that_never_stops_calling_tools_escalates_instead_of_hanging(session):
    forever_tool_call = {
        "text": "",
        "tool_calls": [{"name": "search_knowledge_base", "args": {"query": "returns"}}],
    }
    stub = StubGemini([forever_tool_call] * 10)

    outcome = await run_turn(session, "what's your return policy", gemini=stub)

    assert session.escalation is not None
    assert "colleague" in outcome["spoken"]


async def test_human_present_short_circuits_the_model_loop(session):
    session.human_joined("Rahul")
    stub = StubGemini([])  # would raise IndexError if called — proves the loop is skipped

    outcome = await run_turn(session, "hello again", gemini=stub)

    assert stub.calls == 0
    assert "human colleague" in outcome["spoken"]
