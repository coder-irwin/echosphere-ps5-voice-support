# Design spec — Multilingual voice support line

**Date:** 9 Aug 2026
**Hackathon:** EchoSphere (Agora Conversational AI), PS5
**Status:** Concept, architecture and coverage map approved. Demo script and implementation
plan pending.

---

## Problem

Voice support lines fail people who don't speak the service's language. Escalating to a human
historically doesn't fix this, because the human doesn't speak it either — **the language
barrier survives the escalation.** Meanwhile the caller is stressed, in a noisy place, and
often cannot state their problem cleanly.

PS5 asks for an agent that calmly collects essential information, confirms its understanding,
and transfers to a human when confidence is low or judgement is required. See
[00-hackathon-brief.md](../../00-hackathon-brief.md) for the verbatim statement.

## Goals

1. A caller can conduct an entire support interaction in whatever language(s) they speak,
   including switching mid-sentence.
2. No critical detail is ever acted on without spoken confirmation.
3. The agent knows and states when it is unsure, rather than guessing.
4. Escalation preserves everything — including across a language boundary.
5. Every boundary the agent enforces is a logged, deterministic decision, not a prompt.

## Non-goals

- Outbound calling
- Telephony/PSTN integration (web client only)
- Production-scale concurrency
- Replacing a human support organisation — this is triage plus warm handoff

## Requirements traceability

| PS5 requirement | Where it's satisfied |
|---|---|
| 1. Multilingual & code-switched | Gemini Live native speech-to-speech; language state tracker |
| 2. Natural interruption handling | `agora_vad` turn detection; Agora voice interruption |
| 3. Information collection through conversation | Slot manager + question planner |
| 4. Repetition & confirmation of critical details | Confirmation ladder (`unheard → heard → read-back → confirmed`) |
| 5. Low-confidence detection | Confidence gate: transcript confidence × semantic plausibility |
| 6. Prioritized question flow | Question planner selects max-uncertainty-reduction field |
| 7. Background-noise resilience | Agora AI noise suppression |
| 8. Human escalation with context preservation | Warm escalation — human joins same channel, AI stays as interpreter |
| 9. Ticketing / case-management integration | Zendesk or Freshdesk sandbox |
| 10. Clear boundaries | 9 guardrails enforced in the policy engine |

Universal requirements — real-time voice, natural conversation, interruption handling,
contextual memory, external tool integration, ≥1 meaningful action, human escalation — are all
covered by the above.

## Architecture

Full detail in [02-architecture.md](../../02-architecture.md). Summary:

- **Transport:** one Agora RTC channel per call, `remote_rtc_uids: ["*"]`, Agora AI noise
  suppression, `agora_vad`.
- **Conversation:** Agora Conversational AI Engine with Gemini Live in MLLM mode
  (`gemini-3.1-flash-live-preview`), `transcribe_user`/`transcribe_agent` enabled.
- **Brain:** ShopWave Core — transport-agnostic decision API behind two adapters (MLLM tool
  bridge; OpenAI-compatible `/chat/completions` for the cascade fallback).
- **Surfaces:** caller web client, human agent console, live transparency panel.
- **Persistence:** ShopWave's JSON stores for the prototype; audit log append-only.

### Component boundaries

Each unit has one purpose, a defined interface, and can be tested alone.

| Unit | Does | Interface | Depends on |
|---|---|---|---|
| `slot_manager` | Tracks critical-field state machine | `observe(field, value, conf)`, `confirm(field)`, `state()` | nothing |
| `confidence_gate` | Decides heard vs unsure | `assess(field, value, transcript_conf) -> Confidence` | lookup tools |
| `question_planner` | Picks the next question | `next(slot_state, intent) -> Field \| None` | slot_manager |
| `language_state` | Tracks & mirrors caller language | `observe(turn)`, `current()` | nothing |
| `policy_engine` | Allow/deny an action + reason | `adjudicate(action, context) -> Verdict` | order/customer data |
| `tool_orchestrator` | Executes allowed tools | `execute(tool, args) -> Result` | policy_engine |
| `escalation_packet` | Builds the handoff payload | `build(session) -> Packet` | slot_manager |
| `audit_log` | Append-only decision trace | `record(event)` | nothing |
| `agora_adapter` | Talks to Agora CAI REST | `start()`, `update_config()`, `stop()` | nothing |

**Invariant enforced across units:** a tool call may only reference slots in `confirmed`
state. This is checked in `tool_orchestrator`, not left to the model.

## Data flow

1. Caller joins channel → Agora CAI agent starts with system instruction.
2. Caller speaks → Gemini Live produces a turn; transcript streams to backend.
3. `language_state` records the language; `slot_manager` observes any extracted values.
4. `confidence_gate` assesses each observed value. Low → planner queues a re-ask. High →
   queue a read-back.
5. Read-back spoken in the caller's language; on confirmation the slot becomes `confirmed`.
6. When required slots are confirmed, a tool call is proposed.
7. `policy_engine` adjudicates. Denied → spoken refusal naming the rule, plus escalation path.
   Allowed → `tool_orchestrator` executes.
8. Every step appends to `audit_log` and streams to the transparency panel over WebSocket.
9. On escalation, the console is notified; the human joins the channel; agent config is
   updated to interpreter mode.

## Error handling

| Failure | Behaviour |
|---|---|
| Transcript arrives empty / noise burst | Do not advance slot state; re-ask the same field with a shorter prompt |
| Caller silent | One prompt, then offer human escalation |
| Tool call fails / times out | Retry with backoff (retained from ShopWave); on exhaustion, escalate with context |
| Policy denies | Speak the reason, log the rule, offer escalation. Never silently drop |
| Duplicate action attempted | Idempotency check blocks; agent states it's already done |
| Gemini Live disconnects | Agent restart on the same channel; confirmed slots persist server-side |
| Human agent doesn't join | Ticket filed with full packet; caller told a human will follow up |

**Server-side slot state is the source of truth**, not the model's context window. This is
what makes "never repeat yourself" survive a reconnection.

## Testing

- **Unit:** slot state machine transitions; confidence gate thresholds; policy engine verdicts
  (carried over and extended from ShopWave's deterministic suite).
- **Scenario:** scripted transcript fixtures replaying each of the 9 cross-cutting behaviours
  against the brain, without audio. Fast and deterministic.
- **Audio integration:** recorded utterances with injected background noise, Hindi/English
  code-switch, and mid-utterance corrections, played into a real Agora channel.
- **Demo rehearsal:** the full hero flow end-to-end, timed, at least daily during the sprint.

**Metric to establish early:** slot-capture accuracy under noise. It's the number that
actually matters here and we don't have it yet.

## Open questions

Tracked in [04-risks-and-open-questions.md](../../04-risks-and-open-questions.md).
The two that block: **R1** (function calling in MLLM mode) and **R2** (reuse rule).

## Deferred to implementation planning

- Demo script, beat by beat
- Evaluation-day runbook (5–6 Sep) and finale runbook (12 Sep)
- Sprint schedule across the 4-person team, 29 Aug – 3 Sep
- Cost per call measurement
