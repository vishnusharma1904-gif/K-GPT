"use client";

const BASE = process.env.NEXT_PUBLIC_API_URL || "";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("kgpt_token");
}
export function setToken(t: string) { window.localStorage.setItem("kgpt_token", t); }
export function clearToken() { window.localStorage.removeItem("kgpt_token"); }

// Pages that should never trigger an auth redirect.
const PUBLIC_PATHS = ["/login", "/signup", "/forgot", "/reset", "/verify", "/s/", "/"];

/** Clear the session and bounce to login on an expired/invalid token, so a 401
 *  becomes a clean redirect instead of an unhandled "Not authenticated" error. */
function handleUnauthorized() {
  if (typeof window === "undefined") return;
  clearToken();
  const p = window.location.pathname;
  const onPublic = p === "/" || PUBLIC_PATHS.some((x) => x !== "/" && p.startsWith(x));
  if (!onPublic) window.location.href = "/login";
}

async function req(path: string, opts: RequestInit = {}) {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error("Your session has expired. Please log in again.");
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  // auth
  signup: (b: any) => req("/api/auth/signup", { method: "POST", body: JSON.stringify(b) }),
  login: (b: any) => req("/api/auth/login", { method: "POST", body: JSON.stringify(b) }),
  me: () => req("/api/auth/me"),
  verifyEmail: (token: string) => req("/api/auth/verify", { method: "POST", body: JSON.stringify({ token }) }),
  resendVerification: () => req("/api/auth/resend-verification", { method: "POST" }),
  forgot: (email: string) => req("/api/auth/forgot", { method: "POST", body: JSON.stringify({ email }) }),
  reset: (token: string, password: string) => req("/api/auth/reset", { method: "POST", body: JSON.stringify({ token, password }) }),
  googleConfig: () => req("/api/auth/google/config"),
  googleLogin: (credential: string) => req("/api/auth/google", { method: "POST", body: JSON.stringify({ credential }) }),

  // chat / sessions
  sessions: (projectId?: string) => req(`/api/chat/sessions${projectId ? `?project_id=${projectId}` : ""}`),
  history: (id: string) => req(`/api/chat/sessions/${id}`),
  patchSession: (id: string, b: any) => req(`/api/chat/sessions/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  deleteSession: (id: string) => req(`/api/chat/sessions/${id}`, { method: "DELETE" }),
  searchMessages: (q: string) => req(`/api/chat/search?q=${encodeURIComponent(q)}`),
  listModels: () => req("/api/chat/models"),
  estimate: (b: any) => req("/api/chat/estimate", { method: "POST", body: JSON.stringify(b) }),
  rateMessage: (message_id: string, feedback: number) => req("/api/chat/feedback", { method: "POST", body: JSON.stringify({ message_id, feedback }) }),
  branch: (sessionId: string, b: any = {}) => req(`/api/chat/sessions/${sessionId}/branch`, { method: "POST", body: JSON.stringify(b) }),

  // account
  usage: () => req("/api/account/usage"),
  claimBonus: () => req("/api/account/claim-bonus", { method: "POST" }),
  getPrefs: () => req("/api/account/preferences"),
  setPrefs: (b: any) => req("/api/account/preferences", { method: "PATCH", body: JSON.stringify(b) }),
  payments: () => req("/api/account/payments"),
  exportData: () => req("/api/account/export"),
  deleteAccount: () => req("/api/account/delete-account", { method: "DELETE" }),

  // memory
  memory: {
    list: (projectId?: string) => req(`/api/memory${projectId ? `?project_id=${projectId}` : ""}`),
    add: (b: any) => req("/api/memory", { method: "POST", body: JSON.stringify(b) }),
    remove: (id: string) => req(`/api/memory/${id}`, { method: "DELETE" }),
  },

  // projects
  projects: {
    list: () => req("/api/projects"),
    create: (b: any) => req("/api/projects", { method: "POST", body: JSON.stringify(b) }),
    get: (id: string) => req(`/api/projects/${id}`),
    update: (id: string, b: any) => req(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
    remove: (id: string) => req(`/api/projects/${id}`, { method: "DELETE" }),
  },

  // share
  share: {
    create: (sessionId: string) => req(`/api/share/${sessionId}`, { method: "POST" }),
    mine: () => req("/api/share/mine"),
    revoke: (token: string) => req(`/api/share/${token}`, { method: "DELETE" }),
    public: (token: string) => req(`/api/share/public/${token}`),
  },

  // billing
  billing: {
    config: () => req("/api/billing/config"),
    plans: () => req("/api/billing/plans"),
    order: (plan = "semester", coupon?: string) => req("/api/billing/order", { method: "POST", body: JSON.stringify({ plan, coupon }) }),
    verify: (b: any) => req("/api/billing/verify", { method: "POST", body: JSON.stringify(b) }),
  },

  // prompts (P24)
  prompts: {
    list: () => req("/api/prompts"),
    create: (b: any) => req("/api/prompts", { method: "POST", body: JSON.stringify(b) }),
    remove: (id: string) => req(`/api/prompts/${id}`, { method: "DELETE" }),
  },

  // tools + sandbox (P36 / P37)
  tools: {
    list: () => req("/api/tools"),
    run: (name: string, args: any = {}) => req("/api/tools/run", { method: "POST", body: JSON.stringify({ name, args }) }),
    execute: (code: string, timeout = 6) => req("/api/tools/execute", { method: "POST", body: JSON.stringify({ code, timeout }) }),
  },

  // study aids (P38)
  study: {
    generate: (b: any) => req("/api/study/generate", { method: "POST", body: JSON.stringify(b) }),
    list: () => req("/api/study"),
    remove: (id: string) => req(`/api/study/${id}`, { method: "DELETE" }),
  },

  // voice (P35) — push-to-talk transcription (flag-gated server side)
  voice: { config: () => req("/api/voice/config") },

  // status (P47)
  status: { public: () => req("/api/status") },

  // feedback / NPS (P50)
  feedback: {
    submit: (b: any) => req("/api/feedback", { method: "POST", body: JSON.stringify(b) }),
    nps: () => req("/api/feedback/nps"),
    list: (kind = "") => req(`/api/feedback/list${kind ? `?kind=${kind}` : ""}`),
  },

  // admin
  admin: {
    stats: () => req("/api/admin/stats"),
    users: () => req("/api/admin/users"),
    search: (q = "", tier = "", subStatus = "") => req(`/api/admin/users/search?q=${encodeURIComponent(q)}&tier=${tier}&sub_status=${subStatus}`),
    analytics: (days = 14) => req(`/api/admin/analytics?days=${days}`),
    log: (id: string) => req(`/api/admin/users/${id}/log`),
    grantAccess: (id: string, months = 6) => req(`/api/admin/users/${id}/grant-access?months=${months}`, { method: "POST" }),
    grantPlan: (ids: string[], plan: string) => req("/api/admin/grant-plan", { method: "POST", body: JSON.stringify({ user_ids: ids, plan }) }),
    resetDaily: (ids: string[]) => req("/api/admin/entitlements/reset-daily", { method: "POST", body: JSON.stringify({ user_ids: ids }) }),
    grantTokens: (ids: string[], tokens: number) => req("/api/admin/entitlements/grant-tokens", { method: "POST", body: JSON.stringify({ user_ids: ids, tokens }) }),
    setTier: (ids: string[], tier: string) => req("/api/admin/entitlements/set-tier", { method: "POST", body: JSON.stringify({ user_ids: ids, tier }) }),
    clearOverride: (ids: string[]) => req("/api/admin/entitlements/clear-override", { method: "POST", body: JSON.stringify({ user_ids: ids }) }),
    refreshBonus: (ids: string[]) => req("/api/admin/entitlements/refresh-bonus", { method: "POST", body: JSON.stringify({ user_ids: ids }) }),
    suspend: (ids: string[], suspended: boolean) => req("/api/admin/entitlements/suspend", { method: "POST", body: JSON.stringify({ user_ids: ids, suspended }) }),
    runNightly: () => req("/api/admin/entitlements/run-nightly", { method: "POST" }),
    coupons: () => req("/api/admin/coupons"),
    createCoupon: (b: any) => req("/api/admin/coupons", { method: "POST", body: JSON.stringify(b) }),
    bulkActivate: (roll_nos: string[], months = 6) => req("/api/admin/bulk-activate", { method: "POST", body: JSON.stringify({ roll_nos, months }) }),
    flags: () => req("/api/admin/flags"),
    setFlag: (key: string, enabled: boolean) => req(`/api/admin/flags/${key}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
    budgets: () => req("/api/admin/budgets"),
    setBudget: (b: any) => req("/api/admin/budgets", { method: "PUT", body: JSON.stringify(b) }),
    enforceBudgets: () => req("/api/admin/budgets/enforce", { method: "POST" }),
    usageLog: (limit = 100) => req(`/api/admin/usage-log?limit=${limit}`),
    // Safety monitoring / safeguarding
    monitor: {
      summary: () => req("/api/admin/monitor/summary"),
      events: (severity = "", reviewed = "", userId = "") =>
        req(`/api/admin/monitor/events?severity=${severity}&reviewed=${reviewed}${userId ? `&user_id=${userId}` : ""}`),
      review: (id: string, notes?: string) =>
        req(`/api/admin/monitor/events/${id}/review`, { method: "POST", body: JSON.stringify({ notes: notes || null }) }),
      sessions: (userId: string) => req(`/api/admin/monitor/users/${userId}/sessions`),
      messages: (userId: string, sessionId: string) =>
        req(`/api/admin/monitor/users/${userId}/sessions/${sessionId}`),
    },
    knowledge: {
      list: () => req("/api/admin/knowledge"),
      remove: (source: string) => req(`/api/admin/knowledge?source=${encodeURIComponent(source)}`, { method: "DELETE" }),
    },
    incidents: () => req("/api/status/incidents"),
    createIncident: (b: any) => req("/api/status/incidents", { method: "POST", body: JSON.stringify(b) }),
    updateIncident: (id: string, b: any) => req(`/api/status/incidents/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  },
};

// Multipart file upload (P29)
export async function uploadFile(file: File, projectId?: string, shared = false) {
  const token = getToken();
  const fd = new FormData();
  fd.append("file", file);
  if (projectId) fd.append("project_id", projectId);
  if (shared) fd.append("shared", "true");
  const res = await fetch(`${BASE}/api/upload`, {
    method: "POST",
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: fd,
  });
  if (res.status === 401) { handleUnauthorized(); throw new Error("Your session has expired. Please log in again."); }
  if (!res.ok) {
    let msg = `Upload failed (${res.status})`;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// Voice transcription (P35) — multipart audio clip -> text
export async function transcribeAudio(blob: Blob) {
  const token = getToken();
  const fd = new FormData();
  fd.append("file", blob, "clip.webm");
  const res = await fetch(`${BASE}/api/voice/transcribe`, {
    method: "POST",
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: fd,
  });
  if (res.status === 401) { handleUnauthorized(); throw new Error("Your session has expired. Please log in again."); }
  if (!res.ok) {
    let msg = `Transcription failed (${res.status})`;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// SSE streaming chat with abort support (P19)
export async function streamChat(
  body: any,
  onDelta: (t: string) => void,
  onMeta: (m: any) => void,
  signal?: AbortSignal,
) {
  const token = getToken();
  const res = await fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
      "ngrok-skip-browser-warning": "69420",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (res.status === 401) { handleUnauthorized(); throw new Error("Your session has expired. Please log in again."); }
  if (!res.ok || !res.body) {
    let msg = `Chat failed (${res.status})`;
    try { const j = await res.json(); msg = j.detail || msg; } catch {}
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const p of parts) {
      const line = p.replace(/^data: /, "").trim();
      if (!line) continue;
      try {
        const evt = JSON.parse(line);
        if (evt.event === "delta") onDelta(evt.text);
        else onMeta(evt);
      } catch (err: any) {
        onDelta(`\n\n[Parse Error: ${err.message}] `);
      }
    }
  }
}
