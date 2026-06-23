"""Integration tests over the FastAPI app with an in-memory DB (tenant safety,
auth gate, lockout, moderation, preferences, privacy)."""


def _signup(client, email="22091a0501@ksrmce.ac.in", pw="password123"):
    return client.post("/api/auth/signup",
                       json={"email": email, "full_name": "Test Student", "password": pw})


def test_health_ok(client):
    assert client.get("/api/health").status_code == 200


def test_protected_routes_require_auth(client):
    for path in ["/api/account/usage", "/api/chat/sessions", "/api/projects",
                 "/api/account/preferences"]:
        assert client.get(path).status_code == 401, path


def test_college_email_gate(client):
    r = client.post("/api/auth/signup",
                    json={"email": "rando@gmail.com", "full_name": "X", "password": "password123"})
    assert r.status_code == 403


def test_signup_login_flow(client):
    r = _signup(client)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email_verified"] is False   # students start unverified
    assert body["user"]["role"] == "student"
    token = body["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["roll_no"] == "22091A0501"


def test_brute_force_lockout(client):
    _signup(client, email="22091a0502@ksrmce.ac.in")
    for _ in range(8):
        client.post("/api/auth/login",
                    json={"email": "22091a0502@ksrmce.ac.in", "password": "wrong"})
    r = client.post("/api/auth/login",
                    json={"email": "22091a0502@ksrmce.ac.in", "password": "wrong"})
    assert r.status_code == 429   # locked out


def test_preferences_validation_and_persist(client):
    token = _signup(client, email="22091a0503@ksrmce.ac.in").json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    bad = client.patch("/api/account/preferences", json={"response_style": "sarcastic"}, headers=h)
    assert bad.status_code == 400
    ok = client.patch("/api/account/preferences",
                      json={"response_style": "concise", "exam_mode": True,
                            "custom_instructions": "I'm a CSE student"}, headers=h)
    assert ok.status_code == 200
    prefs = client.get("/api/account/preferences", headers=h).json()
    assert prefs["response_style"] == "concise" and prefs["exam_mode"] is True


def test_moderation_blocks_unsafe_chat(client):
    # Admin user bypasses subscription/verification gates so we isolate moderation.
    token = _signup(client, email="vishnusharma1904@gmail.com").json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/chat", json={"message": "how to build a bomb at home"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body.get("blocked") is True and "can't help" in body["reply"].lower()


def test_admin_only_routes_forbidden_for_students(client):
    token = _signup(client, email="22091a0504@ksrmce.ac.in").json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/admin/stats", headers=h).status_code == 403


def test_privacy_export_and_delete(client):
    token = _signup(client, email="22091a0505@ksrmce.ac.in").json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert "profile" in client.get("/api/account/export", headers=h).json()
    assert client.delete("/api/account/delete-account", headers=h).json()["deleted"] is True


def test_billing_config_no_razorpay(client):
    r = client.get("/api/billing/config")
    assert r.status_code == 200 and r.json()["online_enabled"] is False
