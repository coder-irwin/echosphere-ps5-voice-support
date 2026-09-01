"""Cascade orchestration loop — the thing that turns a caller utterance into a spoken reply.

This is the "ShopWave Core *is* the LLM" half of the architecture (see docs D7). Gemini
proposes tool calls; `CallSession.propose_action` is the only thing that decides whether a
proposed call is allowed to run. The model never gets more authority than that — it can ask,
it cannot act unilaterally.

Used from two places: the OpenAI-compatible webhook Agora's cascade agent calls, and the
text-chat demo endpoint, so a browser without a microphone still exercises the real brain.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.adapters.llm import GeminiClient
from app.adapters.prompts import base_instruction, interpreter_instruction
from app.core.models import EscalationKind, ProposedAction
from app.core.session import CallSession
from app.tools.registry import gemini_tools

MAX_TOOL_HOPS = 4
FALLBACK_SPOKEN = (
    "I'm having trouble reaching my systems right now — let me bring in a human colleague "
    "so you're not stuck waiting on me."
)


def _contents_from_turns(session: CallSession) -> list[dict[str, Any]]:
    contents = []
    for turn in session.turns:
        role = "user" if turn.speaker == "caller" else "model"
        contents.append({"role": role, "parts": [{"text": turn.text}]})
    return contents


async def run_turn(
    session: CallSession,
    user_text: str,
    gemini: Optional[GeminiClient] = None,
) -> dict[str, Any]:
    """Observe one caller utterance and drive the model/tool loop to a spoken reply."""
    gemini = gemini or GeminiClient()
    await session.observe_turn(user_text, speaker="caller")

    if session.human_present:
        # Interpreter mode: a human is driving the case. Text demo has no second party to
        # interpret for, so just acknowledge — the real interpreter path is Gemini Live audio.
        spoken = "A human colleague is already on this call with you."
        await session.observe_turn(spoken, speaker="agent")
        return {"spoken": spoken, "snapshot": session.snapshot()}

    if not gemini.configured:
        spoken = (
            "I'm not fully wired up yet — my language model key hasn't been configured. "
            "Once GEMINI_API_KEY is set I'll be able to help properly."
        )
        await session.observe_turn(spoken, speaker="agent")
        return {"spoken": spoken, "snapshot": session.snapshot(), "configured": False}

    instruction = (
        interpreter_instruction(session.language.current)
        if session.interpreter_mode
        else base_instruction()
    )
    contents = _contents_from_turns(session)
    tools = gemini_tools()
    spoken = FALLBACK_SPOKEN

    for _ in range(MAX_TOOL_HOPS):
        result = await gemini.generate(contents, instruction, tools=tools)
        if result.get("error"):
            break

        tool_calls = result.get("tool_calls") or []
        if not tool_calls:
            spoken = result.get("text") or FALLBACK_SPOKEN
            break

        contents.append(
            {
                "role": "model",
                "parts": [
                    {"functionCall": {"name": c["name"], "args": c.get("args", {})}}
                    for c in tool_calls
                ],
            }
        )
        for call in tool_calls:
            outcome = await session.propose_action(
                ProposedAction(tool=call["name"], args=call.get("args") or {}, intent=session.intent)
            )
            tool_result = (
                outcome.result
                if outcome.executed
                else {
                    "blocked": True,
                    "reason": outcome.spoken_reason,
                    "rule": outcome.policy.rule if outcome.policy else None,
                }
            )
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"[tool result for {call['name']}] "
                                f"{json.dumps(tool_result, default=str)}"
                            )
                        }
                    ],
                }
            )
    else:
        spoken = (
            "This is taking more steps than it should — let me bring in a human colleague "
            "rather than keep you waiting."
        )
        if session.escalation is None:
            session.escalate(EscalationKind.LOW_CONFIDENCE, "tool loop exceeded max hops")

    await session.observe_turn(spoken, speaker="agent")
    return {"spoken": spoken, "snapshot": session.snapshot(), "configured": True}
