# K-GPT — UI/UX + Backend Upgrade (v1.2)

A significant front-to-back polish pass: an ultra-premium "deep-space aurora glass"
design system, ultra-crisp rendering, and a set of advanced, keyboard-first chat
features — plus safe backend hardening.

## Design system ("4D / 8K", ultra-clear)
- **`globals.css`** rebuilt: refined light/dark token sets, multi-layer glass with
  real depth + inner light, holographic hairline borders (`.holo`), 3D tilt
  utilities (`.tilt`, `.scene`), animated `.aurora-text`, glow, a fine film-grain
  overlay to kill gradient banding (the "8K" crispness), premium scrollbars,
  richer chat-markdown styling (tables, blockquotes, code), a streaming caret,
  skeleton shimmer, and full `prefers-reduced-motion` support.
- **`tailwind.config.ts`**: new `brand-2`/`accent-2`/`bg-2` colors, `glow-lg`,
  `depth` shadows, and `rise`/`scale-in` animations.
- **Gradient buttons** and gradient brand accents across the app.

## Theming
- **Light / Dark / System** toggle (`ThemeToggle`) with a no-flash inline init
  script in `layout.tsx`; preference persisted to `localStorage`.

## Landing page
- Reworked hero with `aurora-text`, 3D **pointer-tilt cards** with moving glare
  (`useTilt`), a stats strip, capability rows, and a holographic CTA.
- Richer, theme-aware `AuroraBackground` (extra aurora layer + holographic sweep).

## Advanced chat features
- **Search overlay** (`⌘/Ctrl+F`): instant chat-title matches + debounced
  message search.
- **Pin / star**: pin chats (float to a "Pinned" group) and pin individual
  messages with a "show pinned" filter. Persisted client-side (no DB migration).
- **Export**: download conversation as Markdown, or Print / Save-as-PDF.
- **Voice input** (push-to-talk mic, Web Speech API) and **read-aloud** TTS on
  assistant replies.
- **Keyboard-first UX**: upgraded command palette (icons, groups, hints),
  a **shortcuts overlay** (`?`), and global shortcuts —
  `⌘K` palette · `⌘F` search · `⌘B` sidebar · `⌘⏎` send ·
  `⌘⇧O` new chat · `⌘⇧R` regenerate · `⌘⇧V` voice.
- **Live artifact canvas** upgraded: reload, open-in-new-tab, download,
  fullscreen, copy, version history.
- Polished message bubbles, suggestion chips on the empty state, streaming caret.

## Backend (safe, additive)
- Registered the previously **orphaned `voice` router** (was never mounted).
- Added a **security-headers middleware** (`X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`). Does not touch CORS or SSE streaming.
- Version → **1.2.0**.

## Run & verify
```bash
cd frontend && npm install && npm run build   # type-checks + production build
cd backend  && uvicorn app.main:app --reload  # API + /docs
```

> Note: the assistant could not execute `npm run build` in its sandbox because the
> connected-folder mount served stale/truncated copies of freshly-written files.
> All changes were verified by reading the canonical files and follow the existing,
> working code patterns. Please run `npm run build` locally to confirm in your env.
