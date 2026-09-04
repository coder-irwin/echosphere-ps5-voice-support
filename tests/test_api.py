from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_config_state():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "agora_configured" in body
    assert "gemini_configured" in body


def test_session_lifecycle_and_message():
    created = client.post("/sessions").json()
    session_id = created["session_id"]
    assert created["snapshot"]["session_id"] == session_id

    fetched = client.get(f"/sessions/{session_id}").json()
    assert fetched["session_id"] == session_id

    reply = client.post(f"/sessions/{session_id}/message", json={"text": "hello"})
    assert reply.status_code == 200
    assert "spoken" in reply.json()


def test_unknown_session_is_404():
    assert client.get("/sessions/does-not-exist").status_code == 404
    assert client.post("/sessions/does-not-exist/message", json={"text": "hi"}).status_code == 404


def test_demo_ui_serves_html():
    res = client.get("/")
    assert res.status_code == 200
    assert "ShopWave" in res.text


def test_call_ui_serves_html_with_agora_sdk():
    res = client.get("/call")
    assert res.status_code == 200
    assert "AgoraRTC" in res.text
    assert "agora-rtc-sdk-ng" in res.text


def test_calls_start_without_agora_configured_reports_not_configured():
    res = client.post("/calls/start", json={"channel": "test-channel-1"})
    assert res.status_code == 200
    data = res.json()
    assert data["agora"]["ok"] is False
    assert data["agora"]["error"] == "agora_not_configured"


def test_approve_on_unknown_channel_is_404():
    res = client.post(
        "/calls/no-such-channel/approve",
        json={"tool": "issue_refund", "args": {"order_id": "ORD-4471", "amount": 100}},
    )
    assert res.status_code == 404


def test_approve_without_human_present_is_refused():
    client.post("/calls/start", json={"channel": "test-channel-approve"})
    res = client.post(
        "/calls/test-channel-approve/approve",
        json={"tool": "issue_refund", "args": {"order_id": "ORD-4471", "amount": 18400}},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["outcome"]["executed"] is False
    assert data["outcome"]["policy"]["rule"] == "override_requires_human_present"


def test_token_endpoint_without_agora_configured():
    res = client.get("/token", params={"channel": "demo", "uid": 0})
    assert res.status_code == 200
    assert res.json()["channel"] == "demo"
