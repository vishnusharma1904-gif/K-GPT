# K-GPT — Security Audit & Hardening

A white-box review of the frontend and backend, the fixes applied, and what
still needs your attention. Run `security_probe.py` against your own server to
verify the live posture (see bottom).

> Reality check: nothing is "un-hackable." The goal is to close the real holes
> and raise the cost of an attack. The biggest remaining risks are server-side
> and operational, not in the UI.

---

## What's already solid (verified in code)

- **Tenant isolation / no IDOR** — every session, message, memory and usage query
  filters on `user_id` (`.eq("user_id", user_id)`). A logged-in user cannot read
  another user's data by guessing IDs.
- **JWT** — HS256 with an explicit `algorithms=["HS256"]` allow-list, so
  `alg:none` and RS/HS confusion attacks are rejected.
- **Passwords** — hashed with `pbkdf2_sha256` (passlib), constant-time verify.
- **Brute force** — per-account lockout after 8 failed logins (15 min).
- **No user enumeration on login/forgot** — both return generic responses.
- **CORS** — restricted to a configured origin allow-list (not `*`).
- **Backend security headers** — middleware sets nosniff / frame-options / etc.
- **Frontend XSS surface** — `react-markdown` does **not** render raw HTML and
  sanitizes link URLs; the artifact preview runs in a `sandbox`ed iframe without
  `allow-same-origin`.

---

## Fixed in this pass

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | **Critical** | **Interpreter secret exfiltration.** `/api/tools/execute` ran user code in a subprocess that **inherited the server environment** — all provider API keys, `SECRET_KEY`, and the Supabase service key. `import os; print(os.environ)` dumped them. | `sandbox.py` now passes a scrubbed `env` (PATH + encoding only). |
| 2 | **Critical** | **Sandbox host exec.** The denylist had the string `"os.system"`, which the import guard never matched — so `import os; os.system(...)` ran host commands. `importlib` also bypassed the denylist. | Blocked `os` and `importlib` at the root, plus more network modules. |
| 3 | **Critical** | **Default JWT secret.** `SECRET_KEY` defaulted to `CHANGE_ME_dev_secret`; shipping unset lets anyone forge admin tokens. | `get_settings()` now refuses to boot in production with the default secret. |
| 4 | **High** | **Artifact "open in new tab"** wrote untrusted model HTML into a same-origin tab, where it could read `localStorage` (your token). | Now wraps it in a `sandbox`ed, null-origin iframe. |
| 5 | Medium | Frontend lacked response security headers. | Added CSP (base/object/frame/form), nosniff, frame-options, referrer-policy, permissions-policy, HSTS in `next.config.mjs`; hid the `X-Powered-By` banner. |
| 6 | Low | External citation links used `rel="noreferrer"` only. | Added `noopener nofollow`. |

---

## Still recommended (not changed — needs your decision)

1. **Admin-by-email has no ownership proof (High).** Signup grants `role=admin`
   + auto-verified to anyone who registers an email listed in `ADMIN_EMAILS`,
   with no email verification. If an admin email isn't registered yet, whoever
   claims it first becomes admin. → Pre-provision the admin row server-side, or
   require verification / a separate admin bootstrap secret. Make sure **you have
   already registered** `vishnusharma1904@gmail.com`.
2. **Code interpreter is not a real sandbox.** The import denylist is inherently
   bypassable and `resource`/`SIGALRM` limits are POSIX-only (no caps on Windows).
   For production, run it in a container (gVisor / nsjail / Docker with `--network
   none`, read-only FS, dropped caps) **or keep `code_interpreter` disabled.**
3. **Set `SECRET_KEY`, `DEBUG=false`, and real `CORS_ORIGINS`** in production env.
4. **JWTs aren't revoked** on password reset/logout (stateless, 7-day TTL).
   Consider a shorter TTL or a token-version/`jti` denylist for true logout.
5. **Signup returns 409** for existing emails → minor email enumeration. Optional:
   return the same generic message as login.
6. **Rate limiting** is per-account for login and fair-use for chat; consider an
   IP-based limiter (e.g., slowapi / nginx) in front for blunt DoS/brute-force.
7. **Disable `/docs` & `/openapi.json`** in production if you don't want the API
   surface publicly enumerable.

---

## Run the live self-test

```bash
pip install requests pyjwt
# unauthenticated probes:
python security_probe.py --api http://localhost:8400 --web http://localhost:3000
# add IDOR + sandbox probes (token from DevTools: localStorage.getItem('kgpt_token')):
python security_probe.py --token <YOUR_JWT>
```

A green run on the default-secret, alg:none, auth-gating, CORS and sandbox checks
means the critical issues are closed on your running instance.
