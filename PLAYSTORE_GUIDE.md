# Shipping K-GPT to the Google Play Store

K-GPT is a Next.js web app with a PWA manifest, so the cheapest, fastest path to
an Android app is a **TWA (Trusted Web Activity)** — a thin native wrapper that
runs your live website full-screen with no browser bar. You do **not** rewrite
the app; you wrap it. This is officially supported by Google and passes review.

> A full React Native / native rewrite is *not* recommended — it's months of work
> to re-create what you already have. Use a TWA. (Capacitor is a middle option if
> you later need device features like push notifications or offline mode.)

---

## The one hard prerequisite: a stable, owned HTTPS domain

A TWA verifies ownership via **Digital Asset Links**, which requires a domain
**you control** served over **HTTPS**. This means:

- The Cloudflare *quick* tunnel (`random.trycloudflare.com`) **will not work** — the
  URL changes every restart and you don't own that domain.
- You need K-GPT deployed at a fixed address like `https://kgpt.yourdomain.com`.

Get there with either:
- **A small VPS** (Hetzner/DigitalOcean/Oracle free tier) running your
  `docker compose` stack, with a domain's DNS pointed at it and Caddy doing
  automatic HTTPS; **or**
- **A Cloudflare *named* tunnel** on your own domain (the commented block in
  `docker-compose.tunnel.yml`) — also gives a permanent HTTPS URL.

Everything below assumes you have that stable URL.

---

## Step 1 — Finish the PWA so it's installable

1. Add the two icon files to `frontend/public/` (they're referenced by the
   manifest but currently missing): `icon-192.png` and `icon-512.png`. Use a real
   K-GPT logo at 192×192 and 512×512 (the placeholders provided will do to start).
2. Confirm `frontend/public/manifest.webmanifest` is complete — yours already has
   `name`, `short_name`, `start_url`, `display: standalone`, colors, and maskable
   icons. Good.
3. Deploy, then open the site in Chrome on desktop → DevTools → **Application →
   Manifest / Lighthouse PWA** audit. Fix anything it flags. The TWA tools require
   a passing installable PWA.

---

## Step 2 — Generate the Android app (TWA)

**Easiest — PWABuilder (web UI, no tooling):**
1. Go to `https://www.pwabuilder.com`, enter your `https://kgpt.yourdomain.com`.
2. It scores your PWA; fix anything red.
3. Click **Package for Stores → Android → Generate**. You get:
   - `app-release-bundle.aab` (the file you upload to Play),
   - a signing key (`signing.keystore`) — **back this up; you can't update the app
     without it**,
   - an `assetlinks.json`.

**Or — Bubblewrap (CLI, more control):**
```bash
npm i -g @bubblewrap/cli
bubblewrap init --manifest https://kgpt.yourdomain.com/manifest.webmanifest
bubblewrap build        # produces app-release-bundle.aab + signing key
```

---

## Step 3 — Verify domain ownership (Digital Asset Links)

So the app opens without a URL bar, host the asset-links file on your domain at:

```
https://kgpt.yourdomain.com/.well-known/assetlinks.json
```

PWABuilder/Bubblewrap give you the exact JSON (it contains your app's package
name + the signing key's SHA-256 fingerprint). In Next.js, put it at
`frontend/public/.well-known/assetlinks.json` so it's served at that path.

---

## Step 4 — Play Console + listing

1. Create a **Google Play Console** account — one-time **$25** fee.
2. **Create app**, then complete the required forms (Play won't publish without
   them):
   - **Store listing**: app name, short + full description, a 512×512 app icon, a
     feature graphic (1024×500), and at least 2 phone screenshots.
   - **Privacy Policy URL** — *mandatory* because K-GPT has user accounts and
     processes their data. Host a simple policy page (you can add a `/privacy`
     route to the app).
   - **Data safety** form — declare what you collect (email, chats) and how it's
     used/stored.
   - **Content rating** questionnaire and **Target audience** (note: if any users
     are under 18, extra "Families" policies apply).
3. **Upload** the `.aab` to a release (start with **Internal testing** → then
   Production).
4. Submit for review. First review typically takes a few days.

---

## Realistic checklist before you submit

- [ ] App is live at a stable HTTPS domain you own
- [ ] `icon-192.png` + `icon-512.png` present; Lighthouse PWA audit passes
- [ ] `.well-known/assetlinks.json` served on the domain
- [ ] Signing key backed up safely (losing it = can't update the app ever)
- [ ] Privacy policy page published and linked
- [ ] Data safety + content rating forms completed
- [ ] Screenshots + feature graphic + 512 icon prepared

---

## A note on "app feel"

Because it's a TWA over your responsive web UI, the recent mobile-friendly
changes matter a lot — the drawer sidebar, scrollable header, and touch-sized
controls are what make it feel like a real app rather than a shrunken website.
Test the live site thoroughly on a phone *before* packaging.
