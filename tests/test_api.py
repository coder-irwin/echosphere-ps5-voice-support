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


def test_token_endpoint_without_agora_configured():
    res = client.get("/token", params={"channel": "demo", "uid": 0})
    assert res.status_code == 200
    assert res.json()["channel"] == "demo"
