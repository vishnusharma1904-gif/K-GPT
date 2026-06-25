# Hosting K-GPT on promptpulse.in (Cloudflare Tunnel)

**Goal:** put K-GPT online at a URL on your own domain, running on your PC now and
movable to a cloud VPS later — without touching your existing company website.

Your repo is already built for this: `docker-compose.tunnel.yml` + `deployment/Caddyfile`
put the frontend and backend behind **one origin** (`caddy:8080`) and expose it with a
**Cloudflare Tunnel** (outbound connection — no port-forwarding, works behind your home
router/CGNAT, automatic HTTPS). The only thing to change for a permanent URL is swapping
the *quick* tunnel for a *named* tunnel on your domain.

---

## First decide: the URL

You mentioned `promptpulse.in/kgpt` **or** `kgpt.in`. Here's the honest tradeoff:

| Option | Effort | Notes |
|---|---|---|
| **`kgpt.promptpulse.in`** (subdomain) | ✅ Easiest | **Recommended.** Zero code changes. Keeps your company site at `promptpulse.in` untouched. Gives you "kgpt" branding for free. |
| **`kgpt.in`** (separate domain) | 🟡 Easy-ish | Clean and brandable, but you must **buy** the domain (~₹800/yr) and add it as a second Cloudflare zone. Same tunnel steps, just a different hostname. |
| **`promptpulse.in/kgpt`** (sub-path) | 🔴 Hard | Avoid. Next.js assumes it runs at the site root (`/`, API at `/api/*`). Serving under `/kgpt` requires `basePath: '/kgpt'` in `next.config.mjs`, rewriting every API call, and making your company site's server reverse-proxy `/kgpt/*` to the tunnel. Lots of fiddly breakage for no real benefit. |

**This guide uses `kgpt.promptpulse.in`.** If you prefer `kgpt.in`, the steps are identical
— just add `kgpt.in` as its own Cloudflare site and use that hostname in Step 3.

> Your company website at `promptpulse.in` stays exactly where it is. A subdomain is a
> separate DNS record; it does not affect the root domain.

---

## Step 0 — Why no cloud hosting is needed, and the cert question

- **No hosting purchase.** The app runs on **your own PC**. Cloudflare Tunnel opens an
  *outbound* connection from your PC to Cloudflare, so the internet reaches it with no
  port-forwarding, no static IP, and no rented server. Cost: ₹0.
- **Your SSL certificate:** you do **not** install it here. Cloudflare auto-issues a free
  HTTPS cert for `kgpt.promptpulse.in` (Universal SSL) and the tunnel link is already
  encrypted. Keep your purchased cert for later — it's only used if you self-host on a VPS
  and terminate TLS yourself (Caddy can load it then). On the Free plan you can't upload a
  custom cert anyway, so the free auto-cert is the right choice now.

---

## Step 1 — Add the domain to Cloudflare + repoint GoDaddy nameservers (one-time, free)

The built-in tunnel needs Cloudflare to manage the domain's DNS.

**1a. Add the site in Cloudflare**
1. Create a free account at https://dash.cloudflare.com.
2. Click **Add a site** (or **Add a domain**) → type `promptpulse.in` → **Continue**.
3. Choose the **Free** plan → **Continue**.
4. Cloudflare scans and lists your **existing DNS records**. **Verify your current
   company-website records are there** — typically an `A` record for `promptpulse.in`
   (and `www`) pointing at your current host's IP, plus any `MX`/email records. If any are
   missing, click **Add record** and recreate them exactly, or your site/email could drop
   when nameservers switch.
5. Cloudflare shows you **two nameservers** to use, e.g.
   `dana.ns.cloudflare.com` and `rob.ns.cloudflare.com` (yours will differ). Copy both.

**1b. Change nameservers at GoDaddy (exact path)**
1. Sign in at https://dcc.godaddy.com/control/portfolio (or godaddy.com → top-right
   **profile icon** → **My Products**).
2. Under **Domains**, find `promptpulse.in` → click the **three-dot menu (⋯)** on its row →
   **Manage DNS**. (Or click the domain name → **DNS** tab.)
3. Scroll to the **Nameservers** section near the bottom → click **Change** (or **Edit
   Nameservers**).
4. Select **I'll use my own nameservers** (sometimes labelled **Enter my own
   nameservers (advanced)**).
5. Delete GoDaddy's existing nameservers and **paste the two Cloudflare ones** from step
   1a.5. Add a second field if only one box shows.
6. Click **Save**. GoDaddy may ask you to confirm you're moving DNS away — confirm.
7. Back in Cloudflare, click **Done, check nameservers**.

**1c. Wait for activation**
- Propagation is usually **15 min–2 h** (up to 24 h). Cloudflare **emails you** when the
  domain status flips to **Active**. You can keep working on Steps 2–3 meanwhile, but the
  public URL only goes live after activation.

> ⚠️ This moves *all* DNS for promptpulse.in to Cloudflare. That's why step 1a.4 (verifying
> your company-site + email records came across) matters — otherwise the main site or email
> could briefly drop. The records themselves don't change; only *who serves them* does.

---

## Step 2 — Create a named Cloudflare Tunnel

1. In the Cloudflare dashboard → **Zero Trust** → **Networks** → **Tunnels** →
   **Create a tunnel** → type **Cloudflared** → name it `kgpt` → **Save**.
2. On the install screen, **copy the tunnel token** (the long string after `--token`).
   You don't need to run the install command it shows — your Docker setup does that.
3. Go to the tunnel's **Public Hostname** tab → **Add a public hostname**:
   - **Subdomain:** `kgpt`
   - **Domain:** `promptpulse.in`
   - **Service Type:** `HTTP`
   - **URL:** `caddy:8080`
4. Save. Cloudflare auto-creates the `kgpt` DNS record for you.

---

## Step 3 — Wire the token into your stack

1. Open the **root `.env`** (next to `docker-compose.yml`) and add:
   ```
   CLOUDFLARE_TUNNEL_TOKEN=<paste-the-token-from-step-2>
   ```
2. Edit **`docker-compose.tunnel.yml`** → in the `cloudflared` service, swap the quick
   tunnel for the named one. Comment out the quick line and uncomment the token line:
   ```yaml
   cloudflared:
     image: cloudflare/cloudflared:latest
     restart: unless-stopped
     # command: tunnel --no-autoupdate --url http://caddy:8080      # quick (random URL) — OFF
     command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
     depends_on:
       - caddy
   ```

Nothing else needs to change. `frontend/.env.local` stays **empty** (`NEXT_PUBLIC_API_URL=`)
so the browser calls `/api/...` same-origin through Caddy — no CORS, and streaming works.

---

## Step 4 — Bring the stack up (on your PC)

From the repo root, in PowerShell:

```powershell
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml up -d --build
```

Watch the tunnel connect:

```powershell
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml logs -f cloudflared
```

You should see it register 4 connections to Cloudflare. Then open:

**https://kgpt.promptpulse.in** ✅

> **Before going live, set the real keys** in `backend/.env` (per the handoff):
> `ZENMUX_API_KEY` (+ credits), `GEMINI_API_KEY`, `OCR_VISION_*`, `QDRANT_HTTPS=false`,
> `SCHEDULER_ENABLED=true`. Apply the migration `supabase/migrations/008_qwen768_shared_kb.sql`.
> Remember: prompt/code changes only take effect after a rebuild (`--build`).

---

## The "PC now" reality

While hosting on your PC, **the site is only up when your PC + Docker are running**. The
named tunnel auto-reconnects whenever the machine wakes, so the URL stays stable — but if
the PC sleeps or shuts down, `kgpt.promptpulse.in` goes offline until it's back. Fine for a
demo/pilot; not for real users 24/7. To keep it always-on: disable PC sleep, or move to a VPS.

---

## Step 5 — Later: move to a cloud VPS (always-on)

When you want 24/7 uptime, nothing about the domain changes — you just run the **same
compose** on a server:

1. Get a small VPS (Hetzner CX22 ~€4/mo, or DigitalOcean/Vultr ~$6/mo). Pick ≥ 4 GB RAM
   (this stack runs Postgres + Redis + Qdrant + RabbitMQ + Neo4j + 2 app services).
2. Install Docker + Docker Compose on it.
3. Copy the repo + your `.env` files to the VPS (`git clone` + scp the gitignored `.env`s).
4. Run the **exact same command** from Step 4.
5. The tunnel is **outbound**, so it connects from the VPS to Cloudflare automatically —
   the same `kgpt.promptpulse.in` hostname now points at the VPS instead of your PC. No DNS
   change needed.

> Alternative without a tunnel on a VPS: point a Cloudflare `A` record for `kgpt` at the
> VPS public IP and let Caddy terminate HTTPS directly. The tunnel approach is simpler and
> hides your IP, so prefer it unless you have a reason not to.

---

## Quick reference

| Thing | Value |
|---|---|
| Public URL | `https://kgpt.promptpulse.in` |
| One origin (internal) | `caddy:8080` |
| API path | `/api/*` (+ `/docs`, `/openapi.json`, `/metrics`) → `backend:8400` |
| Everything else | → `frontend:3000` |
| Tunnel token env | `CLOUDFLARE_TUNNEL_TOKEN` in root `.env` |
| Start command | `docker compose -f docker-compose.yml -f docker-compose.tunnel.yml up -d --build` |
| Logs | `... logs -f cloudflared` |

---

## Troubleshooting

- **502 / "Bad Gateway" on the URL** → containers not up yet, or Caddy can't reach a
  service. Check `docker compose ps` and `... logs caddy backend frontend`.
- **Tunnel logs show errors / no connections** → token wrong or not loaded. Confirm
  `CLOUDFLARE_TUNNEL_TOKEN` is in the **root** `.env` and the `command:` was switched.
- **Company site went down after Step 1** → a DNS record didn't import. Re-add the
  `promptpulse.in` / `www` records in Cloudflare DNS to match GoDaddy's originals.
- **"failed to fetch" / CORS in the app** → make sure `frontend/.env.local` has
  `NEXT_PUBLIC_API_URL=` **empty** (same-origin via Caddy).
- **Changes not showing** → rebuild: append `--build` (and the service names) to the up
  command; `restart` alone keeps the old image.
