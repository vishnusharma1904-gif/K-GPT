"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Logo } from "@/components/Logo";
import { Button, Card, Badge } from "@/components/ui/primitives";
import { api, getToken } from "@/lib/api";
import {
  ShieldAlert, ShieldCheck, AlertTriangle, Eye, Check, ArrowLeft,
  MessageSquare, RefreshCw, X, User, Bot, Flag, Ban,
} from "lucide-react";

type Ev = {
  id: string; user_id: string; session_id: string | null; severity: string;
  category: string; score: number; blocked: boolean; snippet: string | null;
  reasons: string | null; reviewed: boolean; created_at: string;
  user_name?: string; user_email?: string; user_plan?: string;
};

const SEV_STYLE: Record<string, string> = {
  high: "bg-danger/15 text-danger",
  medium: "bg-warning/15 text-warning",
  low: "bg-surface-2 text-muted",
};

export default function MonitorPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<any>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [severity, setSeverity] = useState("");
  const [unreviewed, setUnreviewed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");

  // chat viewer
  const [viewUser, setViewUser] = useState<any>(null);
  const [sessions, setSessions] = useState<any[]>([]);
  const [open, setOpen] = useState<any>(null); // { session, messages }
  const [viewerBusy, setViewerBusy] = useState(false);

  async function loadEvents() {
    setLoading(true);
    try {
      const [s, e] = await Promise.all([
        api.admin.monitor.summary(),
        api.admin.monitor.events(severity, unreviewed ? "false" : ""),
      ]);
      setSummary(s); setEvents(e.events || []);
    } catch (err: any) { note(err.message); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api.me().then((m) => {
      if (m.role !== "admin") { router.push("/chat"); return; }
      loadEvents();
      const uid = new URLSearchParams(window.location.search).get("user");
      if (uid) openUser(uid);
    }).catch(() => router.push("/login"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadEvents(); }, [severity, unreviewed]);

  function note(m: string) { setToast(m); setTimeout(() => setToast(""), 3500); }

  async function openUser(userId: string, autoSessionId?: string | null) {
    setViewerBusy(true); setOpen(null);
    try {
      const r = await api.admin.monitor.sessions(userId);
      setViewUser(r.user); setSessions(r.sessions || []);
      if (autoSessionId) openSession(userId, autoSessionId);
    } catch (e: any) { note(e.message); setViewUser(null); setSessions([]); }
    finally { setViewerBusy(false); }
  }

  async function openSession(userId: string, sessionId: string) {
    setViewerBusy(true);
    try {
      const r = await api.admin.monitor.messages(userId, sessionId);
      setOpen(r);
    } catch (e: any) { note(e.message); }
    finally { setViewerBusy(false); }
  }

  async function review(id: string) {
    try { await api.admin.monitor.review(id); setEvents((es) => es.map((e) => e.id === id ? { ...e, reviewed: true } : e)); note("Marked reviewed."); }
    catch (e: any) { note(e.message); }
  }

  const cards = summary ? [
    { label: "Total flags", value: summary.total, icon: Flag, cls: "text-fg" },
    { label: "High severity", value: summary.high, icon: ShieldAlert, cls: "text-danger" },
    { label: "Medium", value: summary.medium, icon: AlertTriangle, cls: "text-warning" },
    { label: "Blocked", value: summary.blocked, icon: Ban, cls: "text-fg" },
    { label: "Unreviewed", value: summary.unreviewed, icon: Eye, cls: "text-brand" },
  ] : [];

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Logo />
          <Badge className="bg-danger/15 text-danger"><ShieldAlert size={13} /> Safety monitor</Badge>
        </div>
        <div className="flex gap-2">
          <Link href="/admin"><Button variant="outline" size="sm"><ArrowLeft size={15} /> Dashboard</Button></Link>
          <Button variant="ghost" size="sm" onClick={loadEvents}><RefreshCw size={15} /> Refresh</Button>
        </div>
      </div>

      <p className="mb-5 text-sm text-muted">
        Auto-detected jailbreak, prompt-injection and safety events for monitored campus
        plans (semester / monthly). High-risk attempts are blocked in real time. Annual
        “public” accounts are not monitored.
      </p>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {cards.map((c, i) => (
          <motion.div key={c.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
            <Card className="p-4">
              <div className="flex items-center gap-2 text-muted"><c.icon size={15} /><span className="text-xs">{c.label}</span></div>
              <div className={`mt-1.5 text-2xl font-black ${c.cls}`}>{c.value ?? 0}</div>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Events feed */}
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b p-3">
            <h2 className="mr-auto font-semibold">Flagged events</h2>
            <select value={severity} onChange={(e) => setSeverity(e.target.value)}
              className="h-8 rounded-lg border border-border bg-surface-2 px-2 text-sm text-fg focus:border-brand focus:outline-none">
              <option value="">All severities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <button onClick={() => setUnreviewed((v) => !v)}
              className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs transition-colors ${unreviewed ? "bg-brand/15 text-brand" : "bg-surface-2 text-muted hover:text-fg"}`}>
              <Eye size={13} /> Unreviewed
            </button>
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {loading ? (
              <div className="space-y-2 p-3">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-16 w-full" />)}</div>
            ) : events.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 p-10 text-center text-muted">
                <ShieldCheck size={28} className="text-success" />
                <p>No flagged events. All clear.</p>
              </div>
            ) : (
              events.map((e) => (
                <div key={e.id} className={`border-b p-3 last:border-0 ${e.reviewed ? "opacity-60" : ""}`}>
                  <div className="flex items-center gap-2">
                    <Badge className={SEV_STYLE[e.severity] || SEV_STYLE.low}>{e.severity}</Badge>
                    <span className="text-xs font-medium text-fg">{e.category}</span>
                    {e.blocked && <span className="chip text-danger"><Ban size={11} /> blocked</span>}
                    <span className="ml-auto text-[11px] text-muted">{new Date(e.created_at).toLocaleString()}</span>
                  </div>
                  <div className="mt-1.5 text-sm font-medium">{e.user_name} <span className="font-normal text-muted">· {e.user_email}</span></div>
                  {e.snippet && <p className="mt-1 line-clamp-2 rounded-md bg-surface-2/60 p-2 text-xs text-muted">“{e.snippet}”</p>}
                  {e.reasons && <p className="mt-1 text-[11px] text-muted/80">{e.reasons}</p>}
                  <div className="mt-2 flex items-center gap-2">
                    <Button size="sm" variant="outline" onClick={() => openUser(e.user_id, e.session_id)}><Eye size={13} /> View chats</Button>
                    {!e.reviewed && <Button size="sm" variant="ghost" onClick={() => review(e.id)}><Check size={13} /> Mark reviewed</Button>}
                    {e.reviewed && <span className="chip text-success"><Check size={11} /> reviewed</span>}
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Chat viewer */}
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 border-b p-3">
            <MessageSquare size={16} className="text-brand" />
            <h2 className="font-semibold">Chat viewer</h2>
            {viewUser && (
              <span className="ml-auto flex items-center gap-2">
                <span className="text-xs text-muted">{viewUser.full_name} · {viewUser.plan || "—"}</span>
                <button onClick={() => { setViewUser(null); setSessions([]); setOpen(null); }} className="text-muted hover:text-fg"><X size={15} /></button>
              </span>
            )}
          </div>

          {!viewUser ? (
            <div className="flex flex-col items-center justify-center gap-2 p-10 text-center text-muted">
              <Eye size={26} />
              <p>Pick “View chats” on a flagged event to inspect a student’s conversations.</p>
            </div>
          ) : open ? (
            <div className="flex h-[60vh] flex-col">
              <div className="flex items-center gap-2 border-b p-2.5">
                <button onClick={() => setOpen(null)} className="text-muted hover:text-fg"><ArrowLeft size={15} /></button>
                <span className="truncate text-sm font-medium">{open.session?.title || "Conversation"}</span>
              </div>
              <div className="flex-1 space-y-3 overflow-y-auto p-3">
                {(open.messages || []).map((m: any, i: number) => (
                  <div key={i} className={`flex gap-2 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                    <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${m.role === "user" ? "bg-surface-2" : "bg-brand/15 text-brand"}`}>
                      {m.role === "user" ? <User size={14} /> : <Bot size={14} />}
                    </div>
                    <div className={`max-w-[82%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${m.role === "user" ? "bg-brand text-brand-fg" : "glass"}`}>
                      {m.content}
                      {m.model && <div className="mt-1 text-[10px] opacity-60">{String(m.model).split("/").pop()}</div>}
                    </div>
                  </div>
                ))}
                {(!open.messages || open.messages.length === 0) && <p className="p-6 text-center text-sm text-muted">Empty conversation.</p>}
              </div>
            </div>
          ) : (
            <div className="max-h-[60vh] overflow-y-auto p-2">
              {viewerBusy && <div className="space-y-2 p-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-10 w-full" />)}</div>}
              {!viewerBusy && sessions.length === 0 && <p className="p-6 text-center text-sm text-muted">No conversations.</p>}
              {sessions.map((s) => (
                <button key={s.id} onClick={() => openSession(viewUser.id, s.id)}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm hover:bg-surface-2">
                  <MessageSquare size={14} className="shrink-0 text-muted" />
                  <span className="flex-1 truncate">{s.title || "Untitled chat"}</span>
                  <span className="text-[11px] text-muted">{s.updated_at ? new Date(s.updated_at).toLocaleDateString() : ""}</span>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>

      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-lg bg-fg px-4 py-2 text-sm text-bg shadow-soft">{toast}</div>}
    </main>
  );
}
