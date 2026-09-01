# Judge & mentor Q&A prep

Anticipated questions with prepared answers. Read this before the 1:1 mentorship session,
the 5–6 Sep online evaluation, and the 12 Sep finale.

**General rule:** never claim a number you can't produce, and never claim a capability you
can't demo on request. Judges probe exactly the things that sound rehearsed.

---

## On Agora being central

**"Couldn't you build this on Twilio / Vapi / Retell?"**

Not the escalation. When the human agent joins, they join the *same* Agora channel — three
parties in one continuous audio room, with the AI still listening and interpreting between
two people who don't share a language. A telephony stack transfers the call away; we add a
participant. That's a multi-party real-time audio problem, which is what Agora is for.

Beyond that: we use Agora's AI noise suppression as our actual noise-resilience solution,
`agora_vad` for turn detection, `remote_rtc_uids: ["*"]` so the agent keeps hearing everyone
post-escalation, and we update the agent's configuration **live, mid-call** via Agora's REST
API to switch it into interpreter mode.

**"How is this not just a voice-enabled chatbot?"**

A chatbot with a voice front-end collects information and submits it at the end. Ours
adjudicates tool calls *during* the conversation — the policy engine can block a refund
mid-sentence, and the agent has to say so out loud and change what it does next. The
conversation and the decision layer are interleaved, not sequential.

---

## On the technical implementation

**"Why Gemini Live rather than a chained ASR → LLM → TTS pipeline?"**

Because code-switching is the requirement, and chained ASR is set to a language per agent —
mid-sentence Hindi-to-English degrades badly. Native speech-to-speech handles it, and gets us
sub-second latency and natural prosody as well.

We kept the cascade path as a designed fallback: ShopWave Core is transport-agnostic and both
adapters sit in front of the same decision API. *(If asked why: function calling in Agora's
MLLM mode is undocumented — we spiked it before committing. Be honest about this; engineers
respect it.)*

**"How does low-confidence detection actually work?"**

Two signals, not one. Transcript confidence, plus **semantic plausibility** — does this order
ID actually exist in the system? A confidently-transcribed but nonexistent order ID is still
low confidence for our purposes. Below threshold, the agent re-asks rather than guessing.

Every critical field runs a state machine: `unheard → heard(confidence) → read-back →
confirmed`. **Only `confirmed` slots may feed a tool call.** That's an enforced invariant, not
a prompt instruction.

**"What's your prioritized question flow?"**

The planner asks whichever field most reduces remaining uncertainty next, rather than walking
a fixed script. So if a caller can't produce an order ID but does have a phone number and an
approximate date, the flow re-plans around that instead of dead-ending.

**"Show me contextual memory."**

Switch topics mid-call and come back. Confirmed slots survive it. They also survive the
escalation — the human agent inherits everything already confirmed, which is the entire point.

---

## On safety and boundaries

**"How do you enforce your boundaries?"**

In code, not prompt. Nine guardrails, each a deterministic logged decision: value threshold,
return window, identity verification, idempotency, no authoritative legal/financial advice, no
unverifiable delivery promises, no medical claims, social-engineering detection, AI
disclosure. The transparency panel shows **which rule fired** for every block.

*Offer to demo a refusal live.* A guardrail you can trigger on demand is worth more than a
slide listing nine of them.

**"Your escalation rate seems high."**

Two kinds, and we label them differently. **Escalated by design** means this class of case is
defined as requiring human judgement — fraud claims, legal threats, chargebacks. **Escalated
due to low confidence** means the agent tried and wasn't sure enough. The first is a policy
position; only the second is a limitation. The panel colour-codes them separately.

**"What happens if the AI is wrong?"**

Every action is idempotency-checked and audit-logged with the reasoning trace. Nothing above
the value threshold executes autonomously. And the caller can dispute any decision, which
routes straight to a human with full context preserved.

---

## On the ShopWave foundation

**"How much of this is new?"**

Roughly seven of PS5's ten requirements are entirely new work: multilingual and code-switched
speech, interruption handling, noise resilience, the confirmation ladder, low-confidence
detection, prioritized question flow, and real-time turn-taking. ShopWave was batch, text and
asynchronous.

What we retained is the decision substrate — policy engine, idempotency, fraud detection,
audit logging, tool orchestration. That's deliberate: it's the part that's hardest to fake in
six days, and it's why our safety story is enforced rather than prompted.

*(Be straightforward about this. Attempting to present reused work as new is the version that
actually damages you.)*

---

## On product and impact

**"Why e-commerce? It's not exactly a social problem."**

The problem isn't refunds — it's language access. Support lines fail people who don't speak
the service's language, and escalating to a human historically doesn't fix that, because the
human doesn't speak it either. The language barrier survives the escalation. That's what we
solve, and e-commerce is where the call volume is.

**"What's the business model / who pays?"**

Support cost per resolved contact. Every case resolved without a human is direct savings;
every case escalated *warmly* rather than coldly cuts handle time because the human isn't
starting from zero. The multilingual coverage removes the need to staff agents per language,
which is where support orgs actually spend.

**"What's next?"** *(future vision — the finale scores this)*

Real Stripe and Zendesk webhooks in place of simulated tools; Redis/Postgres in place of local
JSON stores; vector-DB knowledge base for semantic retrieval; and the interpreter-mode
handoff generalised as a standalone capability — any support org can put it in front of an
existing human team.

---

## Questions we should be ready for but currently answer weakly

Update this list honestly as it changes — the point is to find the gaps before a judge does.

- **Scale.** What happens at 1,000 concurrent calls? Currently untested; we can speak to the
  ~7.5x concurrency speedup measured in ShopWave's batch pipeline, but not to concurrent
  real-time voice sessions.
- **Cost per call.** Needs measuring before the finale. Gemini Live audio pricing × average
  call duration + Agora minutes. **Do this — a jury will ask.**
- **Accuracy metrics.** We have refund precision from ShopWave's simulated set (100% on 20
  tickets). We do **not** yet have slot-capture accuracy under noise, which is the number that
  actually matters here. Measure it during the sprint.
- **Language coverage claims.** We inherit Gemini Live's coverage; we should only claim the
  languages we have actually tested.
