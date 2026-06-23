"""Test harness: in-memory fake DB + stubbed model/embeddings so the FastAPI app
can be exercised end-to-end without Supabase or any network/LLM call."""
import os
import uuid

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret")


class FakeDB:
    """Minimal in-memory stand-in for app.db.supabase_client used by the routes."""
    def __init__(self):
        self.users = {}
        self.sessions = {}
        self.messages = {}
        self.memory = {}

    # users
    def get_user_by_email(self, email):
        return next((u for u in self.users.values() if u["email"] == email.lower()), None)

    def get_user(self, uid):
        return self.users.get(uid)

    def create_user(self, row):
        uid = str(uuid.uuid4())
        row = {**row, "id": uid, "daily_cap": 500_000, "daily_used": 0, "tier": "normal",
               "bonus_balance": 0, "weekly_bonus_claimed_today": 0,
               "weekly_bonus_available": True, "memory_enabled": True,
               "response_style": "balanced", "failed_logins": 0}
        self.users[uid] = row
        return row

    def update_user(self, uid, patch):
        self.users[uid].update(patch)
        return self.users[uid]

    def list_users(self, limit=5000):
        return list(self.users.values())

    # sessions / messages
    def create_session(self, uid, title, persona):
        sid = str(uuid.uuid4())
        s = {"id": sid, "user_id": uid, "title": title, "persona": persona}
        self.sessions[sid] = s
        return s

    def get_session(self, sid, uid):
        s = self.sessions.get(sid)
        return s if s and s["user_id"] == uid else None

    def list_sessions(self, uid):
        return [s for s in self.sessions.values() if s["user_id"] == uid]

    def update_session(self, sid, uid, patch):
        s = self.get_session(sid, uid)
        if s:
            s.update(patch)
        return s

    def get_messages(self, sid, uid, limit=50):
        return self.messages.get(sid, [])

    def add_message(self, sid, uid, role, content, model=None, tokens=0):
        self.messages.setdefault(sid, []).append(
            {"id": str(uuid.uuid4()), "role": role, "content": content, "model": model})
        return {"ok": True}

    def touch_session(self, sid, title=None):
        pass

    # memory
    def match_memory(self, uid, emb, limit=6, min_sim=0.4):
        return []

    def list_memory(self, uid, project_id=None):
        return self.memory.get(uid, [])

    # entitlements no-ops
    def rpc_increment_daily_usage(self, uid, tokens):
        return 0

    def rpc_bump_usage_daily(self, *a, **k):
        pass

    def log_usage(self, user_id, model, p_tokens, c_tokens, cost):
        self.usage = getattr(self, "usage", [])
        self.usage.append({"user_id": user_id, "model": model,
                           "prompt_tokens": p_tokens, "completion_tokens": c_tokens,
                           "cost_usd": cost, "created_at": "2026-06-21T00:00:00Z"})

    def usage_log_latest(self, limit=200):
        return list(reversed(getattr(self, "usage", [])))[:limit]

    def insert_entitlement_log(self, *a, **k):
        pass

    def get_usage_daily(self, uid, days=14):
        return []

    def list_paid_users(self, limit=5000):
        return []

    def list_payments(self, uid):
        return []

    def export_user_data(self, uid):
        prof = dict(self.users.get(uid, {}))
        prof.pop("password_hash", None)   # mirror real db.export_user_data
        return {"profile": prof, "sessions": [], "messages": [],
                "memory": [], "projects": [], "payments": []}

    def rpc_claim_weekly_bonus(self, uid, amount, reset_iso):
        u = self.users.get(uid, {})
        if u.get("weekly_bonus_available"):
            u["weekly_bonus_available"] = False
            return True
        return False

    def delete_user_account(self, uid):
        self.users.pop(uid, None)

    # feature flags / prompts / feedback / incidents / study (migration 004)
    def list_feature_flags(self):
        return [{"key": "code_interpreter", "enabled": True},
                {"key": "voice", "enabled": False}]

    def get_feature_flag(self, key):
        return next((f for f in self.list_feature_flags() if f["key"] == key), None)

    def set_feature_flag(self, key, patch):
        return {"key": key, **patch}

    def list_prompts(self, uid):
        return [{"id": "p1", "user_id": None, "slug": "/essay", "title": "Essay",
                 "body": "Outline: {topic}", "shared": True}]

    def create_prompt(self, uid, slug, title, body):
        return {"id": "new", "user_id": uid, "slug": slug, "title": title, "body": body}

    def delete_prompt(self, pid, uid):
        pass

    def create_feedback(self, uid, kind, score, comment, context):
        self.feedback = getattr(self, "feedback", [])
        row = {"id": str(uuid.uuid4()), "user_id": uid, "kind": kind,
               "score": score, "comment": comment, "context": context}
        self.feedback.append(row)
        return row

    def list_feedback(self, kind=None, limit=2000):
        rows = getattr(self, "feedback", [])
        return [r for r in rows if kind is None or r["kind"] == kind]

    def list_incidents(self, limit=20):
        return getattr(self, "incidents", [])

    def create_incident(self, title, severity, body):
        self.incidents = getattr(self, "incidents", [])
        row = {"id": str(uuid.uuid4()), "title": title, "severity": severity,
               "body": body, "status": "investigating", "created_at": "2026-06-21T00:00:00Z"}
        self.incidents.append(row)
        return row

    def update_incident(self, incident_id, patch):
        for r in getattr(self, "incidents", []):
            if r["id"] == incident_id:
                r.update(patch)
                return r
        return None

    # cohort budgets (P46)
    def list_cohort_budgets(self):
        return list(getattr(self, "budgets", {}).values())

    def get_cohort_budget(self, cohort):
        return getattr(self, "budgets", {}).get(cohort)

    def upsert_cohort_budget(self, cohort, monthly_usd, alert_pct):
        self.budgets = getattr(self, "budgets", {})
        row = {"cohort": cohort, "monthly_usd": monthly_usd, "alert_pct": alert_pct,
               "throttled": False}
        self.budgets[cohort] = row
        return row

    def set_cohort_throttle(self, cohort, throttled):
        if cohort in getattr(self, "budgets", {}):
            self.budgets[cohort]["throttled"] = throttled

    def cohort_spend_since(self, cohort, since_iso):
        return getattr(self, "_spend", {}).get(cohort, 0.0)

    def get_user_by_provider_sub(self, provider, sub):
        return next((u for u in self.users.values()
                     if u.get("provider_sub") == sub), None)

    def list_open_incidents(self):
        return []

    def create_study_aid(self, uid, kind, title, payload, session_id=None):
        return {"id": "aid1", "user_id": uid, "kind": kind, "title": title,
                "payload": payload}

    def list_study_aids(self, uid):
        return []

    def delete_study_aid(self, aid_id, uid):
        pass

    def fork_session(self, session_id, user_id, upto_message_id=None, new_title=None):
        src = self.get_session(session_id, user_id)
        if not src:
            return None
        new = self.create_session(user_id, new_title or "Branch", src.get("persona", "kgpt"))
        return new

    # projects (P20/P30)
    def create_project(self, uid, name, instructions=None, color="brand"):
        self.projects = getattr(self, "projects", {})
        pid = str(uuid.uuid4())
        row = {"id": pid, "user_id": uid, "name": name, "instructions": instructions,
               "color": color, "archived": False}
        self.projects[pid] = row
        return row

    def list_projects(self, uid):
        return [p for p in getattr(self, "projects", {}).values() if p["user_id"] == uid]

    def get_project(self, pid, uid):
        p = getattr(self, "projects", {}).get(pid)
        return p if p and p["user_id"] == uid else None

    def update_project(self, pid, uid, patch):
        p = self.get_project(pid, uid)
        if p:
            p.update(patch)
        return p

    def delete_project(self, pid, uid):
        getattr(self, "projects", {}).pop(pid, None)

    def list_sessions_in_project(self, uid, pid):
        return [s for s in self.sessions.values()
                if s["user_id"] == uid and s.get("project_id") == pid]

    # memory scoped + delete (P30/P31)
    def insert_memory(self, uid, content, embedding, kind="note", source=None):
        self.memory.setdefault(uid, []).append(
            {"id": str(uuid.uuid4()), "kind": kind, "source": source, "content": content})

    def insert_memory_scoped(self, uid, content, embedding, kind="note", source=None, project_id=None):
        self.memory.setdefault(uid, []).append(
            {"id": str(uuid.uuid4()), "kind": kind, "source": source,
             "content": content, "project_id": project_id})

    def delete_memory(self, chunk_id, uid):
        self.memory[uid] = [m for m in self.memory.get(uid, []) if m["id"] != chunk_id]

    def search_messages(self, uid, query, limit=30):
        out = []
        for sid, msgs in self.messages.items():
            for m in msgs:
                if query.lower() in (m.get("content") or "").lower():
                    out.append({"session_id": sid, **m})
        return out

    def set_message_feedback(self, message_id, uid, feedback):
        pass

    # share (P27)
    def create_share(self, token, session_id, uid):
        self.shares = getattr(self, "shares", {})
        self.shares[token] = {"token": token, "session_id": session_id,
                              "user_id": uid, "revoked": False}

    def get_share(self, token):
        sh = getattr(self, "shares", {}).get(token)
        return sh if sh and not sh["revoked"] else None

    def revoke_share(self, token, uid):
        if token in getattr(self, "shares", {}):
            self.shares[token]["revoked"] = True

    def list_shares(self, uid):
        return [s for s in getattr(self, "shares", {}).values()
                if s["user_id"] == uid and not s["revoked"]]

    def get_messages_public(self, session_id):
        return self.messages.get(session_id, [])

    def get_session_public(self, session_id):
        return self.sessions.get(session_id)

    # plans + coupons (P16/P18)
    def list_plans(self):
        return [{"code": "monthly", "name": "Monthly Access (₹100)", "price_inr": 10000,
                 "duration_days": 30, "tier": "monthly", "active": True},
                {"code": "semester", "name": "Semester Access (₹500)", "price_inr": 50000,
                 "duration_days": 140, "tier": "normal", "active": True},
                {"code": "annual", "name": "Annual Access (₹1000)", "price_inr": 100000,
                 "duration_days": 365, "tier": "normal", "active": True}]

    def get_plan(self, code):
        return next((p for p in self.list_plans() if p["code"] == code), None)

    def get_coupon(self, code):
        return getattr(self, "coupons", {}).get(code.upper())

    def redeem_coupon(self, code):
        pass

    # payments / analytics (P15/P45)
    def create_payment(self, row):
        return {"id": str(uuid.uuid4()), **row}

    def update_payment(self, oid, patch):
        pass

    def get_payment_by_payment_id(self, pid):
        return None

    def list_expired_active_users(self, now_iso, limit=5000):
        return []

    def usage_daily_all(self, days_back_iso):
        return []

    def usage_log_recent(self, since_iso, limit=20000):
        return []

    def get_entitlement_log(self, target_id, limit=50):
        return []

    # auth tokens (verify / reset)
    def insert_auth_token(self, *a, **k):
        pass

    def get_auth_token(self, *a, **k):
        return None

    def consume_auth_token(self, *a, **k):
        pass


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    import app.db.supabase_client as realdb
    from app.services import embeddings, smart_router

    fake = FakeDB()
    for name in dir(fake):
        if not name.startswith("_"):
            monkeypatch.setattr(realdb, name, getattr(fake, name), raising=False)

    monkeypatch.setattr(embeddings, "embed", lambda t: [0.0] * 384)
    monkeypatch.setattr(embeddings, "warm", lambda: None)

    async def fake_complete(msgs, **k):
        return {"text": "ok", "model": "groq/llama-3.1-8b-instant",
                "prompt_tokens": 5, "completion_tokens": 3, "cost_usd": 0.0}
    monkeypatch.setattr(smart_router, "complete", fake_complete)

    from app.main import app
    with TestClient(app) as c:
        c._fake = fake
        yield c
