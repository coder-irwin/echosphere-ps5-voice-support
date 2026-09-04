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
from app.core.models import ProposedAction
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


class ApproveIn(BaseModel):
    tool: str
    args: dict[str, Any] = {}
    approved_by: str = "human agent"


@app.post("/calls/{channel}/approve")
async def approve_action(channel: str, body: ApproveIn) -> dict[str, Any]:
    """A human agent approves an action the policy engine blocked. See CallSession.human_override."""
    session = registry.get(channel)
    if session is None:
        raise HTTPException(404, "unknown session")
    outcome = await session.human_override(
        ProposedAction(tool=body.tool, args=body.args, intent=session.intent),
        approved_by=body.approved_by,
    )
    return {"outcome": outcome.model_dump(), "snapshot": session.snapshot()}


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
  header { padding: 16px 24px; border-bottom: 1px solid #1e222b; display: flex; justify-content: space-between; align-items: baseline; }
  header h1 { font-size: 16px; margin: 0; }
  header p { margin: 4px 0 0; color: #8b91a0; font-size: 13px; }
  header a { color: #7ea2ff; font-size: 13px; text-decoration: none; }
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
  <div>
    <h1>ShopWave Voice Support — text demo</h1>
    <p>PS5 · EchoSphere Agora Conversational AI Hackathon. This chat drives the real policy-adjudicated brain — no Agora call needed to see it work.</p>
  </div>
  <a href="/call">live voice call →</a>
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


# ------------------------------------------------------------------- live voice call

_CALL_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>ShopWave Voice Support — live call</title>
<script src="https://cdn.jsdelivr.net/npm/agora-rtc-sdk-ng@4.24.8/AgoraRTC_N-production.js"></script>
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; background: #0b0d12; color: #e6e8ee; }
  header { padding: 16px 24px; border-bottom: 1px solid #1e222b; display: flex; justify-content: space-between; align-items: baseline; }
  header h1 { font-size: 16px; margin: 0; }
  header a { color: #7ea2ff; font-size: 13px; text-decoration: none; }
  main { display: grid; grid-template-columns: 380px 1fr; height: calc(100vh - 57px); }
  section { padding: 20px; overflow-y: auto; }
  #controls { border-right: 1px solid #1e222b; }
  label { display: block; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #8b91a0; margin: 16px 0 6px; }
  input, select { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #2a2f3a; background: #14171f; color: #e6e8ee; box-sizing: border-box; }
  button { width: 100%; padding: 12px; border-radius: 8px; border: none; background: #2b5fff; color: white; cursor: pointer; font-size: 14px; margin-top: 12px; }
  button:disabled { background: #262b36; color: #6b7180; cursor: not-allowed; }
  button.danger { background: #d1495b; }
  button.secondary { background: #1a1e27; border: 1px solid #2a2f3a; }
  #status { margin-top: 16px; padding: 12px; border-radius: 8px; background: #14171f; border: 1px solid #2a2f3a; font-size: 13px; line-height: 1.5; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #6b7180; margin-right: 6px; }
  .dot.live { background: #35d07f; }
  .dot.error { background: #d1495b; }
  #banner { display: none; margin-top: 12px; padding: 10px 12px; border-radius: 8px; background: #3a2a14; border: 1px solid #5a4420; font-size: 13px; color: #f0c674; }
  pre { background: #0f1218; border: 1px solid #1e222b; border-radius: 8px; padding: 12px; font-size: 12px; white-space: pre-wrap; word-break: break-word; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: #8b91a0; margin-top: 0; }
</style>
</head>
<body>
<header>
  <h1>ShopWave Voice Support — live call</h1>
  <a href="/">← text demo</a>
</header>
<main>
  <section id="controls">
    <div id="banner"></div>

    <label>Role</label>
    <select id="role">
      <option value="caller">Caller — start a new call</option>
      <option value="agent">Human agent — join an existing call to escalate</option>
    </select>

    <label>Channel</label>
    <input id="channel" placeholder="auto-generated if blank" />

    <button id="joinBtn">Start call</button>
    <button id="escalateBtn" class="secondary" disabled>Escalate to human</button>
    <button id="endBtn" class="danger" disabled>End call</button>

    <div id="status"><span class="dot"></span>not connected</div>

    <label>Approve a blocked action (human agent)</label>
    <select id="approveTool">
      <option value="issue_refund">issue_refund</option>
      <option value="create_replacement">create_replacement</option>
      <option value="cancel_order">cancel_order</option>
      <option value="update_address">update_address</option>
    </select>
    <input id="approveOrderId" placeholder="order_id, e.g. ORD-4471" style="margin-top: 8px;" />
    <input id="approveAmount" placeholder="amount (for issue_refund), e.g. 18400" style="margin-top: 8px;" />
    <button id="approveBtn" class="secondary" disabled>Approve &amp; execute</button>
  </section>
  <section>
    <h2>Transparency panel (live audit state)</h2>
    <pre id="panel">start a call to connect…</pre>
  </section>
</main>
<script>
let client = null, localTrack = null, ws = null, currentChannel = null;

const $ = (id) => document.getElementById(id);
const statusEl = $('status'), bannerEl = $('banner'), panelEl = $('panel');
const joinBtn = $('joinBtn'), escalateBtn = $('escalateBtn'), endBtn = $('endBtn'), roleSel = $('role');
const approveBtn = $('approveBtn');

function setStatus(text, kind) {
  statusEl.innerHTML = `<span class="dot ${kind || ''}"></span>${text}`;
}
function banner(text) {
  if (!text) { bannerEl.style.display = 'none'; return; }
  bannerEl.textContent = text;
  bannerEl.style.display = 'block';
}
function randomChannel() {
  return 'call-' + Math.random().toString(36).slice(2, 8);
}

function connectPanel(sessionId) {
  if (ws) ws.close();
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/${sessionId}`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.snapshot) panelEl.textContent = JSON.stringify(msg.snapshot, null, 2);
  };
}

async function joinRtc(appId, channel, token, uid) {
  client = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' });
  client.on('user-published', async (user, mediaType) => {
    await client.subscribe(user, mediaType);
    if (mediaType === 'audio') user.audioTrack.play();
  });
  await client.join(appId, channel, token || null, uid);
  localTrack = await AgoraRTC.createMicrophoneAudioTrack();
  await client.publish([localTrack]);
}

async function leaveRtc() {
  if (localTrack) { localTrack.close(); localTrack = null; }
  if (client) { await client.leave(); client = null; }
}

async function startAsCaller() {
  const channel = $('channel').value.trim() || randomChannel();
  $('channel').value = channel;
  setStatus('starting call…');
  const res = await fetch('/calls/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channel }),
  });
  const data = await res.json();

  if (!data.agora || data.agora.ok === false) {
    banner('Voice isn\\'t live yet — Agora credentials haven\\'t been configured on the server. The text demo at / still works fully.');
    setStatus('not connected — Agora not configured', 'error');
    return;
  }
  if (!data.join || !data.join.app_id) {
    banner('Server did not return a valid Agora App ID.');
    setStatus('not connected', 'error');
    return;
  }

  currentChannel = channel;
  connectPanel(channel);
  try {
    await joinRtc(data.join.app_id, data.join.channel, data.join.token, 0);
  } catch (err) {
    banner('Could not join the call: ' + (err && err.message ? err.message : err));
    setStatus('join failed', 'error');
    return;
  }

  setStatus(`live on "${channel}" — mic on, listening for the agent`, 'live');
  joinBtn.disabled = true;
  escalateBtn.disabled = false;
  endBtn.disabled = false;
  approveBtn.disabled = false;
}

async function joinAsAgent() {
  const channel = $('channel').value.trim();
  if (!channel) { banner('Enter the channel name the caller started.'); return; }
  setStatus('joining as human agent…');

  const tokenRes = await fetch(`/token?channel=${encodeURIComponent(channel)}&uid=2`);
  const tokenData = await tokenRes.json();
  if (!tokenData.app_id) {
    banner('Voice isn\\'t live yet — Agora credentials haven\\'t been configured on the server.');
    setStatus('not connected — Agora not configured', 'error');
    return;
  }

  currentChannel = channel;
  connectPanel(channel);
  try {
    await joinRtc(tokenData.app_id, channel, tokenData.token, 2);
  } catch (err) {
    banner('Could not join the call: ' + (err && err.message ? err.message : err));
    setStatus('join failed', 'error');
    return;
  }

  const escRes = await fetch(`/calls/${encodeURIComponent(channel)}/escalate`, { method: 'POST' });
  const escData = await escRes.json();
  banner(escData.brief ? ('Briefed: ' + escData.brief) : null);

  setStatus(`live on "${channel}" as human agent — interpreter mode active`, 'live');
  joinBtn.disabled = true;
  escalateBtn.disabled = true;
  endBtn.disabled = false;
  approveBtn.disabled = false;
}

joinBtn.addEventListener('click', () => {
  banner(null);
  joinBtn.disabled = true;
  (roleSel.value === 'agent' ? joinAsAgent() : startAsCaller()).catch((err) => {
    banner('Unexpected error: ' + err);
    joinBtn.disabled = false;
  });
});

escalateBtn.addEventListener('click', async () => {
  escalateBtn.disabled = true;
  const res = await fetch(`/calls/${encodeURIComponent(currentChannel)}/escalate`, { method: 'POST' });
  const data = await res.json();
  banner(data.brief ? ('Escalated. Briefed: ' + data.brief) : 'Escalated.');
});

approveBtn.addEventListener('click', async () => {
  if (!currentChannel) return;
  const tool = $('approveTool').value;
  const orderId = $('approveOrderId').value.trim();
  const amount = $('approveAmount').value.trim();
  const args = {};
  if (orderId) args.order_id = orderId;
  if (tool === 'issue_refund' && amount) args.amount = parseFloat(amount);
  if (tool === 'update_address') args.new_address = amount || '';

  const res = await fetch(`/calls/${encodeURIComponent(currentChannel)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool, args, approved_by: 'Human agent (console)' }),
  });
  const data = await res.json();
  const outcome = data.outcome || {};
  if (outcome.executed) {
    banner('Approved and executed: ' + JSON.stringify(outcome.result));
  } else {
    banner('Not executed — ' + (outcome.spoken_reason || (outcome.policy && outcome.policy.rule) || 'blocked'));
  }
  if (data.snapshot) panelEl.textContent = JSON.stringify(data.snapshot, null, 2);
});

endBtn.addEventListener('click', async () => {
  endBtn.disabled = true;
  await leaveRtc();
  if (currentChannel) await fetch(`/calls/${encodeURIComponent(currentChannel)}/stop`, { method: 'POST' });
  if (ws) ws.close();
  setStatus('call ended');
  joinBtn.disabled = false;
  escalateBtn.disabled = true;
  approveBtn.disabled = true;
  panelEl.textContent = 'start a call to connect…';
});
</script>
</body>
</html>"""


@app.get("/call", response_class=HTMLResponse)
async def call_ui() -> str:
    return _CALL_HTML


# ----------------------------------------------------------------------------- admin


@app.post("/admin/reset")
async def admin_reset() -> dict[str, Any]:
    """Restores demo data and drops all sessions. See docs/08-runbook.md — `make demo-reset`."""
    get_store().reset()
    for existing in list(registry.all()):
        registry.drop(existing.session_id)
    return {"ok": True}
