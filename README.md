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
| Core brain (policy, slots, guardrails, escalation, audit) | Done — 69 tests passing |
| HTTP/WebSocket service layer + cascade LLM orchestrator | Done — [docs/09-deployment.md](docs/09-deployment.md) |
| Public repo, Docker, live deployment | Done — see **Live demo** below |
| Real-time voice call browser client ([/call](https://shopwave-ps5-855952895014.asia-south1.run.app/call)) | Done — caller + human-agent roles, escalation, human-approved override |
| Real Agora/Gemini credentials wired in | Done — Agora agent joins and runs live end-to-end; blocked only on Gemini API billing credits (see R8) |

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

- **Voice hasn't been demoed with a real spoken reply yet.** Agora credentials are live —
  `POST /calls/start` returns a real, `RUNNING` Conversational AI agent — but the Gemini API
  key backing the cascade LLM has no usable model without prepay billing credits (R8). Add
  credits at https://ai.studio/projects and no further code change is needed.
- **MLLM tool-calling (R1) is unverified** against the live Agora API; cascade mode is the
  deployed default and doesn't need it.
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
