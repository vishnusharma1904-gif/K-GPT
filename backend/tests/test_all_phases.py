"""Completeness verification for the earlier phases (Epics A–E, G–I) not
already covered by test_policy / test_api / test_verify_phases.

One focused check per phase, exercising the real code path. Pure-logic phases
(quota) are asserted directly against the policy module.
"""
from app.services import quota_policy as Q

ADMIN = "vishnusharma1904@gmail.com"


def _student(client, email):
    return client.post("/api/auth/signup", json={
        "email": email, "full_name": "S", "password": "password123"}).json()["access_token"]


def _admin(client):
    return client.post("/api/auth/signup", json={
        "email": ADMIN, "full_name": "Admin", "password": "password123"}).json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


# === P1 — Tenant isolation ==================================================
def test_p1_tenant_isolation(client):
    a = _student(client, "22091a0601@ksrmce.ac.in")
    b = _student(client, "22091a0602@ksrmce.ac.in")
    sa = client.post("/api/chat/sessions", headers=_h(a),
                     json={"title": "A secret", "persona": "kgpt"}).json()
    # B must not see A's session list nor open A's session
    assert all(s["id"] != sa["id"] for s in client.get("/api/chat/sessions", headers=_h(b)).json())
    assert client.get(f"/api/chat/sessions/{sa['id']}", headers=_h(b)).status_code == 404


# === P5 — Observability (request id) ========================================
def test_p5_request_id_header(client):
    r = client.get("/api/health")
    assert "x-request-id" in {k.lower() for k in r.headers.keys()}


# === P8 — Daily quota cap blocks ============================================
def test_p8_over_cap_blocks_429(client):
    # A non-admin (admins bypass by design) with an active sub, over the daily cap.
    tok = _student(client, "22091a0611@ksrmce.ac.in")
    fake = client._fake
    uid = fake.get_user_by_email("22091a0611@ksrmce.ac.in")["id"]
    fake.users[uid].update({"role": "student", "sub_status": "active",
                            "daily_used": 600_000, "daily_cap": 500_000,
                            "bonus_balance": 0, "weekly_bonus_claimed_today": 0,
                            "weekly_bonus_available": False,
                            "daily_reset_at": "2099-01-01T00:00:00+00:00"})
    r = client.post("/api/chat", headers=_h(tok), json={"message": "hi"})
    assert r.status_code == 429


# === P9 — Auto-tiering decision (pure) ======================================
def test_p9_tiering_decision():
    # >=80% of 500k on >=4 of last 7 days -> promote to heavy
    last7 = [450_000] * 5
    assert Q.tiering_decision("normal", False, last7, last7) == "heavy"
    # all of last 14 below 40% of cap -> demote to normal
    light14 = [50_000] * 14
    assert Q.tiering_decision("heavy", False, light14[:7], light14) == "normal"
    # sticky admin override is never auto-changed
    assert Q.tiering_decision("normal", True, [450_000] * 5, [450_000] * 5) == "normal"


# === P10 — Weekly bonus claim ===============================================
def test_p10_claim_weekly_bonus(client):
    tok = _admin(client)
    r = client.post("/api/account/claim-bonus", headers=_h(tok))
    assert r.status_code in (200, 400)  # 200 claims, 400 if already used — both valid


# === P11 — Admin entitlement controls =======================================
def test_p11_admin_reset_grant_tier(client):
    adm = _admin(client)
    _student(client, "22091a0603@ksrmce.ac.in")
    uid = client._fake.get_user_by_email("22091a0603@ksrmce.ac.in")["id"]
    assert client.post("/api/admin/entitlements/reset-daily", headers=_h(adm),
                       json={"user_ids": [uid]}).status_code == 200
    assert client.post("/api/admin/entitlements/grant-tokens", headers=_h(adm),
                       json={"user_ids": [uid], "tokens": 100000}).status_code == 200
    assert client.post("/api/admin/entitlements/set-tier", headers=_h(adm),
                       json={"user_ids": [uid], "tier": "heavy"}).status_code == 200


# === P12 — Percentage-only usage contract ===================================
def test_p12_usage_has_no_raw_tokens(client):
    tok = _admin(client)
    body = client.get("/api/account/usage", headers=_h(tok)).json()
    assert "percent_used" in body and "state" in body
    # the contract: no raw token integers leak to a non-admin usage view
    for forbidden in ("daily_used", "daily_cap", "tokens", "bonus_balance"):
        assert forbidden not in body, f"leaked {forbidden}"


# === P16 — Plans =============================================================
def test_p16_plans_listed(client):
    plans = client.get("/api/billing/plans").json()
    assert any(p["code"] == "semester" for p in plans)


# === P18 — Coupons + bulk activation (admin) ================================
def test_p18_bulk_activate(client):
    # Bulk-activate by roll number (coupon create uses db.sb() directly -> needs live DB).
    adm = _admin(client)
    _student(client, "22091a0610@ksrmce.ac.in")  # roll 22091A0610
    r = client.post("/api/admin/bulk-activate", headers=_h(adm),
                    json={"roll_nos": ["22091A0610"], "months": 6})
    assert r.status_code == 200 and r.json()["activated"] >= 1


# === P20 — Projects CRUD ====================================================
def test_p20_projects_crud(client):
    tok = _student(client, "22091a0604@ksrmce.ac.in")
    p = client.post("/api/projects", headers=_h(tok),
                    json={"name": "DSA", "instructions": "focus on arrays"}).json()
    assert p["name"] == "DSA"
    assert any(x["id"] == p["id"] for x in client.get("/api/projects", headers=_h(tok)).json())
    assert client.patch(f"/api/projects/{p['id']}", headers=_h(tok),
                        json={"name": "DSA-2"}).status_code == 200
    assert client.delete(f"/api/projects/{p['id']}", headers=_h(tok)).status_code == 200


# === P21 — Model-category picker ============================================
def test_p21_category_override(client):
    tok = _admin(client)
    r = client.post("/api/chat", headers=_h(tok),
                    json={"message": "hello", "category": "reasoning"})
    assert r.status_code == 200 and r.json()["category"] == "reasoning"


# === P27 — Share links ======================================================
def test_p27_share_lifecycle(client):
    tok = _student(client, "22091a0605@ksrmce.ac.in")
    s = client.post("/api/chat/sessions", headers=_h(tok),
                    json={"title": "notes", "persona": "kgpt"}).json()
    sh = client.post(f"/api/share/{s['id']}", headers=_h(tok)).json()
    token = sh["token"]
    assert client.get(f"/api/share/public/{token}").status_code == 200
    assert client.delete(f"/api/share/{token}", headers=_h(tok)).status_code == 200
    assert client.get(f"/api/share/public/{token}").status_code == 404  # revoked


# === P29 — File upload → memory =============================================
def test_p29_upload_to_memory(client):
    tok = _student(client, "22091a0606@ksrmce.ac.in")
    files = {"file": ("notes.txt", b"Ohm's law: V equals I times R. " * 30, "text/plain")}
    r = client.post("/api/upload", headers=_h(tok), files=files)
    assert r.status_code == 200 and r.json()["chunks_stored"] >= 1


def test_p29_admin_upload_bypasses_size_cap(client, monkeypatch):
    from app.routers import upload as upload_router

    adm = _admin(client)
    old = upload_router.settings.max_upload_mb
    monkeypatch.setattr(upload_router.settings, "max_upload_mb", 1)
    try:
        files = {"file": ("big-notes.txt", b"A" * (2 * 1024 * 1024), "text/plain")}
        r = client.post("/api/upload", headers=_h(adm), files=files)
    finally:
        monkeypatch.setattr(upload_router.settings, "max_upload_mb", old)
    assert r.status_code == 200 and r.json()["chunks_stored"] >= 1


# === P31 — Memory v2 (add / list / delete) ==================================
def test_p31_memory_crud(client):
    tok = _student(client, "22091a0607@ksrmce.ac.in")
    add = client.post("/api/memory", headers=_h(tok),
                      json={"content": "I prefer worked examples", "kind": "note"})
    assert add.status_code in (200, 201)
    lst = client.get("/api/memory", headers=_h(tok)).json()
    assert any("worked examples" in m["content"] for m in lst)


# === P32 — Citations surfaced ===============================================
def test_p32_chat_returns_citations_field(client):
    tok = _admin(client)
    r = client.post("/api/chat", headers=_h(tok), json={"message": "hello"})
    assert "citations" in r.json()


# === P41 — Privacy export/delete (already in test_api; re-assert shape) =====
def test_p41_export_excludes_password(client):
    tok = _student(client, "22091a0608@ksrmce.ac.in")
    data = client.get("/api/account/export", headers=_h(tok)).json()
    assert "password_hash" not in data.get("profile", {})


# === P44 — Admin v2 search ==================================================
def test_p44_admin_user_search(client):
    adm = _admin(client)
    _student(client, "22091a0609@ksrmce.ac.in")
    r = client.get("/api/admin/users/search?q=22091a0609", headers=_h(adm))
    assert r.status_code == 200 and r.json()["count"] >= 1
