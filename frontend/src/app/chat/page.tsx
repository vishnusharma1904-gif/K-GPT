"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Logo } from "@/components/Logo";
import { Markdown } from "@/components/Markdown";
import { Citations } from "@/components/Citations";
import { Button } from "@/components/ui/primitives";
import { api, streamChat, uploadFile, clearToken, getToken } from "@/lib/api";
import CommandPalette from "@/components/CommandPalette";
import SlashMenu from "@/components/SlashMenu";
import ArtifactPane, { extractArtifact, type Artifact } from "@/components/ArtifactPane";
import ThemeToggle from "@/components/ThemeToggle";
import SereneBackdrop from "@/components/SereneBackdrop";
import KeyboardShortcuts from "@/components/KeyboardShortcuts";
import { useVoiceInput, useReadAloud } from "@/lib/speech";
import { pins, toMarkdown, downloadText, printConversation } from "@/lib/chatExtras";
import {
  Plus, Send, Trash2, LogOut, User, Sparkles, Menu, X, BookOpen, Code, GraduationCap,
  Search, Square, RefreshCw, Paperclip, Globe, Settings, Share2, ThumbsUp, ThumbsDown,
  Image as ImageIcon, Wand2, PanelRight, Shield, Brain, Copy, Check, ArrowDown,
  Mic, Volume2, VolumeX, Pin, Download, Printer, Keyboard, Star, Loader2, FileText,
} from "lucide-react";

type Msg = { id?: string; role: "user" | "assistant"; content: string; model?: string; citations?: any[]; feedback?: number; reasoning?: string; ts?: number };
type Session = { id: string; title: string; persona: string };

const PERSONAS = [
  { id: "kgpt", name: "K-GPT", icon: Sparkles },
  { id: "tutor", name: "Tutor", icon: BookOpen },
  { id: "coder", name: "Code Mentor", icon: Code },
  { id: "examprep", name: "Exam Prep", icon: GraduationCap },
  { id: "research", name: "Researcher", icon: Search },
];

const MODELS = [
  { id: "", name: "Auto" },
  { id: "fast_chat", name: "Fast" },
  { id: "reasoning", name: "Reasoning" },
  { id: "coding", name: "Coding" },
  { id: "long_context", name: "Long context" },
];

const SUGGESTIONS = [
  { icon: GraduationCap, text: "Make a study plan for my upcoming exams" },
  { icon: Code, text: "Explain this code and suggest improvements" },
  { icon: BookOpen, text: "Summarize my uploaded notes into key points" },
  { icon: Brain, text: "Quiz me with 5 questions on this topic" },
];

export default function ChatPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [persona, setPersona] = useState("kgpt");
  const [category, setCategory] = useState("");
  const [webSearch, setWebSearch] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [sidebar, setSidebar] = useState(true);
  const [me, setMe] = useState<any>(null);
  const [notice, setNotice] = useState("");
  const [models, setModels] = useState<any[]>([]);
  const [canPick, setCanPick] = useState(false);
  const [model, setModel] = useState("");
  const [estimate, setEstimate] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [copiedI, setCopiedI] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [images, setImages] = useState<string[]>([]);
  const [attachment, setAttachment] = useState<{ name: string; status: "uploading" | "ready" | "error"; chunks?: number; msg?: string; shared?: boolean } | null>(null);
  const [shareUpload, setShareUpload] = useState(false);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // --- new feature state ---
  const [pinnedChats, setPinnedChats] = useState<Set<string>>(new Set());
  const [pinnedMsgs, setPinnedMsgs] = useState<Set<string>>(new Set());
  const [showPinned, setShowPinned] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const voice = useVoiceInput((t) => setInput(t));
  const tts = useReadAloud();
  // Gate browser-API-dependent UI until after mount to avoid SSR/client
  // hydration mismatches (SpeechRecognition / speechSynthesis are client-only).
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api.me().then(setMe).catch(() => router.push("/login"));
    api.sessions().then(setSessions).catch(() => {});
    api.listModels().then((r: any) => { setCanPick(r.can_pick); setModels(r.models || []); }).catch(() => {});
    api.usage().then(setUsage).catch(() => {});
    setPinnedChats(pins.chats());
  }, [router]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => { if (activeId) setPinnedMsgs(pins.msgs(activeId)); }, [activeId]);

  // Estimate today's-limit usage (debounced).
  useEffect(() => {
    const t = input.trim();
    if (t.length < 6 || me?.role === "admin") { setEstimate(null); return; }
    const h = setTimeout(() => {
      api.estimate({ message: t, session_id: activeId }).then(setEstimate).catch(() => {});
    }, 600);
    return () => clearTimeout(h);
  }, [input, activeId, me]);

  // Global keyboard shortcuts (skip while typing, except the send combo).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      const t = e.target as HTMLElement;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (mod && e.key === "Enter") { e.preventDefault(); send(); return; }
      if (mod && !e.shiftKey && e.key.toLowerCase() === "f") { e.preventDefault(); setSearchOpen(true); return; }
      if (mod && !e.shiftKey && e.key.toLowerCase() === "b") { e.preventDefault(); setSidebar((v) => !v); return; }
      if (mod && e.shiftKey && e.key.toLowerCase() === "o") { e.preventDefault(); newChat(); return; }
      if (mod && e.shiftKey && e.key.toLowerCase() === "r") { e.preventDefault(); regenerate(); return; }
      if (mod && e.shiftKey && e.key.toLowerCase() === "v") { e.preventDefault(); if (voice.supported) voice.toggle(); return; }
      if (e.key === "Escape" && !typing) setSearchOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input, images, streaming, activeId, voice.supported, voice.listening]);

  async function openSession(id: string) {
    setActiveId(id);
    setShowPinned(false);
    const hist = await api.history(id);
    setMessages(hist.map((m: any) => ({ id: m.id, role: m.role, content: m.content, model: m.model, feedback: m.feedback, ts: m.created_at ? Date.parse(m.created_at) : undefined })));
  }

  function newChat() { setActiveId(null); setMessages([]); setShowPinned(false); tts.stop(); }

  async function runStream(text: string, sessionId: string | null, imgs: string[] = []) {
    setStreaming(true);
    const ac = new AbortController();
    abortRef.current = ac;
    let sid = sessionId;
    try {
      await streamChat(
        { message: text, session_id: sessionId, persona, use_memory: true, web_search: webSearch, category: category || undefined, model: model || undefined, images: imgs.length ? imgs : undefined },
        (delta) => setMessages((m) => m.map((msg, i) => i === m.length - 1 ? { ...msg, content: msg.content + delta } : msg)),
        (meta) => {
          if (meta.event === "session") sid = meta.session_id;
          if (meta.event === "citations") setMessages((m) => m.map((msg, i) => i === m.length - 1 ? { ...msg, citations: meta.citations } : msg));
          if (meta.event === "reasoning") setMessages((m) => m.map((msg, i) => i === m.length - 1 ? { ...msg, reasoning: (msg.reasoning || "") + meta.text } : msg));
          if (meta.event === "done" && meta.usage) setUsage(meta.usage);
          if (meta.event === "done") setMessages((m) => {
            const last = m[m.length - 1];
            const art = extractArtifact(last?.content || "");
            if (art) setArtifact(art);
            return m.map((msg, i) => i === m.length - 1 ? { ...msg, model: meta.model } : msg);
          });
        },
        ac.signal,
      );
      if (sid && sid !== activeId) { setActiveId(sid); api.sessions().then(setSessions); }
    } catch (e: any) {
      if (e.name !== "AbortError")
        setMessages((m) => m.map((msg, i) => i === m.length - 1 ? { ...msg, content: msg.content + `\n\n⚠️ ${e.message}` } : msg));
    } finally { setStreaming(false); abortRef.current = null; }
  }

  async function send() {
    const text = input.trim();
    if ((!text && !images.length) || streaming) return;
    if (estimate && estimate.warn && !estimate.unlimited) {
      const ok = window.confirm(
        `Heads up: this prompt looks like it could use about ${estimate.percent}% of today's limit` +
        (estimate.exceeds ? ` — more than the ~${estimate.remaining_percent}% you have left` : "") +
        `. Continue?`);
      if (!ok) return;
    }
    if (voice.listening) voice.stop();
    const imgs = images;
    setInput(""); setImages([]);
    if (inputRef.current) inputRef.current.style.height = "auto";
    setMessages((m) => [...m, { role: "user", content: text || "(image)", ts: Date.now() }, { role: "assistant", content: "", ts: Date.now() }]);
    await runStream(text, activeId, imgs);
  }

  async function onImage(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setImages((im) => [...im, reader.result as string].slice(0, 4));
    reader.readAsDataURL(f);
    if (imageRef.current) imageRef.current.value = "";
  }

  function stop() { abortRef.current?.abort(); }

  async function regenerate() {
    if (streaming) return;
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    setMessages((m) => {
      const c = [...m];
      if (c[c.length - 1]?.role === "assistant") c[c.length - 1] = { role: "assistant", content: "", ts: Date.now() };
      else c.push({ role: "assistant", content: "", ts: Date.now() });
      return c;
    });
    await runStream(lastUser.content, activeId);
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const asShared = shareUpload && me?.role === "admin";
    setAttachment({ name: f.name, status: "uploading", shared: asShared });
    try {
      const r = await uploadFile(f, undefined, asShared);
      setAttachment({ name: f.name, status: "ready", chunks: r.chunks_stored, shared: asShared });
      if (r.suggested_category) {
        setCategory(r.suggested_category);
        setModel(""); // Clear any specifically chosen model to allow auto-routing
      }
    } catch (err: any) {
      setAttachment({ name: f.name, status: "error", msg: err.message, shared: asShared });
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function share() {
    if (!activeId) return;
    try {
      const { token } = await api.share.create(activeId);
      const url = `${window.location.origin}/s/${token}`;
      await navigator.clipboard.writeText(url);
      setNotice(`Share link copied: ${url}`);
      setTimeout(() => setNotice(""), 6000);
    } catch (e: any) { setNotice(`⚠️ ${e.message}`); }
  }

  async function editBranch(i: number) {
    const msg = messages[i];
    if (!msg || msg.role !== "user" || streaming) return;
    const edited = window.prompt("Edit your message to explore a new branch:", msg.content);
    if (edited == null) return;
    let branchId = activeId;
    try {
      if (activeId && msg.id) {
        const nb = await api.branch(activeId, { message_id: msg.id, title: edited.slice(0, 40) });
        branchId = nb.id; setActiveId(nb.id); api.sessions().then(setSessions);
        setMessages((m) => m.slice(0, i).concat({ role: "user", content: edited }, { role: "assistant", content: "" }));
      } else {
        setMessages((m) => m.slice(0, i).concat({ role: "user", content: edited }, { role: "assistant", content: "" }));
      }
    } catch { setMessages((m) => m.slice(0, i).concat({ role: "user", content: edited }, { role: "assistant", content: "" })); }
    await runStream(edited, branchId);
  }

  async function vote(i: number, val: number) {
    const msg = messages[i];
    if (!msg?.id) return;
    const next = msg.feedback === val ? 0 : val;
    setMessages((m) => { const c = [...m]; c[i] = { ...c[i], feedback: next }; return c; });
    try { await api.rateMessage(msg.id, next); } catch {}
  }

  function copyMsg(i: number, text: string) {
    navigator.clipboard?.writeText(text).then(() => { setCopiedI(i); setTimeout(() => setCopiedI(null), 1500); }).catch(() => {});
  }
  function scrollToBottom() { endRef.current?.scrollIntoView({ behavior: "smooth" }); }
  function onScroll() {
    const el = scrollRef.current; if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
  }

  function togglePinChat(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    pins.toggleChat(id);
    setPinnedChats(pins.chats());
  }
  function togglePinMsg(mid?: string) {
    if (!mid || !activeId) return;
    pins.toggleMsg(activeId, mid);
    setPinnedMsgs(pins.msgs(activeId));
  }

  function exportMd() {
    if (!messages.length) return;
    const title = sessions.find((s) => s.id === activeId)?.title || "K-GPT chat";
    downloadText(`${title.slice(0, 40).replace(/[^\w]+/g, "-")}.md`, toMarkdown(title, messages));
    setNotice("Exported conversation as Markdown."); setTimeout(() => setNotice(""), 3500);
  }
  function printChat() {
    if (!messages.length) return;
    const title = sessions.find((s) => s.id === activeId)?.title || "K-GPT chat";
    printConversation(title, messages);
  }

  async function removeSession(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    await api.deleteSession(id);
    setSessions((s) => s.filter((x) => x.id !== id));
    if (activeId === id) newChat();
  }

  async function claimBonus() {
    try { await api.claimBonus(); const u = await api.usage(); setUsage(u); setNotice("Weekly bonus added to today's limit."); }
    catch (e: any) { setNotice(e.message); }
    finally { setTimeout(() => setNotice(""), 4000); }
  }

  function logout() { clearToken(); router.push("/login"); }

  const pinnedList = useMemo(() => sessions.filter((s) => pinnedChats.has(s.id)), [sessions, pinnedChats]);
  const otherList = useMemo(() => sessions.filter((s) => !pinnedChats.has(s.id)), [sessions, pinnedChats]);
  const visibleMsgs = showPinned ? messages.filter((m) => m.id && pinnedMsgs.has(m.id)) : messages;

  return (
    <div className="flex h-screen overflow-hidden">
      <SereneBackdrop />
      <CommandPalette extra={[
        { id: "newchat", label: "New chat", group: "Chat", icon: Plus, run: newChat },
        { id: "search", label: "Search your chats", group: "Chat", icon: Search, run: () => setSearchOpen(true) },
        { id: "web", label: webSearch ? "Turn web search off" : "Turn web search on", group: "Chat", icon: Globe, run: () => setWebSearch((v) => !v) },
        { id: "export", label: "Export conversation (Markdown)", group: "Chat", icon: Download, run: exportMd },
        { id: "print", label: "Print / Save as PDF", group: "Chat", icon: Printer, run: printChat },
      ]} />
      <KeyboardShortcuts />
      {searchOpen && (
        <SearchOverlay
          sessions={sessions}
          onClose={() => setSearchOpen(false)}
          onOpen={(id) => { setSearchOpen(false); openSession(id); }}
        />
      )}

      <AnimatePresence>
        {sidebar && (
          <motion.aside
            initial={{ x: -288 }} animate={{ x: 0 }} exit={{ x: -288 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="glass z-20 flex w-72 flex-col border-r p-3">
            <div className="flex items-center justify-between px-1 py-2">
              <Logo size={26} />
              <button onClick={() => setSidebar(false)} className="text-muted hover:text-fg"><X size={18} /></button>
            </div>
            <Button onClick={newChat} className="btn-shine mt-2 w-full justify-start"><Plus size={16} /> New chat</Button>
            <button onClick={() => setSearchOpen(true)}
              className="mt-2 flex w-full items-center gap-2 rounded-lg border border-border bg-surface-2/50 px-3 py-2 text-sm text-muted transition-colors hover:text-fg">
              <Search size={14} /> Search chats <kbd className="ml-auto rounded bg-surface px-1.5 py-0.5 text-[10px]">⌘F</kbd>
            </button>

            <div className="mt-4 flex-1 space-y-1 overflow-y-auto">
              {pinnedList.length > 0 && (
                <>
                  <p className="px-3 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-muted/70">Pinned</p>
                  {pinnedList.map((s) => <ChatRow key={s.id} s={s} active={activeId === s.id} pinned onOpen={openSession} onPin={togglePinChat} onDelete={removeSession} />)}
                  <p className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wide text-muted/70">Recent</p>
                </>
              )}
              {otherList.map((s) => <ChatRow key={s.id} s={s} active={activeId === s.id} pinned={false} onOpen={openSession} onPin={togglePinChat} onDelete={removeSession} />)}
              {sessions.length === 0 && <p className="px-3 py-4 text-sm text-muted">No chats yet.</p>}
            </div>

            <div className="border-t pt-3">
              <div className="mb-2 px-1"><ThemeToggle /></div>
              {me?.role === "admin" && (
                <button onClick={() => router.push("/admin")} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-brand transition-colors hover:bg-surface-2"><Shield size={14} /> Admin dashboard</button>
              )}
              <button onClick={() => router.push("/settings")} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2"><Settings size={14} /> Settings</button>
              <button onClick={() => router.push("/account")} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand/20 text-brand"><User size={14} /></div>
                <span className="truncate">{me?.full_name || "Account"}</span>
              </button>
              <button onClick={logout} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2"><LogOut size={14} /> Log out</button>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      <main className="relative flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-3">
            {!sidebar && <button onClick={() => setSidebar(true)} className="text-muted hover:text-fg"><Menu size={20} /></button>}
            <div className="flex gap-1 overflow-x-auto">
              {PERSONAS.map((p) => (
                <button key={p.id} onClick={() => setPersona(p.id)}
                  className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${persona === p.id ? "bg-gradient-to-br from-brand to-brand-2 text-brand-fg shadow-glow" : "text-muted hover:bg-surface-2"}`}>
                  <p.icon size={14} /> {p.name}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {me?.exam_mode && <span className="hidden rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-400 sm:inline">Exam mode</span>}
            {messages.length > 0 && (
              <>
                {pinnedMsgs.size > 0 && (
                  <button onClick={() => setShowPinned((v) => !v)} title="Show pinned messages"
                    className={`flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs transition-colors ${showPinned ? "bg-brand/15 text-brand" : "text-muted hover:bg-surface-2"}`}>
                    <Star size={14} className={showPinned ? "fill-current" : ""} /> {pinnedMsgs.size}
                  </button>
                )}
                <button onClick={exportMd} title="Export as Markdown" className="text-muted hover:text-fg"><Download size={18} /></button>
                <button onClick={printChat} title="Print / Save as PDF" className="hidden text-muted hover:text-fg sm:block"><Printer size={18} /></button>
              </>
            )}
            <button onClick={() => { const e = new KeyboardEvent("keydown", { key: "?" }); window.dispatchEvent(e); }}
              title="Keyboard shortcuts (?)" className="hidden text-muted hover:text-fg sm:block"><Keyboard size={18} /></button>
            {activeId && <button onClick={share} title="Share read-only link" className="text-muted hover:text-fg"><Share2 size={18} /></button>}
            {me && me.sub_status !== "active" && me.role !== "admin" && (
              <Button size="sm" variant="outline" onClick={() => router.push("/account")}>Activate access</Button>
            )}
          </div>
        </header>

        <div ref={scrollRef} onScroll={onScroll} className="relative flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-4 py-6">
            {messages.length === 0 ? (
              <div className="flex h-[60vh] flex-col items-center justify-center text-center">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand/20 to-accent/20 text-brand shadow-glow animate-glow-pulse"><Sparkles size={30} /></div>
                <h2 className="text-3xl font-black tracking-tight">How can I help you, <span className="aurora-text">{me?.full_name?.split(" ")[0] || "there"}</span>?</h2>
                <p className="mt-2 max-w-sm text-muted">Ask anything — write, code, analyze, plan, learn, or get exam-ready. K-GPT remembers what you share.</p>
                <div className="mt-7 grid w-full max-w-xl grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s.text} onClick={() => { setInput(s.text); inputRef.current?.focus(); }}
                      className="lift glass flex items-center gap-2.5 rounded-xl px-3.5 py-3 text-left text-sm text-fg/90 hover:border-brand/40">
                      <s.icon size={16} className="shrink-0 text-brand" /> {s.text}
                    </button>
                  ))}
                </div>
              </div>
            ) : showPinned && visibleMsgs.length === 0 ? (
              <div className="flex h-[40vh] flex-col items-center justify-center text-center text-muted">
                <Star size={28} className="mb-3 opacity-50" />
                <p>No pinned messages in this chat yet.</p>
                <button onClick={() => setShowPinned(false)} className="mt-2 text-sm text-brand hover:underline">Show all messages</button>
              </div>
            ) : (
              visibleMsgs.map((m, vi) => {
                const i = showPinned ? messages.indexOf(m) : vi;
                const isLast = i === messages.length - 1;
                const isPinned = !!m.id && pinnedMsgs.has(m.id);
                return (
                <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  className={`group/msg mb-5 flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                  <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${m.role === "user" ? "bg-surface-2" : "bg-gradient-to-br from-brand/20 to-accent/15 text-brand"}`}>
                    {m.role === "user" ? <User size={16} /> : <Sparkles size={16} />}
                  </div>
                  <div className={`relative max-w-[82%] rounded-2xl px-4 py-2.5 ${m.role === "user" ? "bg-gradient-to-br from-brand to-brand-2 text-brand-fg shadow-glow" : "glass"} ${isPinned ? "ring-1 ring-brand/40" : ""}`}>
                    {isPinned && <Star size={11} className="absolute -left-1.5 -top-1.5 fill-brand text-brand" />}
                    {m.role === "assistant" ? (
                      <>
                        {m.reasoning && <ReasoningBlock text={m.reasoning} live={streaming && isLast && !m.content} />}
                        {m.content
                          ? <div className={streaming && isLast ? "stream-caret" : ""}><Markdown content={m.content} /></div>
                          : (!m.reasoning && streaming && isLast
                              ? <ThinkingIndicator model={model} category={category} />
                              : (!streaming && !m.reasoning ? <span className="text-sm text-muted">Stopped.</span> : null))}
                        {m.citations && <Citations items={m.citations} />}
                        <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted">
                          {m.model && <span className="chip">{m.model.split("/").pop()}</span>}
                          {m.content && !streaming && (
                            <>
                              <button onClick={() => vote(i, 1)} title="Good response" className={m.feedback === 1 ? "text-brand" : "hover:text-fg"}><ThumbsUp size={12} /></button>
                              <button onClick={() => vote(i, -1)} title="Bad response" className={m.feedback === -1 ? "text-danger" : "hover:text-fg"}><ThumbsDown size={12} /></button>
                              {mounted && tts.supported && (
                                <button onClick={() => tts.speak(i, m.content)} title={tts.speakingId === i ? "Stop" : "Read aloud"} className={tts.speakingId === i ? "text-brand" : "hover:text-fg"}>
                                  {tts.speakingId === i ? <VolumeX size={12} /> : <Volume2 size={12} />}
                                </button>
                              )}
                              {m.id && (
                                <button onClick={() => togglePinMsg(m.id)} title={isPinned ? "Unpin" : "Pin message"} className={isPinned ? "text-brand" : "hover:text-fg"}><Pin size={12} /></button>
                              )}
                              {extractArtifact(m.content || "") && (
                                <button onClick={() => setArtifact(extractArtifact(m.content || ""))} title="Open in canvas" className="hover:text-fg"><PanelRight size={12} /></button>
                              )}
                              <button onClick={() => copyMsg(i, m.content)} title="Copy message" className="hover:text-fg">{copiedI === i ? <Check size={12} /> : <Copy size={12} />}</button>
                              {m.ts && <span className="opacity-60">{new Date(m.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}
                            </>
                          )}
                        </div>
                      </>
                    ) : (
                      <div>
                        <p className="whitespace-pre-wrap text-sm">{m.content}</p>
                        {!streaming && (
                          <div className="mt-1 flex items-center gap-3 text-[11px] text-brand-fg/70">
                            <button onClick={() => editBranch(i)} title="Edit & branch" className="hover:text-brand-fg">Edit & branch</button>
                            {m.id && <button onClick={() => togglePinMsg(m.id)} className="hover:text-brand-fg">{isPinned ? "Unpin" : "Pin"}</button>}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </motion.div>
              );})
            )}
            <div ref={endRef} />
          </div>
        </div>

        {!atBottom && messages.length > 0 && (
          <button onClick={scrollToBottom} title="Scroll to latest"
            className="lift absolute bottom-32 left-1/2 z-10 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full glass text-fg shadow-soft hover:bg-surface-2">
            <ArrowDown size={16} />
          </button>
        )}
        <div className="border-t p-4">
          {notice && <p className="mx-auto mb-2 max-w-3xl text-center text-xs text-brand">{notice}</p>}
          <div className="mx-auto max-w-3xl">
            <div className="mb-2 flex items-center gap-2 text-xs">
              <select value={category} onChange={(e) => setCategory(e.target.value)} disabled={!!model}
                title={model ? "Clear the model pick to use smart routing" : "Routing mode"}
                className="h-8 rounded-lg border border-border bg-surface-2 px-2 text-fg focus:border-brand focus:outline-none disabled:opacity-50">
                {MODELS.map((mm) => <option key={mm.id} value={mm.id}>{mm.name}</option>)}
              </select>
              {canPick && (
                <select value={model} onChange={(e) => setModel(e.target.value)}
                  title="Pick a specific model (paid feature) — overrides routing"
                  className="h-8 max-w-[220px] rounded-lg border border-border bg-surface-2 px-2 text-fg focus:border-brand focus:outline-none">
                  <option value="">Auto (smart routing)</option>
                  {Object.entries(models.reduce((acc: any, m: any) => {
                    (acc[m.provider_label] = acc[m.provider_label] || []).push(m); return acc;
                  }, {})).map(([prov, list]: any) => (
                    <optgroup key={prov} label={prov}>
                      {list.map((m: any) => (
                        <option key={m.id} value={m.id} disabled={!m.available}>
                          {m.label}{m.frontier ? ` · ${m.multiplier}×` : ""}{m.available ? "" : " (no key)"}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              )}
              <button onClick={() => setWebSearch((v) => !v)}
                className={`flex items-center gap-1 rounded-lg px-2 py-1 transition-colors ${webSearch ? "bg-brand/15 text-brand" : "text-muted hover:bg-surface-2"}`}>
                <Globe size={13} /> Web
              </button>
              <button onClick={() => fileRef.current?.click()} className="flex items-center gap-1 rounded-lg px-2 py-1 text-muted hover:bg-surface-2">
                <Paperclip size={13} /> Attach
              </button>
              {me?.role === "admin" && (
                <button onClick={() => setShareUpload((v) => !v)}
                  title="When on, the next file you attach is stored in the shared knowledge base — every user's questions will be answered from it."
                  className={`flex items-center gap-1 rounded-lg px-2 py-1 transition-colors ${shareUpload ? "bg-brand/15 text-brand" : "text-muted hover:bg-surface-2"}`}>
                  <Shield size={13} /> {shareUpload ? "Shared KB: ON" : "Shared KB"}
                </button>
              )}
              <input ref={fileRef} type="file" className="hidden" onChange={onFile}
                accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md" />
              <button onClick={() => imageRef.current?.click()} title="Attach image (vision)" className="flex items-center gap-1 rounded-lg px-2 py-1 text-muted hover:bg-surface-2">
                <ImageIcon size={13} /> Image
              </button>
              <input ref={imageRef} type="file" accept="image/*" className="hidden" onChange={onImage} />
              {activeId && messages.length > 1 && (
                <button onClick={async () => {
                  setNotice("Generating summary…");
                  try { await api.study.generate({ kind: "summary", session_id: activeId });
                    setNotice("Saved a summary to Study aids in Settings."); }
                  catch (e: any) { setNotice(`⚠️ ${e.message}`); }
                  finally { setTimeout(() => setNotice(""), 5000); }
                }} title="Generate study aid" className="flex items-center gap-1 rounded-lg px-2 py-1 text-muted hover:bg-surface-2">
                  <Wand2 size={13} /> Study
                </button>
              )}
              <div className="ml-auto flex items-center gap-2">
                {estimate && estimate.warn && !estimate.unlimited && input.trim() && (
                  <span title="Approximate share of today's limit this prompt may use"
                    className={`rounded-full px-2 py-0.5 text-[11px] ${estimate.level === "high" ? "bg-danger/15 text-danger" : estimate.level === "medium" ? "bg-warning/15 text-warning" : "bg-surface-2 text-muted"}`}>
                    ≈ {estimate.percent}% of today{estimate.exceeds ? " · may exceed" : ""}
                  </span>
                )}
                {messages.length > 0 && !streaming && (
                  <button onClick={regenerate} className="flex items-center gap-1 rounded-lg px-2 py-1 text-muted hover:bg-surface-2"><RefreshCw size={13} /> Regenerate</button>
                )}
              </div>
            </div>
            {images.length > 0 && (
              <div className="mb-2 flex gap-2">
                {images.map((src, i) => (
                  <div key={i} className="relative">
                    <img src={src} alt="" className="h-14 w-14 rounded-lg object-cover border border-border" />
                    <button onClick={() => setImages((im) => im.filter((_, j) => j !== i))}
                      className="absolute -right-1.5 -top-1.5 rounded-full bg-surface-2 p-0.5 text-muted hover:text-danger"><X size={12} /></button>
                  </div>
                ))}
              </div>
            )}
            {attachment && (
              <div className="mb-2 flex flex-wrap gap-2">
                <div className={`group flex items-center gap-2 rounded-xl border px-3 py-2 text-xs shadow-sm ${
                  attachment.status === "error"
                    ? "border-danger/40 bg-danger/10 text-danger"
                    : "border-border bg-surface-2 text-fg"}`}>
                  <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${
                    attachment.status === "error" ? "bg-danger/15 text-danger" : "bg-brand/15 text-brand"}`}>
                    {attachment.status === "uploading"
                      ? <Loader2 size={14} className="animate-spin" />
                      : <FileText size={14} />}
                  </span>
                  <div className="flex flex-col leading-tight">
                    <span className="max-w-[220px] truncate font-medium">{attachment.name}</span>
                    <span className="text-[11px] text-muted">
                      {attachment.status === "uploading"
                        ? (attachment.shared ? "Uploading to shared knowledge base…" : "Uploading & indexing…")
                        : attachment.status === "ready"
                        ? (attachment.shared
                            ? `Saved to shared KB · ${attachment.chunks} chunks · all users can ask`
                            : `Ready · ${attachment.chunks} chunks · ask about it`)
                        : (attachment.msg || "Upload failed")}
                    </span>
                  </div>
                  <button onClick={() => setAttachment(null)} title="Remove"
                    className="ml-1 rounded-full p-1 text-muted hover:bg-surface hover:text-danger">
                    <X size={13} />
                  </button>
                </div>
              </div>
            )}
            <div className="relative flex items-end gap-2">
              {input.startsWith("/") && (
                <SlashMenu query={input} onPick={(body) => setInput(body)} onClose={() => {}} />
              )}
              <div className="relative flex-1">
                <textarea
                  ref={inputRef}
                  value={input} onChange={(e) => setInput(e.target.value)} rows={1}
                  onInput={(e) => { const t = e.currentTarget; t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 160) + "px"; }}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !input.startsWith("/")) { e.preventDefault(); (e.currentTarget as HTMLTextAreaElement).style.height = "auto"; send(); } }}
                  placeholder={voice.listening ? "Listening…" : "Message K-GPT…  (/ for prompts, ⌘K for commands)"}
                  className={`max-h-40 w-full resize-none rounded-xl border bg-surface/60 px-4 py-3 pr-12 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30 ${voice.listening ? "border-brand/70" : "border-border"}`} />
                {mounted && voice.supported && (
                  <button onClick={voice.toggle} title="Voice input (⌘⇧V)"
                    className={`absolute bottom-2.5 right-2.5 flex h-7 w-7 items-center justify-center rounded-lg transition-colors ${voice.listening ? "bg-danger/20 text-danger animate-pulse" : "text-muted hover:bg-surface-2 hover:text-fg"}`}>
                    <Mic size={15} />
                  </button>
                )}
              </div>
              {streaming ? (
                <Button onClick={stop} size="lg" variant="outline" className="h-12 w-12 p-0"><Square size={16} /></Button>
              ) : (
                <Button onClick={send} disabled={!input.trim() && !images.length} size="lg" className="btn-shine h-12 w-12 p-0"><Send size={18} /></Button>
              )}
            </div>
          </div>
          {usage && (me?.role !== "admin") && (
            <div className="mx-auto mt-2 flex max-w-3xl items-center justify-center gap-2 text-[11px] text-muted">
              <span className="font-medium text-fg">Daily limit</span>
              <div className="h-1.5 w-32 overflow-hidden rounded-full bg-surface-2">
                <div className={`h-full rounded-full transition-all ${usage.percent_used >= 95 ? "bg-danger" : usage.percent_used >= 75 ? "bg-warning" : "bg-gradient-to-r from-brand to-brand-2"}`}
                  style={{ width: `${Math.min(100, usage.percent_used ?? 0)}%` }} />
              </div>
              <span>{usage.percent_used ?? 0}% used · {usage.state}</span>
              {usage.resets_in_seconds != null && usage.resets_in_seconds > 0 && (
                <span className="text-muted/70">· resets in {Math.floor(usage.resets_in_seconds / 3600)}h {Math.floor((usage.resets_in_seconds % 3600) / 60)}m</span>
              )}
              {usage.weekly_bonus_available && (
                <button onClick={claimBonus} className="ml-1 rounded-full bg-brand/15 px-2 py-0.5 text-brand hover:bg-brand/25">+ weekly bonus</button>
              )}
            </div>
          )}
          {me?.role === "admin" && (
            <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted">Admin · no daily limit</p>
          )}
          {me?.monitored && (
            <p className="mx-auto mt-2 flex max-w-3xl items-center justify-center gap-1.5 text-center text-[11px] text-muted/80">
              <Shield size={11} /> For safety, campus admins may review conversations on student plans.
            </p>
          )}
          <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted">K-GPT can make mistakes. Verify important answers.</p>
        </div>
      </main>

      {artifact && (
        <aside className="hidden w-[44%] max-w-2xl border-l border-border p-3 lg:block">
          <ArtifactPane artifact={artifact} onClose={() => setArtifact(null)} />
        </aside>
      )}
    </div>
  );
}

function ChatRow({ s, active, pinned, onOpen, onPin, onDelete }: {
  s: Session; active: boolean; pinned: boolean;
  onOpen: (id: string) => void; onPin: (id: string, e: React.MouseEvent) => void; onDelete: (id: string, e: React.MouseEvent) => void;
}) {
  return (
    <div onClick={() => onOpen(s.id)}
      className={`group flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${active ? "bg-brand/15 text-fg" : "text-muted hover:bg-surface-2"}`}>
      <span className="truncate">{s.title}</span>
      <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
        <button onClick={(e) => onPin(s.id, e)} title={pinned ? "Unpin" : "Pin"} className={pinned ? "text-brand" : "hover:text-brand"}>
          <Pin size={13} className={pinned ? "fill-current" : ""} />
        </button>
        <button onClick={(e) => onDelete(s.id, e)} title="Delete" className="hover:text-danger"><Trash2 size={13} /></button>
      </div>
    </div>
  );
}

function SearchOverlay({ sessions, onClose, onOpen }: {
  sessions: Session[]; onClose: () => void; onOpen: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const titleHits = useMemo(() => {
    const ql = q.toLowerCase().trim();
    return ql ? sessions.filter((s) => s.title.toLowerCase().includes(ql)).slice(0, 6) : [];
  }, [q, sessions]);

  useEffect(() => {
    const ql = q.trim();
    if (ql.length < 2) { setResults([]); return; }
    setLoading(true);
    const h = setTimeout(() => {
      api.searchMessages(ql).then((r: any) => setResults(Array.isArray(r) ? r.slice(0, 20) : [])).catch(() => setResults([])).finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(h);
  }, [q]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[12vh] backdrop-blur-sm" onClick={onClose}>
      <motion.div initial={{ opacity: 0, y: -10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        className="glass-strong holo w-full max-w-xl overflow-hidden rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-border px-4">
          <Search size={16} className="text-muted" />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search chat titles and messages…"
            className="w-full bg-transparent py-3.5 text-sm text-fg placeholder:text-muted focus:outline-none" />
          <button onClick={onClose} className="text-muted hover:text-fg"><X size={16} /></button>
        </div>
        <div className="max-h-[60vh] overflow-auto p-1.5">
          {titleHits.length > 0 && (
            <>
              <p className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted/70">Chats</p>
              {titleHits.map((s) => (
                <button key={s.id} onClick={() => onOpen(s.id)}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-fg hover:bg-brand/15">
                  <BookOpen size={14} className="text-brand" /> <span className="truncate">{s.title}</span>
                </button>
              ))}
            </>
          )}
          {q.trim().length >= 2 && (
            <p className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted/70">Messages</p>
          )}
          {loading && <div className="space-y-1.5 px-3 py-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-9 w-full" />)}</div>}
          {!loading && results.map((r, i) => (
            <button key={r.id || i} onClick={() => r.session_id && onOpen(r.session_id)}
              className="flex w-full flex-col gap-0.5 rounded-lg px-3 py-2 text-left hover:bg-surface-2">
              <span className="text-[10px] uppercase tracking-wide text-muted/70">{r.role || "message"}</span>
              <span className="line-clamp-2 text-sm text-fg/90">{(r.content || r.text || "").slice(0, 200)}</span>
            </button>
          ))}
          {!loading && q.trim().length >= 2 && results.length === 0 && titleHits.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-muted">No matches found.</p>
          )}
          {q.trim().length < 2 && (
            <p className="px-4 py-6 text-center text-sm text-muted">Type at least 2 characters to search.</p>
          )}
        </div>
      </motion.div>
    </div>
  );
}

function ReasoningBlock({ text, live }: { text: string; live: boolean }) {
  const [open, setOpen] = useState(true);
  useEffect(() => { if (!live) setOpen(false); }, [live]);
  return (
    <div className="mb-2 overflow-hidden rounded-lg border border-border/60 bg-surface-2/40">
      <button onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-muted hover:text-fg">
        <Brain size={12} className={live ? "animate-pulse text-brand" : ""} />
        {live ? "Thinking…" : "Thought process"}
        <span className="ml-auto">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="max-h-60 overflow-auto whitespace-pre-wrap px-3 pb-2 text-xs italic leading-relaxed text-muted">
          {text}
        </div>
      )}
    </div>
  );
}

function ThinkingIndicator({ model, category }: { model?: string; category?: string }) {
  const label = model
    ? "Using " + (model.split("/").pop() || model)
    : category && category !== "" ? "Routing to the best model" : "K-GPT";
  const phrases = [
    "Thinking", "Reading your request", "Reasoning through it",
    "Composing a response", "Putting it together", "Almost there",
  ];
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((x) => (x + 1) % phrases.length), 1700);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2 text-sm text-fg">
        <span className="relative flex h-4 w-4">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand/40" />
          <span className="relative inline-flex h-4 w-4 items-center justify-center rounded-full bg-brand/70" />
        </span>
        <span className="bg-gradient-to-r from-muted via-fg to-muted bg-[length:200%_100%] bg-clip-text text-transparent animate-text-shimmer">
          {phrases[i]}…
        </span>
      </div>
      <span className="pl-6 text-[11px] text-muted">{label}</span>
    </div>
  );
}
