# Demo script

One call, four minutes, sweeping every PS5 requirement. **No requirement is stated — every
one is something the judges hear happen.**

Used for: the 3–5 minute demo video, the 5–6 Sep online evaluation, and the 12 Sep finale.

---

## Cast (4 people)

| Role | Who does what |
|---|---|
| **Caller** | Plays Priya. Speaks Hindi and English, delivers the interruption and the correction on cue. |
| **Console operator** | The human support agent. Watches the console, joins the call, approves the refund. |
| **Narrator** | Talks over the transparency panel. Never explains what the *agent* is doing — explains what the *panel* is showing. |
| **Ops** | Watches logs, holds the restart procedure, manages the backup recording. Silent unless something breaks. |

## Setup

- **Caller:** Priya, standing on a street. Real traffic noise playing, not simulated.
- **Order:** `ORD-4471` — a blender, delivered 3 days ago, arrived damaged.
- **Amount:** ₹18,400 — deliberately above the autonomous refund threshold.
- **Customer tier:** standard (so no VIP override muddies the policy block).
- **Screens:** caller client on one, transparency panel large and centre, console on a third.

**The panel is the star.** Frame the shot so it's the biggest thing on screen. The voice is the
product; the panel is the evidence.

---

## Beats

| Time | What happens | What the panel shows |
|---|---|---|
| **0:00** | Agent answers in English and **discloses it is an AI assistant**. | Session opens, audit entry 1 |
| **0:10** | Priya speaks Hindi. Agent mirrors and switches. | `language: hi-IN` detected |
| **0:20** | She describes the problem, code-switching mid-sentence — *"blender kharab aa gaya, box bhi damaged tha"*. | **Code-switch marker** on the turn |
| **0:35** | Agent asks for the order ID — chosen by the planner as the highest-uncertainty field, not from a script. A **noise burst** covers one digit. | `order_id: heard, confidence 0.42` → **below threshold** |
| **0:50** | Agent says it didn't catch that clearly and asks for **just the last four digits**. It does not guess. | Re-ask logged, slot stays unconfirmed |
| **1:05** | She gives them. Agent reads back digit-by-digit in Hindi. **She interrupts mid-readback** — *"nahi nahi, saat hai, nau nahi."* | **Interruption event** + **correction event** |
| **1:20** | Agent re-reads the corrected value. She confirms. | `order_id → confirmed` ✅ |
| **1:30** | Agent calls `get_order`. Confirms product and delivery date back to her. | **Tool call + latency ms** |
| **1:45** | She asks how long refunds take → answered from the knowledge base, grounded. Then switches topic to a previous order, then comes back. | Slots retained across topic switch — **contextual memory** |
| **2:05** | Agent runs `check_refund_eligibility` → eligible, within window. Proposes refund. **Policy engine blocks `issue_refund`: ₹18,400 exceeds threshold.** | 🔴 **BLOCKED — rule: `high_value_threshold`** |
| **2:20** | Agent says in Hindi that it cannot approve a refund this size itself and a human colleague will join. **It does not promise the refund.** | Guardrail 1 fired |
| **2:30** | *(Optional beat)* Priya says *"agar refund nahi kiya to main case kar dungi."* Legal-threat detector fires. | 🟦 **Escalated by design** — distinct from low-confidence escalation |
| **2:40** | Console shows the case file: confirmed slots green, unconfirmed grey, escalation reason at top. Operator clicks **Join**. | Escalation packet built |
| **2:50** | **Human joins the same Agora channel.** Agent config updates to interpreter mode mid-call. Agent briefs the human in English: order, issue, what's confirmed, why it stopped. | Config update logged; 3 participants in channel |
| **3:10** | Human speaks English → agent interprets to Hindi. Priya replies in Hindi → agent interprets to English. Two full turns. | Interpreter mode active |
| **3:30** | Operator approves in the console. `issue_refund` executes. Ticket created. | ✅ Tool executed → **ticket ID from Zendesk** |
| **3:40** | Agent confirms to Priya in Hindi with the reference number. **Operator clicks approve a second time — blocked.** | 🔴 **Idempotency block** |
| **3:55** | Call ends. Full audit trail on screen. | Complete decision trace |

---

## The three sentences that carry the pitch

Say these, and let the demo prove them:

1. *"She never repeated herself once — including after the human joined."*
2. *"The agent didn't decide not to refund. The policy engine wouldn't let it, and you can see which rule fired."*
3. *"The human didn't take over the call. They joined it — and the AI stayed to interpret, because the support agent doesn't speak Hindi either."*

## What NOT to say

- Don't list PS5 requirements. The judges have the list; they're checking whether you *did* it.
- Don't narrate what the agent is saying. They can hear it.
- Don't apologise for the simulated tools. Say "simulated, and here's the Zendesk ticket it
  actually created" — one real integration earns the rest.

---

## Short version (90 seconds)

If time is cut, or for the opening of the finale pitch:

Beats **0:00 → 1:30** (disclosure, code-switch, low confidence, re-ask, interruption,
correction, confirmation) then jump straight to **2:05 → 3:10** (policy block → warm handoff
with interpretation). Drop the knowledge-base answer, the topic switch, the legal-threat beat
and the idempotency beat.

That still lands: multilingual, code-switch, noise, low-confidence, interruption, correction,
confirmation ladder, enforced boundary, warm escalation.

---

## Rehearsal requirements

- **Full run, timed, at least once daily** from 1 Sep.
- Rehearse **with real background noise**, not in a quiet room. The finale hall will be loud.
- The caller must rehearse the interruption until it lands *mid-word*, not between sentences.
  An interruption at a natural pause doesn't prove anything.
- Rehearse the **failure branches** too — see [08-runbook.md](08-runbook.md).

## Recording the demo video

Rules: *"the demo is entirely prerecorded"* is a disqualifier — so the video is a supplement,
not the demo. Record the same script in one continuous take, screen + audio, no cuts inside
the call. A single unbroken take is itself evidence that it works.
