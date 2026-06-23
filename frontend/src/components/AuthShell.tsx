"use client";
/* =============================================================================
 *  K-GPT · AuthShell
 *  Shared wrapper for auth screens: the live divine 3D canvas behind an
 *  ethereal glass card. Keeps each page focused on its own form/logic.
 * ========================================================================== */

import dynamic from "next/dynamic";
import Link from "next/link";
import type { ReactNode } from "react";
import type { BiomeKey } from "@/components/divine/Landscape";

const DivineCanvas = dynamic(() => import("@/components/divine/DivineCanvas"), {
  ssr: false,
  loading: () => null,
});

const TITLE_SHADOW = "0 1px 2px rgba(3,16,28,0.6)";
const TEXT_SHADOW = "0 1px 3px rgba(3,16,28,0.55)";

/** Reusable ethereal field styles for auth forms. */
export const authLabel = "block text-xs font-medium uppercase tracking-wide text-white/70";
export const authInput =
  "w-full rounded-xl border border-white/15 bg-white/10 px-3.5 py-2.5 text-sm text-white placeholder:text-white/40 backdrop-blur-md transition-colors focus:border-white/40 focus:bg-white/15 focus:outline-none";
export const authButton =
  "w-full rounded-xl bg-white/90 px-4 py-2.5 text-sm font-semibold text-slate-900 transition-colors hover:bg-white disabled:opacity-60";
export const authError =
  "rounded-lg border border-red-300/25 bg-red-500/15 px-3 py-2 text-sm text-red-50";

export default function AuthShell({
  biome = "forests",
  title,
  subtitle,
  children,
  footer,
}: {
  biome?: BiomeKey;
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050b12] text-white">
      <div className="fixed inset-0 z-0">
        <DivineCanvas biome={biome} />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/30 via-black/10 to-black/55" />
      </div>

      <header className="relative z-20 flex items-center justify-between px-6 py-5 sm:px-10">
        <Link href="/" className="text-lg font-semibold tracking-[0.12em]" style={{ textShadow: TITLE_SHADOW }}>
          K&nbsp;GPT
        </Link>
        <Link href="/" className="text-sm text-white/80 transition-colors hover:text-white" style={{ textShadow: TEXT_SHADOW }}>
          ← Home
        </Link>
      </header>

      <div className="relative z-10 flex min-h-[calc(100vh-76px)] items-center justify-center px-6 pb-16">
        <div className="w-full max-w-md animate-rise">
          <div className="overflow-hidden rounded-3xl border border-white/12 bg-[#0a1420]/55 p-8 shadow-[0_40px_120px_-40px_rgba(2,10,20,0.9)] backdrop-blur-2xl">
            <h1 className="font-serif text-3xl font-medium tracking-tight" style={{ textShadow: TITLE_SHADOW }}>
              {title}
            </h1>
            {subtitle && (
              <p className="mt-2 text-sm text-white/70" style={{ textShadow: TEXT_SHADOW }}>
                {subtitle}
              </p>
            )}
            <div className="mt-6">{children}</div>
            {footer && (
              <div className="mt-6 text-center text-sm text-white/70" style={{ textShadow: TEXT_SHADOW }}>
                {footer}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
