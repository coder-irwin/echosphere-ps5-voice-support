# EchoSphere 2026 — Multilingual Voice Support Line

**Hackathon:** EchoSphere: Agora Conversational AI Hackathon (Knotic, hybrid, Grand Finale in Delhi)
**Problem statement:** PS5 — Real-time multilingual voice AI for a customer assistance line
**Domain:** E-commerce customer support
**Foundation:** ShopWave Autonomous Resolution Engine (re-domained; policy/audit/tool engine retained)

---

## One-line pitch

A multilingual voice support line where the caller never repeats themselves, never gets
transferred into a void, and never gets told a confident lie.

## Status

| Phase | State |
|---|---|
| Problem statement selected | Done — PS5 |
| Domain selected | Done — e-commerce customer assistance |
| Concept + demo spine | Approved |
| Architecture | Approved |
| Case coverage map | Approved |
| Demo script & eval-day plan | Done — [docs/07-demo-script.md](docs/07-demo-script.md), [docs/08-runbook.md](docs/08-runbook.md) |
| Design spec written | Done — [docs/superpowers/specs/](docs/superpowers/specs/) |
| Core brain (policy, slots, guardrails, escalation, audit) | Done — 79 tests passing |
| HTTP/WebSocket service layer + cascade LLM orchestrator | Done — [docs/09-deployment.md](docs/09-deployment.md) |
| Public repo, Docker, live deployment | Done — see **Live demo** below |
| Real-time voice call browser client ([/call](https://shopwave-ps5-855952895014.asia-south1.run.app/call)) | Done — caller + human-agent roles, escalation, human-approved override |
| Real Agora/Gemini credentials wired in, verified live end-to-end | Done — real conversation, real tool calls, real policy block, confirmed 8 Sep 2026 |

## Live demo

Deployed on GCP Cloud Run: **https://shopwave-ps5-855952895014.asia-south1.run.app**

Open it and start typing — the text-chat UI drives the real policy-adjudicated brain (intent
classification, the confirmation ladder, policy blocks, escalation, full audit trail) live in
the transparency panel, no Agora account required. Voice, over a real Agora channel, comes
online once `AGORA_*` and `GEMINI_API_KEY` are set — see [docs/09-deployment.md](docs/09-deployment.md).

## Document index

| Doc | What it holds |
|---|---|
| [docs/00-hackathon-brief.md](docs/00-hackathon-brief.md) | Rules, timeline, deliverables, disqualifiers, PS5 verbatim. Source of truth. |
| [docs/01-decision-log.md](docs/01-decision-log.md) | Every decision, the alternatives rejected, and why. |
| [docs/02-architecture.md](docs/02-architecture.md) | System architecture, components, data flow, stack. |
| [docs/03-case-coverage.md](docs/03-case-coverage.md) | Intent tiers, cross-cutting behaviours, guardrail catalogue. |
| [docs/04-risks-and-open-questions.md](docs/04-risks-and-open-questions.md) | Ranked risks, unknowns, de-risking actions with owners. |
| [docs/05-judge-qa.md](docs/05-judge-qa.md) | Anticipated judge questions with prepared answers. |
| [docs/06-research-notes.md](docs/06-research-notes.md) | Verified external facts with sources. |
| [docs/07-demo-script.md](docs/07-demo-script.md) | The scripted demo flow. |
| [docs/08-runbook.md](docs/08-runbook.md) | Evaluation-day and finale operational checklist. |
| [docs/09-deployment.md](docs/09-deployment.md) | How to run this locally, in Docker, and how it's deployed on GCP Cloud Run. |
| [docs/superpowers/specs/](docs/superpowers/specs/) | Formal design spec. |

## Technologies used

| Layer | Technology | Status |
|---|---|---|
| Voice transport | Agora RTC + Conversational AI Engine, Agora Web SDK (`agora-rtc-sdk-ng` 4.24.8) | Backend + browser client built ([/call](https://shopwave-ps5-855952895014.asia-south1.run.app/call)); live voice pending real Agora credentials |
| Model — primary | Gemini Live (MLLM, speech-to-speech) | Designed, unverified against the live API (R1) |
| Model — deployed | Gemini `generateContent` (cascade path) | Live, pending `GEMINI_API_KEY` |
| Backend | Python 3.12, FastAPI, Pydantic v2, httpx, WebSockets | Live |
| Frontend | Vanilla HTML/JS (text-chat demo + voice-call client) | Live |
| Tests | pytest, pytest-asyncio, FastAPI TestClient | 76 passing |
| CI | GitHub Actions | Live, runs on every push/PR |
| Infra | Docker, GCP Cloud Run, Artifact Registry, Cloud Build, Secret Manager | Live — see [docs/09-deployment.md](docs/09-deployment.md) |
| Data | In-memory JSON-backed store (orders, customers, products, knowledge base) | Live — simulated, not a real DB |
| Ticketing | Simulated sandbox (`app/tools/ticketing.py`) | Live — real Zendesk/Freshdesk integration not yet built |

## Known limitations

- **Voice hasn't been demoed over a real phone/browser call yet.** The text-chat path
  (`/`) is verified live end-to-end — real intent classification, real tool calls, a real
  policy block — and a real Agora Conversational AI agent joins and runs (`/calls/start`
  returns `RUNNING`) with the same cascade brain behind it. What's untested is a live
  microphone conversation through `/call`, which needs a person on a mic, not more code.
- **MLLM tool-calling (R1) is unverified** against the live Agora API; cascade mode is the
  deployed default and doesn't need it.
- **Model reliability nuance (R9):** in a multi-slot conversation, Gemini has occasionally
  confirmed the wrong field right after confirming another one in the same conversation
  (e.g. re-confirming an order ID instead of a phone number just read back). The slot it
  actually names is always confirmed correctly — this is a prompting nuance to tune, not a
  guardrail failure.
- **No persistent database.** Orders/customers/products are in-memory JSON, reset on
  redeploy or `POST /admin/reset`.
- **No auth on the service.** `--allow-unauthenticated` is deliberate so judges can reach it
  without credentials, but `/admin/reset` and `/calls/*` are open to anyone with the URL.
- **No CI/CD.** Tests run on every push; deploys are still a manual `gcloud run deploy`.
- **Ticketing is simulated**, not a real Zendesk/Freshdesk sandbox.
- **Scale is untested** beyond a handful of concurrent sessions; see
  [docs/05-judge-qa.md](docs/05-judge-qa.md) for the honest list of what we can't yet answer.

## Key dates (2026)

- **25 Aug** — registration closes
- **26–28 Aug** — idea submission & screening
- **29 Aug – 3 Sep** — development sprint (one 1:1 mentorship session)
- **4 Sep, 23:59 IST** — submission deadline
- **5–6 Sep** — online evaluation (live demo; no changes permitted)
- **7 Sep** — finalists announced
- **12 Sep** — offline Grand Finale, Delhi

## Documentation rule

This doc set is updated at the end of **every** working session. See
[docs/01-decision-log.md](docs/01-decision-log.md) for the running log.
