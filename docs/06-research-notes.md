# Research notes

Verified external facts with sources. Everything here was checked against primary
documentation or reporting — do not cite anything in a pitch that isn't in this file.

Last verified: **9 Aug 2026**

---

## Agora Conversational AI Engine

### Multiple agents and multi-user subscription

`remote_rtc_uids: ["*"]` subscribes the agent to **all UIDs present in the channel**,
including other AI agents. Multiple AI agents can run in the same channel.

Caveats from the docs:
- If multiple agents are active in one channel with `["*"]`, they detect each other's
  presence and the `idle_timeout` condition (all other users have left) may never trigger.
  Review `idle_timeout` best practice to avoid unnecessary cost.
- When using an AI Avatar, subscribing to all users with `["*"]` is **not supported**.

*Note:* one docs page states "currently, only one user ID is supported" for
`remote_rtc_uids`. This appears stale — the wildcard is documented elsewhere and in the
release notes. **Verify empirically before relying on it.**

Sources:
[Release notes](https://docs.agora.io/en/conversational-ai/overview/release-notes) ·
[Start an agent](https://docs.agora.io/en/conversational-ai/rest-api/agent/join)

### Custom LLM (cascade path)

Requires an HTTP service compatible with the **OpenAI API format**. Supports RAG,
multimodal text/audio output, tool invocation, and **function calling**.

When `llm.vendor` is `"custom"`, the agent includes extra metadata in requests to your
endpoint beyond `role` and `content` — notably **`turn_id`** (unique identifier per
conversation turn) and `timestamp`.

Reference implementation: an Express.js microservice supporting streaming and non-streaming
responses, function calling, and RAG.

Sources:
[Custom LLM](https://docs.agora.io/en/conversational-ai/develop/custom-llm) ·
[Connect your own LLM service](https://docs.agora.io/en/ai/build/custom-model-integration/custom-llm) ·
[agora-convo-ai-custom-llm-express](https://github.com/AgoraIO-Community/agora-convo-ai-custom-llm-express)

### Gemini Live (MLLM path)

Agora supports Google Gemini Live as an MLLM vendor — multimodal LLM with real-time audio,
enabling natural voice conversations **without separate ASR/TTS components**.

- `"vendor": "gemini"`, `"model": "gemini-3.1-flash-live-preview"`
- `"instructions"`, `"voice"` (e.g. `"Charon"`)
- `"input_modalities": ["audio"]`, `"output_modalities": ["audio"]`
- `"transcribe_agent"`, `"transcribe_user"` flags
- `turn_detection` may be set **inside** the `mllm` object; when `mllm.turn_detection` is
  defined, the top-level `turn_detection` has no effect
- `agora_vad` is compatible with both cascade and MLLM modes

**Enabling MLLM automatically disables ASR, LLM and TTS** — the MLLM handles end-to-end voice
processing directly.

Gemini Live API offers real-time voice-to-voice translation in **70+ languages**.

**⚠️ Unverified:** Agora's Gemini Live documentation does **not** mention function calling or
tool declarations. Gemini Live supports tools natively; whether Agora passes them through is
unknown. See R1 in [04-risks-and-open-questions.md](04-risks-and-open-questions.md).

Sources:
[Gemini Live](https://docs.agora.io/en/conversational-ai/models/mllm/gemini) ·
[Gemini Live (Vertex AI)](https://docs.agora.io/en/conversational-ai/models/mllm/google-vertex-ai) ·
[Agora blog — Gemini 3.1 Flash Preview](https://www.agora.io/en/blog/build-a-live-ai-voice-agent-with-gemini-3-1-flash-preview-and-agora/) ·
[Gemini Live API overview](https://ai.google.dev/gemini-api/docs/live-api)

### ASR vendors (cascade path only)

| Vendor | Language coverage |
|---|---|
| Agora (ARES) | 36 languages |
| Microsoft Azure | 100+ languages |
| Deepgram | 50+ languages |

Keyword-recognition capability, including multi-language and dialect support, depends on the
chosen ASR provider.

### Interruption

The engine supports agent interruption via **voice interruption** — it detects user voice
input and automatically stops the agent's response. Keyword-based interruption is available
when `turn_detection.interrupt_mode` is set to `"keyword"`.

Source: [Interrupt the agent](https://docs.agora.io/en/conversational-ai/develop/interrupt-agent)

### Agent configuration update

A REST endpoint exists to update agent configuration.
Source: [Update agent configuration](https://docs.agora.io/en/conversational-ai/rest-api/agent/update)

**Unverified:** whether config update works mid-call in MLLM mode. Needed for the
interpreter-mode switch on escalation.

---

## Market and impact context

Collected while exploring domains. Retained because parts are still usable in the pitch's
problem framing even though we settled on e-commerce.

### Language access — the core problem framing

- Global illiterate adults: **754 million (2023) → 739 million (2024)**. Women are nearly
  two-thirds — **466 million**.
- UNESCO frames it as a **"double exclusion"**: people without digital skills and literacy are
  excluded both from full participation in the real world and from digital opportunity.
- India has 22 official languages and hundreds of dialects. Growth increasingly comes from
  Tier-2 and Tier-3 cities, where people are digitally active but engage most naturally in
  regional languages and by voice.
- **The language gap is invisible in the data** — it shows up as unexplained drop-off, not as
  "customer left because we didn't speak their language."
- Long, complex IVR menus produce high call abandonment, especially where technical literacy
  is lower.
- India's BPO industry faces **30–50% annual attrition**.

Sources:
[UNESCO literacy](https://www.unesco.org/en/literacy) ·
[UNESCO digital inclusion guidelines](https://en.unesco.org/news/unesco-launches-guidelines-inclusive-digital-solutions-people-low-skills-and-low-literacy) ·
[Vernacular voice AI in India](https://chatmaxima.com/blog/vernacular-voice-ai-india/) ·
[IVR challenges in India](https://kommuno.in/the-challenges-of-implementing-an-ivr-system-in-india-and-how-to-overcome-them/)

### Displacement (explored, not used)

- **117.8 million** forcibly displaced worldwide as of December 2025.
- UNHCR operated with **24% less funding** than 2024 and assisted 30.7 million people — 16%
  fewer than the previous year.
- Workforce down by **more than one third — 6,600 positions — by January 2026**.

Sources:
[UNHCR figures at a glance](https://www.unhcr.org/us/about-unhcr/overview/figures-glance) ·
[UNHCR Global Appeal 2026](https://www.unhcr.org/publications/global-appeal-2026)

### Indian helplines (explored, not used)

- Haryana's **1930** cybercrime helpline: **7.25 lakh calls in 2024**, up from 1.45 lakh in
  2022 — roughly 300–350 calls/day in one state.
- **Kisan Call Centre** (1800-180-1551): replies in **22 local languages**, 25 centres
  covering all states/UTs, operating 06:00–22:00 daily — i.e. **no overnight coverage**.

Sources:
[Tribune — Haryana cybercrime volumes](https://www.tribuneindia.com/news/haryana/cybercrime-complaints-in-haryana-double-in-two-years-public-awareness-surges/amp) ·
[mKisan — about KCC](https://mkisan.gov.in/Alpha/aboutkcc.aspx)

---

## ShopWave baseline metrics (from the prior repo's README)

Measured on 20 simulated tickets running concurrently under asyncio. **These are batch text
metrics — they do not transfer to real-time voice and should not be presented as if they do.**

| Metric | Result |
|---|---|
| Operational completion | 20/20 (zero DLQ) |
| Refund precision | 100% |
| Unsafe actions blocked | 6 |
| Concurrency speedup | ~7.5x |
| Average resolve time | < 4.8s |

Existing tools: `get_order`, `get_customer`, `get_product`, `check_refund_eligibility`,
`issue_refund`, `send_reply`, `search_knowledge_base`, `escalate`.

Repo: `github.com/coder-irwin/hackathon2026-akaash-tripathee`
