# Risks and open questions

Ranked by how badly they hurt. Each has a de-risking action and a deadline.

---

## R1 — Function calling in Gemini Live MLLM mode is undocumented

**Status (1 Sep 2026):** still unverified against the live API — this requires a real
Agora App ID/Certificate and Gemini key, which weren't available when this risk was
written. The mitigation is no longer just designed for; it is **built and deployed**: the
cascade path (`AGENT_MODE=cascade`) runs today at the production URL in
[docs/09-deployment.md](09-deployment.md), served by `app/main.py`'s
`/agora/llm/{channel}/v1/chat/completions` webhook and `app/core/orchestrator.py`. Once
real credentials are wired in, do the MLLM spike; if it fails, cascade is already the
default and needs no code change to fall back to.

**Severity:** critical. Sinks the primary architecture path.

Agora's Gemini Live docs cover `vendor`, `model`, `instructions`, `voice`,
`input_modalities`, `output_modalities`, `transcribe_agent`, `transcribe_user` and
`turn_detection` — but say **nothing about tools or function declarations**. Gemini Live
supports function calling natively; whether Agora passes tool declarations through the MLLM
integration is unverified.

Since ShopWave's entire value is policy-adjudicated tool calls, this decides the architecture.

**Action:** build a minimal spike — one Agora agent in MLLM mode with a single trivial tool
declaration (`get_order`). Confirm the tool actually fires. Ask in the Agora Discord in
parallel.

**Deadline:** this week. You have until 29 Aug before the sprint even opens — there is no
reason to carry this unknown into the build.

**Mitigation if it fails:** cascade path with `llm.vendor: "custom"`. Already designed for;
ShopWave Core is transport-agnostic and the adapter is ~200 lines.

---

## R2 — The reuse rule — RESOLVED (1 Sep 2026)

**Status:** resolved. Organisers confirmed offline that reusing Akaash's own prior
ShopWave engine, re-domained and combined with an entirely new real-time conversational
layer, is acceptable. Logged here per the "document every iteration" rule rather than
silently dropped — see [docs/01-decision-log.md](01-decision-log.md).

**Severity (pre-resolution):** critical. Potential disqualification.

The FAQ lists as a disqualifier: *"The project is copied without significant modification."*
This is your own prior work rather than someone else's — materially different — but it is a
**completed submission from another hackathon four months ago**, and many hackathons require
the build to happen during the sprint.

**Action:** ask the organisers directly in the WhatsApp group or Agora Discord. Get the
answer **in writing**. Frame it accurately: *"We have a prior open-source project of our own
containing a policy/audit engine. We intend to build the entire real-time conversational
layer new and reuse that engine as a component. Is that acceptable?"*

**Deadline:** before the 26–28 Aug idea submission. Better to find out on 10 August than on
5 September.

**Mitigation if disallowed:** rebuild the policy engine from scratch. It is genuinely a few
days of work — the design is known, only the code needs to be new.

---

## R3 — The voice-wrapper trap

**Severity:** high. The named disqualifier.

*"The project is only a voice-enabled chatbot"* and *"Agora must remain the core voice
interaction platform."* If the architecture reads as "Agora front-end → existing ShopWave
pipeline," that is precisely what the screening is designed to catch.

**Mitigation, by design:**

- The policy engine adjudicates tool calls **mid-conversation**, not at the end. It is not a
  voice form that submits a ticket.
- The warm escalation puts three parties in one continuous Agora channel with live
  interpretation — unbuildable on a phone-tree stack.
- Agora AI noise suppression is used as the actual noise-resilience solution.
- Agent configuration is updated **live, mid-call**, via Agora's REST API.

**Action:** make these four points explicit in the architecture diagram and the pitch. Do
not let the judges have to infer them.

---

## R4 — Latency budget

**Severity:** high. Degrades the core UX claim.

Target is **under 1.5s** round trip. The confirmation ladder deliberately adds conversational
turns — if each turn is slow, the ladder becomes the thing that makes the call frustrating
rather than the thing that makes it trustworthy. The mechanism inverts.

**Action:** measure end-to-end turn latency from day one of the sprint and put it on the
transparency panel. If it exceeds budget, shorten the ladder (batch-confirm two fields in one
utterance) rather than removing it.

---

## R5 — Live demo in a noisy hall

**Severity:** medium, and partly an opportunity.

The Delhi finale room will be loud. That is either the worst enemy of a voice demo or the
best unplanned demonstration of noise resilience you could ask for.

**Action:** test with real background noise early. Have a wired headset as fallback for the
caller role. Decide in advance whether to lean into the room noise as part of the pitch —
if noise suppression genuinely holds up, calling attention to it is far more convincing than
any slide.

---

## R6 — Deployment must be publicly reachable

**Severity:** medium.

The 5–6 Sep online evaluation is a **live demo** and no modifications are permitted during
that window. Localhost is not an option, and neither is a last-minute deploy.

**Action:** deploy early and keep it deployed. Freeze and smoke-test before 4 Sep 23:59 IST.

---

## R7 — Impact narrative is weak for e-commerce

**Severity:** medium. Affects the Grand Finale pitch, not the technical evaluation.

E-commerce refunds is the weakest impact story of every domain examined. The Shark
Tank–style finale explicitly scores "the problem they solved" and "impact."

**Mitigation:** lean hard on the UX and language-access framing rather than on cause impact.
The defensible version of the story: support lines fail people who don't speak the service's
language, and escalating to a human historically doesn't fix that because the human doesn't
speak it either. That is a real, large, global problem, and it is what this solves.

---

## Open questions for the organisers

1. Is reuse of our own prior open-source project as a component acceptable? *(R2)*
2. Is the "Open Innovation" track actually available? The overview page mentions it; the FAQ
   says own problem statements are not permitted. *(Not blocking — we're on PS5.)*
3. Any constraint on where the prototype is hosted for the live evaluation?

## Open questions for Agora (Discord)

1. Does the Gemini Live MLLM integration support function calling / tool declarations? *(R1)*
2. Recommended `idle_timeout` configuration when using `remote_rtc_uids: ["*"]`?
3. Is agent configuration update supported mid-call while in MLLM mode? (Needed for the
   interpreter-mode switch on escalation.)
