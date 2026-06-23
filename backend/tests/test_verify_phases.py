"""Phase-by-phase verification (Session 3).

One test per delivered phase, exercising the real request path through the app
with the in-memory harness. Admin paths use the configured admin email so
require_admin passes.
"""

ADMIN_EMAIL = "vishnusharma1904@gmail.com"


def _student(client, email="a1234@ksrmce.ac.in"):
    r = client.post("/api/auth/signup", json={
        "email": email, "full_name": "Stu Dent", "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _admin(client):
    r = client.post("/api/auth/signup", json={
        "email": ADMIN_EMAIL, "full_name": "Admin", "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# === P3 — Google SSO ========================================================
def test_p3_google_config_and_rejects_bad_token(client):
    assert client.get("/api/auth/google/config").json()["enabled"] is False
    # With no GOOGLE_CLIENT_ID configured, login is unavailable (503), not a crash.
    r = client.post("/api/auth/google", json={"credential": "x.y.z"})
    assert r.status_code == 503


# === P4 — Environments & feature flags ======================================
def test_p4_flags_admin_only_and_toggle(client):
    stu = _student(client)
    assert client.get("/api/admin/flags", headers=_h(stu)).status_code == 403
    adm = _admin(client)
    assert client.get("/api/admin/flags", headers=_h(adm)).status_code == 200
    r = client.patch("/api/admin/flags/voice", headers=_h(adm), json={"enabled": True})
    assert r.status_code == 200


# === P23 — Artifacts (frontend) — backend has no surface; covered by tsc ====


# === P24 — Prompt library & slash commands ==================================
def test_p24_prompts_crud(client):
    tok = _student(client)
    assert any(p["slug"] == "/essay" for p in client.get("/api/prompts", headers=_h(tok)).json())
    created = client.post("/api/prompts", headers=_h(tok),
                          json={"slug": "mine", "title": "Mine", "body": "do {x}"})
    assert created.status_code == 200 and created.json()["slug"] == "/mine"  # slug normalised


# === P26 — Branching ========================================================
def test_p26_branch_creates_new_session(client):
    tok = _student(client)
    s = client.post("/api/chat/sessions", headers=_h(tok),
                    json={"title": "orig", "persona": "kgpt"}).json()
    r = client.post(f"/api/chat/sessions/{s['id']}/branch", headers=_h(tok), json={})
    assert r.status_code == 200 and r.json()["id"] != s["id"]
    # branching a missing session 404s, not 500
    assert client.post("/api/chat/sessions/nope/branch", headers=_h(tok), json={}).status_code == 404


# === P34 — Vision ===========================================================
def test_p34_vision_routes_to_vision_category(client):
    # Use admin (active subscription) so the access check passes; images must
    # still force the vision category ahead of the premium/intent logic.
    tok = _admin(client)
    px = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    r = client.post("/api/chat", headers=_h(tok),
                    json={"message": "what is this?", "images": [px]})
    assert r.status_code == 200, r.text
    assert r.json()["category"] == "vision"


def test_p34_unsubscribed_student_blocked_before_model(client):
    # Confirms the access gate (402) fires for an unpaid student even with images.
    tok = _student(client)
    r = client.post("/api/chat", headers=_h(tok),
                    json={"message": "hi", "images": ["data:image/png;base64,iVBORw0KGgo="]})
    assert r.status_code == 402


# === P36 — Code interpreter =================================================
def test_p36_sandbox_executes_and_isolates(client):
    tok = _student(client)
    ok = client.post("/api/tools/execute", headers=_h(tok), json={"code": "print(6*7)"})
    assert ok.status_code == 200 and "42" in ok.json()["stdout"]
    blocked = client.post("/api/tools/execute", headers=_h(tok), json={"code": "import socket"})
    assert blocked.json()["ok"] is False


# === P37 — Tool framework ===================================================
def test_p37_tools_list_and_run(client):
    tok = _student(client)
    names = client.get("/api/tools", headers=_h(tok)).json()["names"]
    assert "calculator" in names
    r = client.post("/api/tools/run", headers=_h(tok),
                    json={"name": "convert", "args": {"value": 1, "from_unit": "km", "to_unit": "m"}})
    assert "1000" in r.json()["result"]


# === P38 — Study aids =======================================================
def test_p38_study_generate_from_text(client):
    tok = _student(client)
    r = client.post("/api/study/generate", headers=_h(tok),
                    json={"kind": "summary", "text": "Photosynthesis converts light to energy."})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "summary" and "payload" in r.json()
    # empty input is a clean 400, not a crash
    assert client.post("/api/study/generate", headers=_h(tok),
                       json={"kind": "quiz"}).status_code == 400


# === P45 — Analytics (admin) ================================================
def test_p45_analytics_admin_only(client):
    assert client.get("/api/admin/analytics", headers=_h(_student(client))).status_code == 403
    r = client.get("/api/admin/analytics", headers=_h(_admin(client)))
    assert r.status_code == 200 and "totals" in r.json()


# === P46 — Cost governance ==================================================
def test_p46_budget_set_and_evaluate(client):
    adm = _admin(client)
    assert client.put("/api/admin/budgets", headers=_h(adm),
                      json={"cohort": "CSE-A", "monthly_usd": 10, "alert_pct": 80}).status_code == 200
    ev = client.get("/api/admin/budgets", headers=_h(adm))
    assert ev.status_code == 200 and any(b["cohort"] == "CSE-A" for b in ev.json())
    assert client.post("/api/admin/budgets/enforce", headers=_h(adm)).status_code == 200


# === P47 — Reliability & status =============================================
def test_p47_status_public_and_incident_lifecycle(client):
    assert client.get("/api/status").json()["status"] in ("operational", "degraded", "outage")
    adm = _admin(client)
    inc = client.post("/api/status/incidents", headers=_h(adm),
                      json={"title": "DB slow", "severity": "major"})
    assert inc.status_code == 200
    iid = inc.json()["id"]
    upd = client.patch(f"/api/status/incidents/{iid}", headers=_h(adm),
                       json={"status": "resolved"})
    assert upd.status_code == 200


# === P50 — Pilot feedback / NPS =============================================
def test_p50_feedback_and_nps(client):
    stu = _student(client)
    assert client.post("/api/feedback", headers=_h(stu), json={"kind": "nps", "score": 10}).status_code == 200
    adm = _admin(client)
    rep = client.get("/api/feedback/nps", headers=_h(adm))
    assert rep.status_code == 200 and rep.json()["responses"] >= 1


# === P21 — Explicit model picker (paid/admin) ===============================
def test_p21_model_picker_list_and_gate(client):
    # Student (inactive sub) cannot pick; admin can.
    stu = _student(client, "a7777@ksrmce.ac.in")
    sres = client.get("/api/chat/models", headers=_h(stu)).json()
    assert sres["can_pick"] is False and len(sres["models"]) >= 20
    providers = {m["provider"] for m in sres["models"]}
    assert providers == {"groq", "gemini", "mistral", "fireworks_ai", "openrouter"}

    adm = _admin(client)
    ares = client.get("/api/chat/models", headers=_h(adm)).json()
    assert ares["can_pick"] is True


def test_p21_admin_can_pin_model(client):
    adm = _admin(client)
    mid = "groq/llama-3.3-70b-versatile"
    r = client.post("/api/chat", headers=_h(adm), json={"message": "hi", "model": mid})
    assert r.status_code == 200 and r.json()["category"] == "custom"


def test_p21_student_model_pick_ignored(client):
    # An unpaid student passing a model is ignored (no crash); but they're gated
    # at the access check first (402), proving the pin can't bypass entitlements.
    stu = _student(client, "a7778@ksrmce.ac.in")
    r = client.post("/api/chat", headers=_h(stu),
                    json={"message": "hi", "model": "groq/llama-3.3-70b-versatile"})
    assert r.status_code == 402


# === Cost estimate (uncapped output + pre-send caution) =====================
def test_estimate_returns_percent_only(client):
    stu = _student(client, "a8001@ksrmce.ac.in")
    r = client.post("/api/chat/estimate", headers=_h(stu),
                    json={"message": "build me a full website with backend in python"})
    assert r.status_code == 200
    body = r.json()
    assert "percent" in body and "level" in body and "remaining_percent" in body
    # %-only contract: no raw token integers leak
    for forbidden in ("tokens", "daily_cap", "daily_used"):
        assert forbidden not in body
    # a big request should estimate a higher cost than a tiny one
    small = client.post("/api/chat/estimate", headers=_h(stu), json={"message": "hi"}).json()
    assert body["percent"] >= small["percent"]


def test_estimate_admin_unlimited(client):
    adm = _admin(client)
    r = client.post("/api/chat/estimate", headers=_h(adm), json={"message": "build a website"})
    assert r.status_code == 200 and r.json().get("unlimited") is True


# === Frontier 3.5x multiplier + monthly tier ================================
def test_frontier_multiplier():
    from app.services import smart_router as r
    from app.services import quota_policy as Q
    assert r.cost_multiplier("groq/llama-3.1-8b-instant") == 1.0
    assert r.cost_multiplier("groq/llama-3.3-70b-versatile") == 1.5   # override (was frontier)
    assert r.cost_multiplier("fireworks_ai/accounts/fireworks/models/glm-5p1") == 3.5  # >$1
    # monthly plan tier caps the day at 150k
    assert Q.cap_for_tier("monthly") == 150_000
    assert Q.cap_for_tier("heavy") == 1_000_000
    assert Q.cap_for_tier("normal") == 500_000


def test_monthly_plan_listed(client):
    plans = client.get("/api/billing/plans").json()
    m = next((p for p in plans if p["code"] == "monthly"), None)
    assert m and m["tier"] == "monthly" and m["price_inr"] == 10000


def test_picker_reserved_for_heavy(client):
    # An active NORMAL-tier student still can't pick (power-hitters only).
    tok = _student(client, "a9001@ksrmce.ac.in")
    uid = client._fake.get_user_by_email("a9001@ksrmce.ac.in")["id"]
    client._fake.users[uid].update({"sub_status": "active", "tier": "normal"})
    assert client.get("/api/chat/models", headers=_h(tok)).json()["can_pick"] is False
    client._fake.users[uid]["tier"] = "heavy"
    assert client.get("/api/chat/models", headers=_h(tok)).json()["can_pick"] is True


# === Admin grant-plan (monthly/semester/annual) =============================
def test_admin_grant_plan(client):
    adm = _admin(client)
    _student(client, "a9100@ksrmce.ac.in")
    uid = client._fake.get_user_by_email("a9100@ksrmce.ac.in")["id"]
    r = client.post("/api/admin/grant-plan", headers=_h(adm),
                    json={"user_ids": [uid], "plan": "monthly"})
    assert r.status_code == 200 and r.json()["plan"] == "monthly"
    u = client._fake.get_user(uid)
    assert u["sub_status"] == "active" and u["tier"] == "monthly"
    # unknown plan → 404
    assert client.post("/api/admin/grant-plan", headers=_h(adm),
                       json={"user_ids": [uid], "plan": "nope"}).status_code == 404
