# Deployment

How this runs — locally, in Docker, and in production on GCP Cloud Run. Written so anyone
cloning the repo can go from zero to a running service without asking a teammate anything.

---

## What's actually running

`app/main.py` is the HTTP/WebSocket surface. It exposes:

| Route | What it's for |
|---|---|
| `GET /health` | Liveness + which integrations are configured |
| `GET /` | Text-chat demo UI + live transparency panel — no Agora account needed |
| `POST /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/message` | Drive the brain over text |
| `WS /ws/{id}` | Live audit-event feed for the transparency panel |
| `POST /calls/start`, `POST /calls/{channel}/stop`, `POST /calls/{channel}/escalate` | Control a real Agora Conversational AI Engine call |
| `GET /token` | Agora RTC token for a browser client to join a channel |
| `POST /agora/llm/{channel}/v1/chat/completions` | OpenAI-compatible webhook — this is what Agora's cascade agent calls when `AGENT_MODE=cascade`. The channel name is baked into the URL at call-start time, so there's no ambiguity about which session a request belongs to (Agora's exact custom-LLM payload shape is otherwise unverified — see [R1](04-risks-and-open-questions.md)) |
| `POST /admin/reset` | Restores demo data, drops all sessions — what `make demo-reset` calls |

The service is designed to **degrade, not fail**, when secrets are missing: `/health`
reports `agora_configured`/`gemini_configured` as `false`, and `/sessions/{id}/message`
returns a plain-language "not configured yet" reply instead of a 500. That's why it's
demoable today even before `GEMINI_API_KEY` exists.

---

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in what you have; empty is fine to start
uvicorn app.main:app --reload --port 8080
```

Visit `http://localhost:8080` for the chat demo, or `http://localhost:8080/health`.

```bash
pytest -q   # 69 tests, no credentials required
```

## Run it in Docker

```bash
make docker-build
make docker-run   # reads .env
```

## Production — GCP Cloud Run

**Project:** `echosphere-ps5-hackathon` — a dedicated GCP project, kept separate from any
other project on the account so hackathon usage/billing/cleanup never mixes with anything
else.

**Service:** `shopwave-ps5`, region `asia-south1`, deployed straight from source (Cloud
Build reads the repo's `Dockerfile`, builds, pushes to Artifact Registry, deploys to Cloud
Run — no manual image management).

```bash
gcloud config set project echosphere-ps5-hackathon

gcloud run deploy shopwave-ps5 \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars AGENT_MODE=cascade
```

After the first deploy, `PUBLIC_BASE_URL` must point at the service's own URL (the cascade
webhook needs to hand Agora a URL back to itself):

```bash
gcloud run services update shopwave-ps5 --region asia-south1 \
  --set-env-vars PUBLIC_BASE_URL=https://<service-url>,AGENT_MODE=cascade
```

### Secrets

Real credentials (`AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `AGORA_CUSTOMER_KEY`,
`AGORA_CUSTOMER_SECRET`, `GEMINI_API_KEY`) go into **Secret Manager**, never into
`--set-env-vars` (those are visible in plaintext via `gcloud run services describe`) and
never into the repo:

```bash
printf '%s' "$AGORA_APP_ID" | gcloud secrets create agora-app-id --data-file=-
printf '%s' "$AGORA_APP_CERTIFICATE" | gcloud secrets create agora-app-certificate --data-file=-
printf '%s' "$AGORA_CUSTOMER_KEY" | gcloud secrets create agora-customer-key --data-file=-
printf '%s' "$AGORA_CUSTOMER_SECRET" | gcloud secrets create agora-customer-secret --data-file=-
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-

gcloud run services update shopwave-ps5 --region asia-south1 \
  --set-secrets AGORA_APP_ID=agora-app-id:latest,\
AGORA_APP_CERTIFICATE=agora-app-certificate:latest,\
AGORA_CUSTOMER_KEY=agora-customer-key:latest,\
AGORA_CUSTOMER_SECRET=agora-customer-secret:latest,\
GEMINI_API_KEY=gemini-api-key:latest
```

If a secret's value ever changes, add a new version (`gcloud secrets versions add <name>
--data-file=-`) rather than editing in place — Cloud Run picks up `:latest` on the next
revision.

### Redeploying

Any push to `main` does **not** auto-deploy (no CI/CD wired up — see known limitations).
Redeploy manually with the same `gcloud run deploy --source .` command above; it rebuilds
from the current working tree.

### Demo-day reset

```bash
BASE_URL=https://<service-url> make demo-reset
```

Restores `ORD-4471` and the rest of the demo data to clean state and drops all in-memory
sessions. Per [docs/08-runbook.md](08-runbook.md), forgetting this before a live demo is
the single most common failure — it's a one-liner for a reason.

---

## Known limitations

- CI runs the test suite on every push/PR (`.github/workflows/tests.yml`), but there's no
  CD — deploys stay manual (`gcloud run deploy --source .`).
- No auth on the service — `--allow-unauthenticated` is intentional for a hackathon demo
  that judges need to reach without credentials, but it means `/admin/reset` and the
  `/calls/*` control endpoints are open to anyone with the URL. Fine for a demo window;
  not production-grade beyond that.
- Sessions and the demo data store are in-process memory — a Cloud Run cold start or scale
  event drops them. Cloud Run is configured to allow scale-to-zero, which trades cost for
  the possibility of losing an in-flight demo session if the instance recycles mid-call;
  acceptable for the hackathon's traffic pattern, worth revisiting for real production use.
- MLLM-mode tool calling (R1) is still unverified against the live Agora API — cascade mode
  is the default until that spike happens.
