"""HTTP/WebSocket surface. Everything a transport (Agora, a browser, curl) talks to.

Two independent ways to drive the same brain, per the architecture (docs/02):

  demo chat   POST /sessions, POST /sessions/{id}/message   — text in, spoken text out.
              No Agora account needed; this is what a judge sees on the public URL.
  cascade     POST /agora/llm/{channel}/v1/chat/completions  — Agora's `llm.vendor: "custom"`
              calls this. Session id == Agora channel name, baked into the URL when the
              call starts, so no guessing about what Agora's payload identifies a call with.

`/calls/*` drives the real Agora Conversational AI Engine (join/leave/escalate) once
AGORA_APP_ID / AGORA_CUSTOMER_KEY / AGORA_CUSTOMER_SECRET / GEMINI_API_KEY are configured.
Without them, `AgoraConvoAI` returns a clear `agora_not_configured` error instead of raising,
so the service stays healthy and demoable before those secrets exist.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.adapters.agora import AgoraConfig, AgoraConvoAI, build_rtc_token
from app.adapters.llm import GeminiClient
from app.api.state import registry
from app.core.orchestrator import run_turn
from app.core.session import DISCLOSURE
from app.factory import get_store

app = FastAPI(title="EchoSphere PS5 — ShopWave Voice Support", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _public_base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


# --------------------------------------------------------------------------- health


@app.get("/health")
async def health() -> dict[str, Any]:
    agora_cfg = AgoraConfig.from_env()
    gemini = GeminiClient()
    return {
        "status": "ok",
        "agora_configured": agora_cfg.configured,
        "gemini_configured": gemini.configured,
        "active_sessions": len(registry.all()),
    }


# ---------------------------------------------------------------------- text demo


class MessageIn(BaseModel):
    text: str


@app.post("/sessions")
async def create_session() -> dict[str, Any]:
    session = registry.create()
    return {"session_id": session.session_id, "snapshot": session.snapshot()}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = registry.get(session_id)
    if session is None:
        raise HTTPException(404, "unknown session")
    return session.snapshot()


@app.post("/sessions/{session_id}/message")
async def post_message(session_id: str, body: MessageIn) -> dict[str, Any]:
    session = registry.get(session_id)
    if session is None:
        raise HTTPException(404, "unknown session")
    return await run_turn(session, body.text)


# --------------------------------------------------------------------- panel feed


@app.websocket("/ws/{session_id}")
async def panel_ws(websocket: WebSocket, session_id: str) -> None:
    session = registry.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    await websocket.send_json({"type": "snapshot", "snapshot": session.snapshot()})
    registry.hub.attach(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # panel is read-only; drain pings
    except WebSocketDisconnect:
        pass
    finally:
        registry.hub.detach(session_id, websocket)


# ------------------------------------------------------------------- live Agora calls


class CallStartIn(BaseModel):
    channel: str
    mode: Optional[str] = None  # "mllm" | "cascade" — defaults to AGENT_MODE env


@app.post("/calls/start")
async def start_call(body: CallStartIn) -> dict[str, Any]:
    session = registry.get(body.channel) or registry.create(body.channel)

    cfg = AgoraConfig.from_env()
    if body.mode:
        cfg = dataclasses.replace(cfg, mode=body.mode)
    if cfg.mode == "cascade":
        base = _public_base_url()
        cfg = dataclasses.replace(cfg, llm_base_url=f"{base}/agora/llm/{body.channel}")

    convo = AgoraConvoAI(cfg)
    result = await convo.start_agent(body.channel)
    if result.get("ok") and result.get("agent_id"):
        registry.bind_agent(body.channel, result["agent_id"])

    return {
        "session_id": session.session_id,
        "disclosure": DISCLOSURE,
        "agora": result,
        "join": {
            "app_id": cfg.app_id,
            "channel": body.channel,
            "token": build_rtc_token(cfg, body.channel, uid=0),
        },
    }


@app.post("/calls/{channel}/stop")
async def stop_call(channel: str) -> dict[str, Any]:
    agent_id = registry.agent_for(channel)
    result: dict[str, Any] = {"ok": True, "note": "no agent bound"}
    if agent_id:
        result = await AgoraConvoAI().stop_agent(agent_id)
    registry.close(channel)
    return result


@app.post("/calls/{channel}/escalate")
async def escalate_call(channel: str, agent_name: str = "human agent") -> dict[str, Any]:
    session = registry.get(channel)
    if session is None:
        raise HTTPException(404, "unknown session")
    brief = session.human_joined(agent_name)

    agent_id = registry.agent_for(channel)
    agora_result: dict[str, Any] = {"ok": True, "note": "no agent bound"}
    if agent_id:
        from app.adapters.prompts import interpreter_instruction

        instruction = interpreter_instruction(session.language.current)
        agora_result = await AgoraConvoAI().update_agent(agent_id, instruction)

    return {"brief": brief, "agora": agora_result, "snapshot": session.snapshot()}


@app.get("/token")
async def issue_token(channel: str, uid: int = 0) -> dict[str, Any]:
    cfg = AgoraConfig.from_env()
    return {"app_id": cfg.app_id, "channel": channel, "token": build_rtc_token(cfg, channel, uid)}


# -------------------------------------------------------------- Agora cascade webhook


@app.post("/agora/llm/{channel}/v1/chat/completions")
async def cascade_completions(channel: str, request: Request) -> JSONResponse:
    """OpenAI-compatible endpoint. `llm.vendor: "custom"` in cascade mode points here.

    Session id is the Agora channel name, baked into the URL at `/calls/start` time — see
    that endpoint's docstring-equivalent comment above for why.
    """
    body = await request.json()
    messages = body.get("messages") or []
    user_text = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
    )

    session = registry.get(channel) or registry.create(channel)
    outcome = await run_turn(session, user_text)

    return JSONResponse(
        {
            "id": f"chatcmpl-{session.session_id}",
            "object": "chat.completion",
            "model": body.get("model", "shopwave-core"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": outcome["spoken"]},
                    "finish_reason": "stop",
                }
            ],
        }
    )


# --------------------------------------------------------------------------- demo UI

_DEMO_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>EchoSphere PS5 — ShopWave Voice Support</title>
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; background: #0b0d12; color: #e6e8ee; }
  header { padding: 16px 24px; border-bottom: 1px solid #1e222b; }
  header h1 { font-size: 16px; margin: 0; }
  header p { margin: 4px 0 0; color: #8b91a0; font-size: 13px; }
  main { display: grid; grid-template-columns: 1fr 1fr; gap: 0; height: calc(100vh - 65px); }
  section { padding: 16px; overflow-y: auto; }
  #chat { border-right: 1px solid #1e222b; display: flex; flex-direction: column; }
  #log { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
  .msg { padding: 8px 12px; border-radius: 10px; max-width: 80%; font-size: 14px; line-height: 1.4; }
  .caller { align-self: flex-end; background: #2b5fff; color: white; }
  .agent { align-self: flex-start; background: #1a1e27; }
  form { display: flex; gap: 8px; margin-top: 12px; }
  input { flex: 1; padding: 10px 12px; border-radius: 8px; border: 1px solid #2a2f3a; background: #14171f; color: #e6e8ee; }
  button { padding: 10px 16px; border-radius: 8px; border: none; background: #2b5fff; color: white; cursor: pointer; }
  pre { background: #0f1218; border: 1px solid #1e222b; border-radius: 8px; padding: 12px; font-size: 12px; white-space: pre-wrap; word-break: break-word; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: #8b91a0; }
</style>
</head>
<body>
<header>
  <h1>ShopWave Voice Support — text demo</h1>
  <p>PS5 · EchoSphere Agora Conversational AI Hackathon. This chat drives the real policy-adjudicated brain — no Agora call needed to see it work.</p>
</header>
<main>
  <section id="chat">
    <h2>Conversation</h2>
    <div id="log"></div>
    <form id="form"><input id="input" autocomplete="off" placeholder="e.g. my blender arrived damaged" /><button>Send</button></form>
  </section>
  <section>
    <h2>Transparency panel (live audit state)</h2>
    <pre id="panel">connecting…</pre>
  </section>
</main>
<script>
let sessionId = null, ws = null;
const log = document.getElementById('log');
const panel = document.getElementById('panel');

function addMsg(text, cls) {
  const el = document.createElement('div');
  el.className = 'msg ' + cls;
  el.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
}

async function boot() {
  const res = await fetch('/sessions', { method: 'POST' });
  const data = await res.json();
  sessionId = data.session_id;
  panel.textContent = JSON.stringify(data.snapshot, null, 2);
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/${sessionId}`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.snapshot) panel.textContent = JSON.stringify(msg.snapshot, null, 2);
  };
}

document.getElementById('form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text || !sessionId) return;
  input.value = '';
  addMsg(text, 'caller');
  const res = await fetch(`/sessions/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  const data = await res.json();
  addMsg(data.spoken, 'agent');
  panel.textContent = JSON.stringify(data.snapshot, null, 2);
});

boot();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def demo_ui() -> str:
    return _DEMO_HTML


# ----------------------------------------------------------------------------- admin


@app.post("/admin/reset")
async def admin_reset() -> dict[str, Any]:
    """Restores demo data and drops all sessions. See docs/08-runbook.md — `make demo-reset`."""
    get_store().reset()
    for existing in list(registry.all()):
        registry.drop(existing.session_id)
    return {"ok": True}
