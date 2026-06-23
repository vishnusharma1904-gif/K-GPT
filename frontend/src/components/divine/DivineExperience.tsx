"use client";
/* =============================================================================
 *  K-GPT · DivineExperience.tsx
 *  -----------------------------------------------------------------------------
 *  The full "divine" surface: a fixed, full-screen 3D world (DivineCanvas) with
 *  four scroll sections — Mountains · Beaches · Waterfalls · Forests — that drive
 *  the active biome via an IntersectionObserver. The biome name lives quietly in
 *  the BACKGROUND as a faint watermark; foreground chrome is minimal and
 *  professional. The ethereal K-GPT chat floats over everything.
 * ========================================================================== */

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ChevronDown, MessageCircle, X } from "lucide-react";
import ChatInterface from "@/components/divine/ChatInterface";
import { DIVINE_CONFIG, BIOME_ORDER, type BiomeKey } from "@/components/divine/Landscape";

const DivineCanvas = dynamic(() => import("@/components/divine/DivineCanvas"), {
  ssr: false,
  loading: () => null,
});

const TEXT_SHADOW = "0 1px 4px rgba(3,16,28,0.6)";
const WORDMARK_SHADOW = "0 2px 10px rgba(3,16,28,0.5)";

export default function DivineExperience() {
  const [biome, setBiome] = useState<BiomeKey>("mountains");
  const [chatOpen, setChatOpen] = useState(false);
  const sectionRefs = useRef<(HTMLElement | null)[]>([]);
  const activeIdx = BIOME_ORDER.indexOf(biome);
  const cfg = DIVINE_CONFIG.biomes[biome];

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            const key = e.target.getAttribute("data-biome") as BiomeKey | null;
            if (key) setBiome(key);
          }
        });
      },
      { threshold: 0.55 },
    );
    sectionRefs.current.forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <main className="relative bg-[#050b12] text-white">
      {/* ── Fixed 3D world ───────────────────────────────────────────────── */}
      <div className="fixed inset-0 z-0">
        <DivineCanvas biome={biome} />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/25 via-transparent to-black/45" />
      </div>

      {/* ── Faint background watermark of the current biome (sits behind UI) ─ */}
      <div aria-hidden className="pointer-events-none fixed inset-0 z-[1] flex items-end overflow-hidden">
        <span
          key={biome}
          className="select-none whitespace-nowrap pb-[8vh] pl-[4vw] font-serif text-[24vw] font-light leading-none tracking-tighter text-white/[0.05]"
          style={{ animation: "kgptFade 1.2s ease both" }}
        >
          {cfg.label}
        </span>
      </div>

      {/* ── Top nav ──────────────────────────────────────────────────────── */}
      <header className="pointer-events-none fixed inset-x-0 top-0 z-30 flex items-center justify-between px-6 py-5 sm:px-10">
        <span
          className="pointer-events-auto text-lg font-semibold tracking-[0.12em]"
          style={{ textShadow: WORDMARK_SHADOW }}
        >
          K&nbsp;GPT
        </span>
        <nav className="pointer-events-auto flex items-center gap-4 text-sm text-white/85">
          <Link href="/chat" className="transition-colors hover:text-white" style={{ textShadow: TEXT_SHADOW }}>
            Open app
          </Link>
          <Link
            href="/login"
            className="rounded-full border border-white/20 bg-white/10 px-4 py-1.5 backdrop-blur-md transition-colors hover:bg-white/20"
            style={{ textShadow: TEXT_SHADOW }}
          >
            Log in
          </Link>
        </nav>
      </header>

      {/* ── Left progress rail + small professional caption ──────────────── */}
      <div className="pointer-events-none fixed left-6 top-1/2 z-20 hidden -translate-y-1/2 flex-col gap-3 sm:flex lg:left-10">
        {BIOME_ORDER.map((k, i) => (
          <div key={k} className="flex items-center gap-3">
            <span
              className={`h-px transition-all duration-500 ${i === activeIdx ? "w-8 bg-white" : "w-4 bg-white/40"}`}
            />
            <span
              className={`text-[11px] uppercase tracking-[0.2em] transition-colors duration-500 ${
                i === activeIdx ? "text-white/90" : "text-white/40"
              }`}
              style={{ textShadow: TEXT_SHADOW }}
            >
              {DIVINE_CONFIG.biomes[k].label}
            </span>
          </div>
        ))}
      </div>

      {/* ── Bottom-left caption for the active biome ─────────────────────── */}
      <div className="pointer-events-none fixed bottom-8 left-6 z-20 max-w-xs sm:left-10 lg:left-20">
        <p className="font-mono text-xs tracking-[0.3em] text-white/55" style={{ textShadow: TEXT_SHADOW }}>
          {String(activeIdx + 1).padStart(2, "0")} / 04
        </p>
        <p
          key={biome}
          className="mt-2 text-sm leading-relaxed text-white/80"
          style={{ textShadow: TEXT_SHADOW, animation: "kgptRise 0.7s ease both" }}
        >
          {cfg.caption}
        </p>
      </div>

      {/* ── Scroll sections (empty spacers; canvas is the star) ──────────── */}
      <div className="pointer-events-none relative z-10">
        {BIOME_ORDER.map((key, i) => (
          <section
            key={key}
            data-biome={key}
            ref={(el) => {
              sectionRefs.current[i] = el;
            }}
            className="min-h-screen"
          />
        ))}
      </div>

      {/* ── Scroll cue ───────────────────────────────────────────────────── */}
      <div
        className={`pointer-events-none fixed bottom-8 left-1/2 z-20 -translate-x-1/2 transition-opacity duration-500 ${
          activeIdx === 0 ? "opacity-100" : "opacity-0"
        }`}
        style={{ textShadow: TEXT_SHADOW }}
      >
        <ChevronDown size={24} className="animate-bounce text-white/70" />
      </div>

      {/* ── Floating chat: right rail (desktop) / bottom sheet (mobile) ──── */}
      <div
        className={`pointer-events-auto fixed z-40 transition-all duration-500
          inset-x-0 bottom-0 px-4 pb-4
          lg:inset-x-auto lg:bottom-auto lg:right-8 lg:top-1/2 lg:w-[440px] lg:-translate-y-1/2 lg:px-0 lg:pb-0
          ${chatOpen ? "" : "max-lg:pointer-events-none max-lg:translate-y-6 max-lg:opacity-0"}`}
      >
        <div className="relative">
          <button
            onClick={() => setChatOpen(false)}
            aria-label="Close chat"
            className="absolute -top-3 right-1 z-10 flex h-8 w-8 items-center justify-center rounded-full border border-white/20 bg-black/40 text-white backdrop-blur-md lg:hidden"
          >
            <X size={15} />
          </button>
          <ChatInterface />
        </div>
      </div>

      {/* ── Mobile launcher ──────────────────────────────────────────────── */}
      <button
        onClick={() => setChatOpen(true)}
        className={`pointer-events-auto fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/20 bg-white/15 px-5 py-3 text-sm font-medium text-white backdrop-blur-md transition-opacity lg:hidden ${
          chatOpen ? "pointer-events-none opacity-0" : "opacity-100"
        }`}
        style={{ textShadow: TEXT_SHADOW }}
      >
        <MessageCircle size={16} /> Ask K&nbsp;GPT
      </button>
    </main>
  );
}
