# Decision log

Every decision, the alternatives considered, and the reasoning. Newest session at the bottom.
This is the doc to read before a mentor call or a jury Q&A — it holds the *why*.

---

## Session 1 — 9 Aug 2026

### D1. Problem statement: PS5 (multilingual support line)

**Decision:** PS5 — real-time multilingual voice AI for a customer assistance line.

**Alternatives considered and rejected:**

| Option | Why not |
|---|---|
| PS1 — interview panel | Strongest demo mechanics (multi-agent, judge can sit in the candidate chair) but AI interviewing is a crowded category, and "human escalation" doesn't fit naturally. |
| PS2 — sales agent | Most crowded pick in the field. 1:1 call — Agora becomes an implementation detail rather than load-bearing. |
| PS3 — classroom co-teacher | The impressive engineering is *restraint* (knowing when not to speak), which is hard to build and harder to make legible to a jury in five minutes. |
| PS4 — incident commander | Best enterprise pitch and least crowded, but the agent mostly listens — risks demoing as a transcription tool. Live multi-human demo has more failure modes. |
| Open Innovation | **Not available.** FAQ explicitly forbids own problem statements. |

**Note on the original analysis:** the initial recommendation was PS1, on the grounds that
PS2/PS5 are 1:1 calls that a phone-tree vendor could replicate, making Agora decorative.
That objection is real and PS5 must actively answer it — see D5 (warm escalation), which is
the specific design move that makes Agora structurally necessary.

### D2. Domain: e-commerce customer assistance

**Decision:** e-commerce support (refunds, returns, delivery, warranty).

PS5 permits "customer assistance, public information or non-clinical support" — e-commerce
customer assistance qualifies under the first.

**Alternatives explored (India-focused, then global):**

- Cyber-fraud intake (1930-style) — golden-hour clock, digits-over-noise confirmation
- Railway/station assistance (RailMadad-style) — natural platform noise
- Kisan farmer helpline — 22 languages, but fuzzy information collection
- Migrant worker wage-theft intake — high impact, language mismatch intrinsic
- Welfare scheme eligibility navigator — huge reach, high "uncertain info as fact" risk
- Gig worker grievance line — most startup-shaped
- Aid access line for displaced people — 117.8M displaced, UNHCR down a third of staff
- Family tracing / reunification — cross-script phonetic name matching, highest novelty

**Why e-commerce won:** it reuses the ShopWave engine's existing domain model (orders,
customers, products, refund policy) with no re-domaining cost, and the team chose to make
**user experience** the differentiator rather than cause impact. The pitch becomes
*"the least frustrating support call you've ever been on"* rather than a humanitarian story.

**Known trade-off, stated openly:** e-commerce refunds is the weakest impact narrative of
all options examined. The compensating strength must be UX depth and the guardrail engine.

### D3. Reuse ShopWave — keep the engine

**Decision:** retain ShopWave's policy/audit/tool substrate; build the entire real-time
conversational layer new.

**What ShopWave contributes:**
- Policy engine (return windows, tier overrides, value thresholds)
- Idempotency checks (no duplicate refunds)
- Fraud / social-engineering detection
- Structured escalation payloads
- Forensic audit logging
- Tool set: `get_order`, `get_customer`, `get_product`, `check_refund_eligibility`,
  `issue_refund`, `send_reply`, `search_knowledge_base`, `escalate`
- Rule engine (O(1) keyword classification) + LLM fallback — this is what makes broad
  intent coverage cheap

**What ShopWave does NOT contribute** — roughly 7 of PS5's 10 requirements are new work:
multilingual/code-switched speech, interruption handling, noise resilience, the
confirmation ladder, low-confidence detection, prioritized question flow, real-time
turn-taking. ShopWave is batch, text and asynchronous. PS5 is real-time, voice and
conversational.

**Alternatives rejected:**
- *Ship ShopWave with a voice front-end* — this is precisely the "only a voice-enabled
  chatbot" disqualifier. Rejected.
- *Start completely fresh* — throws away the one thing that is genuinely hard to fake in
  six days (a real enforcement layer rather than a system prompt).

**Open risk:** see R2 in [04-risks-and-open-questions.md](04-risks-and-open-questions.md) —
organiser confirmation needed that building on your own prior repo is acceptable under the
"copied without significant modification" rule.

### D4. Surfaces: build all three

**Decision:** caller voice experience + human agent console + live transparency panel.

The transparency panel is the highest-leverage surface. Low-confidence detection, policy
enforcement and audit trails are invisible in a voice-only demo — the panel converts them
into something the judges watch happen in real time, and therefore something scoreable.

### D5. Warm escalation — the AI stays in the room

**Decision:** escalation is an *addition*, not a transfer. The human agent joins the same
Agora channel; the AI remains as interpreter and copilot.

This is the single design move that makes Agora structurally necessary rather than
decorative. Three parties in one continuous audio room with live interpretation between two
humans who don't share a language is not achievable on a phone-tree stack. It also converts
PS5's requirement 8 ("human escalation with context preservation") from a checkbox into the
most impressive moment in the demo.

Implementation: Agora's *update agent configuration* REST endpoint switches the agent to
interpreter mode live, mid-call.

### D6. Languages: whatever Gemini Live covers

**Decision:** rely on Gemini Live's native multilingual speech-to-speech (70+ languages for
voice-to-voice) rather than picking a fixed language pair.

Demo centrepiece should still be **Hindi/English code-switching** — it is the most realistic
code-switching in the world and a Delhi jury can personally verify it works. Other languages
become the "and it generalises" claim.

### D7. Transport: MLLM primary, cascade fallback, brain transport-agnostic

**Decision:** ShopWave Core exposes one internal decision API. Two thin adapters sit in
front of it.

| Path | Config | Pros | Cons |
|---|---|---|---|
| **MLLM (primary)** | `mllm.vendor: "gemini"`, `gemini-3.1-flash-live-preview` | Native speech-to-speech. Far better code-switching, interruption, prosody. Sub-second. | **Function calling undocumented through Agora.** No explicit ASR confidence score. |
| **Cascade (fallback)** | `asr` → `llm.vendor: "custom"` → `tts` | Function calling fully documented. `turn_id` metadata. Total control. ShopWave *is* the LLM. | Serial latency. Less natural prosody. Mid-sentence Hinglish is hard for chained ASR. |

Ship MLLM if the tool-calling test passes; cascade if it doesn't. ~200 lines of adapter as
insurance against the one unknown that could sink the build. See R1.

### D8. Breadth vs depth in case coverage

**Decision:** wide *routing* surface, deep *resolution* on a chosen set. Three tiers —
5 hero flows, 9 lighter flows, 9 recognised-and-routed. Cross-cutting conversational
behaviours are prioritised over intent count.

Rationale: a team demoing thirty shallow intents loses to a team demoing five flows that
survive interruption, correction, topic-switching and code-switching.

**Cut list if behind schedule:** drop Tier 2 bottom-up (invoice → subscription → promo code
→ warranty). **Never cut a cross-cutting behaviour to save an intent.**

### D9. Stack: FastAPI, not Flask

**Decision:** port ShopWave's Flask dashboard to FastAPI.

Needed for async and WebSockets. ShopWave's own "future improvements" already called for
moving off AJAX polling. Pydantic models carry over unchanged.

---

### D10. Cascade webhook: bake the session id into the URL, don't guess Agora's payload

**Decision:** the OpenAI-compatible endpoint Agora's cascade agent calls is
`/agora/llm/{channel}/v1/chat/completions`, with the Agora channel name as the path
segment — not inferred from the request body.

Agora's exact `llm.vendor: "custom"` request shape is unverified (same root uncertainty
as R1). Rather than guess whether a session identifier arrives in the body, a header, or
the `user` field, `/calls/start` builds a per-channel `PUBLIC_BASE_URL/agora/llm/{channel}`
and hands that URL to Agora as `llm.url` when the call starts. Agora only needs to be able
to POST to a URL; it never needs to identify itself, because the URL already does.

### D11. Text-chat demo path as a first-class deliverable, not a fallback

**Decision:** `app/main.py` serves a full text-chat UI + live transparency panel at `/`,
independent of any Agora call, hitting the same `app/core/orchestrator.py` loop the cascade
webhook uses.

The runbook requires a publicly reachable, non-localhost deployment before the 4 Sep
deadline. Voice requires a browser mic and a live Agora session — both hard to guarantee
for every judge doing an unattended review. The text path exercises the actual brain
(intent classification, the confirmation ladder, policy adjudication, escalation, the full
audit trail) with nothing but a browser tab, so the core IP is inspectable by anyone with
the URL, voice or not.

### D12. `/call` — one page, two roles, no separate console

**Decision:** the real-time voice client at `/call` lets the same page act as either the
caller or the human agent, picked by a role selector, rather than building a separate
console application.

The demo script needs a caller and a console operator on different screens; it doesn't need
different *code*. A human agent picking "Human agent" and entering the channel name joins
the same Agora RTC channel with a different uid and immediately calls the escalation
endpoint — same backend path a real console would use. One deployable artifact instead of
two, for a hackathon timeline where every extra surface is a UI to test.

### D13. Human override is a distinct method, not a flag on `propose_action`

**Decision:** `CallSession.human_override()` is a new method, not `propose_action(action,
override=True)`.

`propose_action` is the model's only path to acting, and it's exercised by every existing
test and by the orchestrator's tool loop — the model calls it, unmediated. Threading an
override flag through that same method risks the model ever supplying `override=True`
itself if a caller ever exposed it, which would defeat the entire point of enforcing policy
in code rather than in a prompt. A separate method with its own `human_present` gate can
only be reached from `POST /calls/{channel}/approve`, which nothing but a human clicking
"Approve" in `/call` ever calls. Slot-backing (`_unbacked_args`) still applies unconditionally
— a human approving an action never grants permission to act on a value the caller didn't
confirm.

---

## Running log

| Date | Session outcome |
|---|---|
| 9 Aug 2026 | PS5 selected, e-commerce domain locked, ShopWave reuse strategy set, concept + architecture + coverage map approved. Doc set created. |
| 1 Sep 2026 | Organisers confirmed the ShopWave reuse rule (R2) is acceptable — resolved, see [docs/04-risks-and-open-questions.md](04-risks-and-open-questions.md). Built the missing service layer end to end: FastAPI app (`app/main.py`), cascade LLM orchestrator (`app/core/orchestrator.py`, D10/D11), Docker image, 10 new tests (69 total, all passing with zero credentials configured). Published the repo publicly at [github.com/coder-irwin/echosphere-ps5-voice-support](https://github.com/coder-irwin/echosphere-ps5-voice-support), added Vedansh (theDeviser) as a collaborator. Stood up a dedicated GCP project (`echosphere-ps5-hackathon`) and deployed to Cloud Run — live at the URL in the README. Real Agora/Gemini credentials still pending from the team; R1 (MLLM tool-calling) remains unverified until they're wired in, cascade mode is the deployed default in the meantime. |
| 4 Sep 2026 | Built the real-time voice call browser client at `/call` (D12) — Agora Web SDK, caller and human-agent roles both joinable from the same page, wired to the actual escalation/interpreter-mode endpoints. While preparing against the demo script (docs/07-demo-script.md) found that the script's 3:30 beat — "operator approves in the console, `issue_refund` executes" — had **no corresponding code path**: `human_present` didn't grant any override of a policy block. Added `CallSession.human_override` (D13) and `POST /calls/{channel}/approve` to close that gap; still fully enforces slot-backing, only bypasses the policy block, and only when a human has actually joined. 76 tests passing. Vedansh's collaborator invite accepted. Still blocked on real Agora/Gemini credentials. |
