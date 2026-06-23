"use client";
/* =============================================================================
 *  K-GPT · ChatInterface.tsx
 *  -----------------------------------------------------------------------------
 *  The floating, "Ethereal Glass" chat panel that hovers over the divine 3D
 *  world. It is a real, working client of the existing FastAPI backend:
 *
 *    • streamChat() (src/lib/api.ts) → POST /api/chat/stream (SSE)
 *    • Request body matches ChatReq:  { message, session_id, persona,
 *      use_memory, web_search }   — exactly what the live backend expects.
 *    • SSE events handled:  session → delta → reasoning → done.
 *    • Auth-aware: streaming requires a campus token, so when none is present
 *      we show a gentle sign-in invitation instead of failing.
 *
 *  Motion: the official useGSAP() hook materialises the panel "like a breath"
 *  on mount using soft sine-wave easing, then keeps it gently floating.
 * ========================================================================== */

import { useRef, useState, useEffect } from "react";
import Link from "next/link";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { Sparkles, Send, Square, Loader2, ArrowUpRight } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { streamChat, getToken } from "@/lib/api";

type Role = "user" | "assistant";
interface Msg {
  role: Role;
  content: string;
  model?: string;
}

/** Soft layered text-shadows keep type razor-sharp over the shifting 3D light. */
const TITLE_SHADOW = "0 1px 2px rgba(3,16,28,0.6)";
const TEXT_SHADOW = "0 1px 3px rgba(3,16,28,0.55)";

const OPENERS = [
  "How do I prepare for KSRMCE semester exams?",
  "Explain gradient descent like I'm new to ML",
  "Summarise my uploaded notes into key points",
  "Give me a 7-day study plan for DBMS",
];

export interface ChatInterfaceProps {
  className?: string;
}

export default function ChatInterface({ className = "" }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [authed, setAuthed] = useState(true); // optimistic; corrected on mount
  const sessionRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Auth presence (token lives in localStorage; only available client-side).
  useEffect(() => {
    setAuthed(!!getToken());
  }, []);

  // Keep the transcript pinned to the newest message.
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  /* ── GSAP: materialise like a breath, then float softly ─────────────────── */
  useGSAP(
    () => {
      const ease = "sine.out";
      // Panel breathes into existence.
      gsap.from(panelRef.current, {
        opacity: 0,
        y: 26,
        scale: 0.985,
        filter: "blur(14px)",
        duration: 1.5,
        ease,
      });
      // Inner elements rise in a gentle, staggered wave.
      gsap.from(".eth-rise", {
        opacity: 0,
        y: 16,
        duration: 1.1,
        ease,
        stagger: 0.09,
        delay: 0.25,
      });
      // Perpetual, near-imperceptible float — starts AFTER the entrance tween
      // finishes so the two don't fight over `y` and cause a jitter on mount.
      gsap.to(panelRef.current, {
        y: "+=8",
        duration: 4.5,
        ease: "sine.inOut",
        yoyo: true,
        repeat: -1,
        delay: 1.7,
      });
    },
    { scope: rootRef },
  );

  /* ── Networking: stream a reply from the live backend ───────────────────── */
  async function runStream(text: string) {
    setStreaming(true);
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamChat(
        {
          message: text,
          session_id: sessionRef.current,
          persona: "kgpt",
          use_memory: true,
          web_search: false,
        },
        // onDelta → append tokens to the in-flight assistant message
        (delta) =>
          setMessages((m) =>
            m.map((msg, i) => (i === m.length - 1 ? { ...msg, content: msg.content + delta } : msg)),
          ),
        // onMeta → session id, final model, etc.
        (meta) => {
          if (meta.event === "session") sessionRef.current = meta.session_id;
          if (meta.event === "done")
            setMessages((m) =>
              m.map((msg, i) => (i === m.length - 1 ? { ...msg, model: meta.model } : msg)),
            );
        },
        ac.signal,
      );
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        setMessages((m) =>
          m.map((msg, i) =>
            i === m.length - 1 ? { ...msg, content: msg.content + `\n\n⚠️ ${e.message}` } : msg,
          ),
        );
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function send(text?: string) {
    const body = (text ?? input).trim();
    if (!body || streaming) return;
    if (!authed) return; // sign-in panel is shown instead
    setInput("");
    if (taRef.current) taRef.current.style.height = "auto";
    setMessages((m) => [...m, { role: "user", content: body }, { role: "assistant", content: "" }]);
    runStream(body);
  }

  function stop() {
    abortRef.current?.abort();
  }

  const empty = messages.length === 0;

  return (
    <div ref={rootRef} className={`w-full ${className}`}>
      <div
        ref={panelRef}
        className="relative mx-auto flex w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-[#0a1420]/70 shadow-[0_40px_120px_-40px_rgba(2,10,20,0.9)] backdrop-blur-2xl"
        style={{ maxHeight: "min(74vh, 640px)" }}
      >
        {/* faint inner light along the top edge — the glass catching the sun */}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/60 to-transparent"
        />

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="eth-rise flex items-center gap-3 border-b border-white/10 px-6 py-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/20 bg-white/10">
            <Sparkles size={17} className="text-white" />
          </span>
          <div className="leading-tight">
            <p
              className="font-serif text-lg font-semibold tracking-tight text-white"
              style={{ textShadow: TITLE_SHADOW }}
            >
              K&nbsp;GPT
            </p>
            <p className="text-[11px] text-white/65" style={{ textShadow: TEXT_SHADOW }}>
              KSRM College of Engineering · Campus AI
            </p>
          </div>
          <span className="ml-auto flex items-center gap-1.5 text-[11px] text-white/60">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-300/90" />
            {streaming ? "thinking" : "online"}
          </span>
        </div>

        {/* ── Transcript ─────────────────────────────────────────────────── */}
        <div ref={listRef} className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {empty ? (
            <div className="eth-rise py-6 text-center">
              <h2
                className="font-serif text-2xl font-medium tracking-tight text-white sm:text-3xl"
                style={{ textShadow: TITLE_SHADOW }}
              >
                How can I help today?
              </h2>
              <p
                className="mx-auto mt-3 max-w-md text-sm text-white/70"
                style={{ textShadow: TEXT_SHADOW }}
              >
                A private campus assistant that remembers your courses and helps you learn, code,
                and prepare for exams.
              </p>
              <div className="mt-6 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                {OPENERS.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    disabled={!authed}
                    className="group flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.04] px-3.5 py-3 text-left text-[13px] text-white/85 transition-colors hover:border-white/25 hover:bg-white/10 disabled:opacity-50"
                    style={{ textShadow: TEXT_SHADOW }}
                  >
                    <span className="flex-1">{q}</span>
                    <ArrowUpRight
                      size={14}
                      className="shrink-0 text-white/40 transition-colors group-hover:text-white/80"
                    />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m, i) => {
              const isLast = i === messages.length - 1;
              return (
                <div
                  key={i}
                  className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}
                >
                  {m.role === "assistant" && (
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/20 bg-white/10">
                      <Sparkles size={13} className="text-white" />
                    </span>
                  )}
                  <div
                    className={
                      m.role === "user"
                        ? "max-w-[82%] rounded-2xl rounded-tr-md border border-white/10 bg-white/15 px-4 py-2.5 text-sm text-white"
                        : "max-w-[86%] rounded-2xl rounded-tl-md text-sm text-white/95"
                    }
                    style={{ textShadow: m.role === "user" ? TEXT_SHADOW : undefined }}
                  >
                    {m.role === "assistant" ? (
                      m.content ? (
                        <div className={`prose-chat ${isLast && streaming ? "stream-caret" : ""}`}>
                          <Markdown content={m.content} />
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-2 text-white/70">
                          <Loader2 size={14} className="animate-spin" /> composing…
                        </span>
                      )
                    ) : (
                      <span className="whitespace-pre-wrap">{m.content}</span>
                    )}
                    {m.role === "assistant" && m.model && (
                      <div className="mt-1.5 text-[10px] uppercase tracking-wide text-white/45">
                        {m.model.split("/").pop()}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* ── Composer / sign-in invitation ──────────────────────────────── */}
        <div className="eth-rise border-t border-white/10 px-4 py-3.5">
          {authed ? (
            <div className="flex items-end gap-2 rounded-2xl border border-white/10 bg-white/[0.05] px-3 py-2">
              <textarea
                ref={taRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onInput={(e) => {
                  const t = e.currentTarget;
                  t.style.height = "auto";
                  t.style.height = Math.min(t.scrollHeight, 132) + "px";
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="Message K GPT…"
                className="max-h-32 flex-1 resize-none bg-transparent py-1.5 text-sm text-white placeholder:text-white/45 focus:outline-none"
                style={{ textShadow: TEXT_SHADOW }}
              />
              {streaming ? (
                <button
                  onClick={stop}
                  aria-label="Stop"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/20 bg-white/10 text-white transition-colors hover:bg-white/20"
                >
                  <Square size={15} />
                </button>
              ) : (
                <button
                  onClick={() => send()}
                  disabled={!input.trim()}
                  aria-label="Send"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/25 bg-white/85 text-slate-900 transition-all hover:bg-white disabled:opacity-40"
                >
                  <Send size={15} />
                </button>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 py-1 text-center">
              <p className="text-sm text-white/80" style={{ textShadow: TEXT_SHADOW }}>
                Sign in with your campus email to begin a private conversation.
              </p>
              <div className="flex gap-2">
                <Link
                  href="/login"
                  className="rounded-xl border border-white/25 bg-white/85 px-4 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-white"
                >
                  Log in
                </Link>
                <Link
                  href="/signup"
                  className="rounded-xl border border-white/20 bg-white/10 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-white/20"
                >
                  Create account
                </Link>
              </div>
            </div>
          )}
          <p
            className="mt-2 text-center text-[10px] text-white/45"
            style={{ textShadow: TEXT_SHADOW }}
          >
            K GPT can make mistakes. Verify important answers.
          </p>
        </div>
      </div>
    </div>
  );
}
