#!/usr/bin/env python3
"""
K-GPT — authorized self-pentest probe
=====================================
Run this ONLY against your own K-GPT instance. It is non-destructive: it does
not delete data, persist anything, or attempt to damage the server. It reports
how well your security holds against a set of common attacks.

Usage:
    pip install requests pyjwt
    python security_probe.py                          # localhost defaults
    python security_probe.py --api http://localhost:8400 --web http://localhost:3000
    python security_probe.py --token <YOUR_JWT>        # also run authenticated probes

Get a token: log in to the web app, open DevTools console, run
    localStorage.getItem('kgpt_token')

Exit code is non-zero if any CRITICAL/FAIL check trips.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid

try:
    import requests
except ImportError:
    sys.exit("Please `pip install requests pyjwt` first.")
try:
    import jwt as pyjwt
except ImportError:
    sys.exit("Please `pip install pyjwt` first.")

DEFAULT_SECRET = "CHANGE_ME_dev_secret"   # the insecure default in config.py

results: list[tuple[str, str, str]] = []   # (level, name, detail)


def record(level: str, name: str, detail: str = ""):
    results.append((level, name, detail))
    tag = {"PASS": "\033[92mPASS\033[0m", "WARN": "\033[93mWARN\033[0m",
           "FAIL": "\033[91mFAIL\033[0m", "INFO": "\033[96mINFO\033[0m"}.get(level, level)
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))


def get(url, **kw):
    kw.setdefault("timeout", 8)
    return requests.get(url, **kw)


# --------------------------------------------------------------------------- #
# 1. Security headers
# --------------------------------------------------------------------------- #
def check_headers(api, web):
    wanted = ["X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"]
    for label, base in (("API", api), ("Web", web)):
        try:
            r = get(base + "/")
        except Exception as e:
            record("WARN", f"{label} reachable", f"could not connect: {e}")
            continue
        missing = [h for h in wanted if h not in r.headers]
        if missing:
            record("WARN", f"{label} security headers", f"missing: {', '.join(missing)}")
        else:
            record("PASS", f"{label} security headers", "nosniff / frame-options / referrer-policy present")
        if "Server" in r.headers and any(s in r.headers["Server"].lower() for s in ("uvicorn", "next")):
            record("INFO", f"{label} server banner", r.headers.get("Server", ""))


# --------------------------------------------------------------------------- #
# 2. Auth gating — protected endpoints must reject anonymous callers
# --------------------------------------------------------------------------- #
def check_auth_gating(api):
    protected = ["/api/auth/me", "/api/chat/sessions", "/api/account/usage",
                 "/api/admin/stats", "/api/memory"]
    bad = []
    for p in protected:
        try:
            r = get(api + p)
        except Exception:
            continue
        if r.status_code not in (401, 403):
            bad.append(f"{p}={r.status_code}")
    if bad:
        record("FAIL", "Anonymous access blocked", "leaked: " + ", ".join(bad))
    else:
        record("PASS", "Anonymous access blocked", "all protected endpoints return 401/403")


# --------------------------------------------------------------------------- #
# 3. JWT forgery with the default secret  (THE big one)
# --------------------------------------------------------------------------- #
def check_default_secret(api):
    now = int(time.time())
    forged = pyjwt.encode(
        {"sub": "probe-admin", "role": "admin", "iat": now, "exp": now + 3600},
        DEFAULT_SECRET, algorithm="HS256",
    )
    try:
        r = get(api + "/api/admin/stats", headers={"Authorization": f"Bearer {forged}"})
    except Exception as e:
        record("WARN", "Default-secret JWT forgery", f"could not test: {e}")
        return
    if r.status_code == 200:
        record("FAIL", "Default-secret JWT forgery",
               "CRITICAL: admin token forged with the public default secret was ACCEPTED. "
               "Set a strong SECRET_KEY now.")
    else:
        record("PASS", "Default-secret JWT forgery", f"forged admin token rejected ({r.status_code})")


# --------------------------------------------------------------------------- #
# 4. alg:none / tampered token must be rejected
# --------------------------------------------------------------------------- #
def check_alg_none(api):
    import base64
    def b64(d): return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    now = int(time.time())
    tok = b64({"alg": "none", "typ": "JWT"}) + "." + b64({"sub": "x", "role": "admin", "exp": now + 3600}) + "."
    try:
        r = get(api + "/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
        if r.status_code in (401, 403):
            record("PASS", "alg:none token", f"rejected ({r.status_code})")
        else:
            record("FAIL", "alg:none token", f"CRITICAL: accepted ({r.status_code})")
    except Exception as e:
        record("WARN", "alg:none token", str(e))


# --------------------------------------------------------------------------- #
# 5. Signup domain gate (non-destructive: bad domain should be refused)
# --------------------------------------------------------------------------- #
def check_signup_gate(api):
    fake = f"attacker-{uuid.uuid4().hex[:8]}@evil.example"
    try:
        r = requests.post(api + "/api/auth/signup",
                          json={"full_name": "probe", "email": fake, "password": "Password123!"},
                          timeout=8)
        if r.status_code == 403:
            record("PASS", "Signup domain gate", "non-college email refused (403)")
        elif r.status_code in (200, 201):
            record("FAIL", "Signup domain gate", "CRITICAL: arbitrary external email created an account")
        else:
            record("INFO", "Signup domain gate", f"status {r.status_code}")
    except Exception as e:
        record("WARN", "Signup domain gate", str(e))


# --------------------------------------------------------------------------- #
# 6. CORS — a hostile origin must not be reflected with credentials
# --------------------------------------------------------------------------- #
def check_cors(api):
    evil = "https://evil.example"
    try:
        r = requests.options(api + "/api/auth/login",
                             headers={"Origin": evil,
                                      "Access-Control-Request-Method": "POST"}, timeout=8)
        acao = r.headers.get("Access-Control-Allow-Origin", "")
        acac = r.headers.get("Access-Control-Allow-Credentials", "")
        if acao == evil or acao == "*" and acac == "true":
            record("FAIL", "CORS policy", f"hostile origin reflected (ACAO={acao}, creds={acac})")
        else:
            record("PASS", "CORS policy", f"hostile origin not allowed (ACAO='{acao}')")
    except Exception as e:
        record("WARN", "CORS policy", str(e))


# --------------------------------------------------------------------------- #
# Authenticated probes (need --token)
# --------------------------------------------------------------------------- #
def check_idor(api, token):
    h = {"Authorization": f"Bearer {token}"}
    rnd = str(uuid.uuid4())
    try:
        r = get(api + f"/api/chat/sessions/{rnd}", headers=h)
        if r.status_code in (403, 404):
            record("PASS", "IDOR (cross-tenant read)", f"random session id rejected ({r.status_code})")
        elif r.status_code == 200:
            record("FAIL", "IDOR (cross-tenant read)", "a session you don't own returned data")
        else:
            record("INFO", "IDOR (cross-tenant read)", f"status {r.status_code}")
    except Exception as e:
        record("WARN", "IDOR (cross-tenant read)", str(e))


def check_sandbox_exfil(api, token):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # 6a. secret exfiltration via environment
    try:
        r = requests.post(api + "/api/tools/execute",
                          headers=h, json={"code": "import os\nprint(dict(os.environ))", "timeout": 5},
                          timeout=20)
        body = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}) or {}
        blob = json.dumps(body).upper()
        leak = any(k in blob for k in ("API_KEY", "SECRET_KEY", "SERVICE_KEY", "SUPABASE", "RAZORPAY"))
        blocked = "not allowed" in json.dumps(body).lower() or "importerror" in blob.lower()
        if leak:
            record("FAIL", "Sandbox secret exfiltration",
                   "CRITICAL: provider/secret keys appear in interpreter output")
        elif blocked:
            record("PASS", "Sandbox secret exfiltration", "`import os` blocked in sandbox")
        else:
            record("PASS", "Sandbox secret exfiltration", "no secrets in interpreter environment")
    except Exception as e:
        record("WARN", "Sandbox secret exfiltration", str(e))
    # 6b. host command execution
    try:
        r = requests.post(api + "/api/tools/execute",
                          headers=h, json={"code": "import os\nprint(os.system('echo PWNED'))", "timeout": 5},
                          timeout=20)
        out = json.dumps(r.json()).upper() if r.ok else ""
        if "PWNED" in out and "ERROR" not in out:
            record("FAIL", "Sandbox host command", "CRITICAL: os.system executed on the host")
        else:
            record("PASS", "Sandbox host command", "os.system blocked / unavailable")
    except Exception as e:
        record("WARN", "Sandbox host command", str(e))


def main():
    ap = argparse.ArgumentParser(description="K-GPT authorized self-pentest probe")
    ap.add_argument("--api", default="http://localhost:8400")
    ap.add_argument("--web", default="http://localhost:3000")
    ap.add_argument("--token", default="", help="a valid JWT for authenticated probes")
    args = ap.parse_args()

    print("=" * 64)
    print(" K-GPT self-pentest — run only against systems you own/operate")
    print(f" API: {args.api}    Web: {args.web}")
    print("=" * 64)

    check_headers(args.api, args.web)
    check_auth_gating(args.api)
    check_default_secret(args.api)
    check_alg_none(args.api)
    check_signup_gate(args.api)
    check_cors(args.api)

    if args.token:
        check_idor(args.api, args.token)
        check_sandbox_exfil(args.api, args.token)
    else:
        record("INFO", "Authenticated probes", "skipped — pass --token to run IDOR + sandbox tests")

    print("-" * 64)
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print(f" Summary: {len(fails)} FAIL, {len(warns)} WARN, "
          f"{sum(1 for r in results if r[0] == 'PASS')} PASS")
    if fails:
        print(" ❗ Address FAIL items before exposing this server to the internet.")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
