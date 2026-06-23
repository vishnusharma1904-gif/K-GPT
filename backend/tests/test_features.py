"""API-level tests for the new phase routers (in-memory DB harness)."""


def _signup(client, email="a1234@ksrmce.ac.in"):
    r = client.post("/api/auth/signup", json={
        "email": email, "full_name": "Test Student", "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- P37 tools / P36 sandbox -------------------------------------------------
def test_tools_list_requires_auth(client):
    assert client.get("/api/tools").status_code == 401


def test_tools_run(client):
    tok = _signup(client)
    r = client.post("/api/tools/run", headers=_auth(tok),
                    json={"name": "calculator", "args": {"expression": "6*7"}})
    assert r.status_code == 200 and "42" in r.json()["result"]


def test_tools_execute_sandbox(client):
    tok = _signup(client)
    r = client.post("/api/tools/execute", headers=_auth(tok),
                    json={"code": "print('hi from sandbox')"})
    assert r.status_code == 200
    assert "hi from sandbox" in r.json()["stdout"]


# --- P24 prompts ------------------------------------------------------------
def test_prompts_list_includes_starters(client):
    tok = _signup(client)
    r = client.get("/api/prompts", headers=_auth(tok))
    assert r.status_code == 200
    assert any(p["slug"] == "/essay" for p in r.json())


# --- P50 feedback / NPS -----------------------------------------------------
def test_feedback_submit_and_nps_admin_only(client):
    tok = _signup(client)
    assert client.post("/api/feedback", headers=_auth(tok),
                       json={"kind": "nps", "score": 9}).status_code == 200
    # students cannot read the NPS report
    assert client.get("/api/feedback/nps", headers=_auth(tok)).status_code == 403


# --- P47 public status ------------------------------------------------------
def test_public_status_open(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["status"] in ("operational", "degraded", "outage")


# --- P3 google config -------------------------------------------------------
def test_google_config_public(client):
    r = client.get("/api/auth/google/config")
    assert r.status_code == 200
    assert "enabled" in r.json()


# --- P26 branch -------------------------------------------------------------
def test_branch_session(client):
    tok = _signup(client)
    s = client.post("/api/chat/sessions", headers=_auth(tok),
                    json={"title": "orig", "persona": "kgpt"}).json()
    r = client.post(f"/api/chat/sessions/{s['id']}/branch", headers=_auth(tok),
                    json={"title": "alt path"})
    assert r.status_code == 200 and r.json()["id"] != s["id"]
