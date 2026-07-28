"use client";
/* =============================================================================
 *  K-GPT · AuthShell
 *  Shared wrapper for auth screens: uses the lightweight SereneBackdrop instead
 *  of heavy WebGL to preserve battery on low-end devices.
 * ========================================================================== */

import Link from "next/link";
import type { ReactNode } from "react";
import SereneBackdrop from "@/components/SereneBackdrop";

export const authLabel = "block text-xs font-medium uppercase tracking-wide text-fg/70";
export const authInput =
  "w-full rounded-xl border border-border bg-surface-2/60 px-3.5 py-2.5 text-sm text-fg placeholder:text-muted backdrop-blur-md transition-colors focus:border-brand/40 focus:bg-surface focus:outline-none";
export const authButton =
  "btn-shine w-full rounded-xl bg-fg px-4 py-2.5 text-sm font-semibold text-bg transition-colors hover:opacity-90 disabled:opacity-60";
export const authError =
  "rounded-lg border border-danger/25 bg-danger/15 px-3 py-2 text-sm text-danger";

export default function AuthShell({
  children,
  title,
  subtitle,
  footer,
  showBack = true,
  biome,
}: {
  children: ReactNode;
  title: string;
  subtitle?: ReactNode;
  footer?: ReactNode;
  showBack?: boolean;
  /** Optional themed-backdrop hint (e.g. "beaches", "forests"). Accepted so auth
   *  pages can pass it; currently decorative. */
  biome?: string;
}) {
  return (
    <main className="relative min-h-dvh overflow-hidden">
      <SereneBackdrop />

      <header className="relative z-20 flex items-center justify-between px-5 py-5 pt-safe sm:px-10">
        <Link href="/" className="text-lg font-semibold tracking-[0.12em] text-fg">
          K&nbsp;GPT
        </Link>
        {showBack && (
          <Link href="/" className="text-sm text-muted transition-colors hover:text-fg">
            ← Home
          </Link>
        )}
      </header>

      <div className="relative z-10 flex min-h-[calc(100dvh-76px)] items-center justify-center px-4 pb-12 sm:px-6 sm:pb-16">
        <div className="w-full max-w-md animate-rise">
          <div className="glass-strong overflow-hidden rounded-3xl p-6 sm:p-8">
            <h1 className="font-serif text-3xl font-medium tracking-tight text-fg">
              {title}
            </h1>
            {subtitle && (
              <p className="mt-2 text-sm text-muted">
                {subtitle}
              </p>
            )}
            <div className="mt-6">{children}</div>
            {footer && (
              <div className="mt-6 text-center text-sm text-muted">
                {footer}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
