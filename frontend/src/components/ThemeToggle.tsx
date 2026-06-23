"use client";
/* Theme toggle — cycles dark → light → system, persisted, no-flash.
   Pairs with the inline init script in layout.tsx. */
import { useEffect, useState } from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { getTheme, setTheme, applyTheme, type Theme } from "@/lib/theme";

const ORDER: Theme[] = ["dark", "light", "system"];
const ICON = { dark: Moon, light: Sun, system: Monitor } as const;
const LABEL = { dark: "Dark", light: "Light", system: "System" } as const;

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [theme, setT] = useState<Theme>("dark");

  useEffect(() => {
    const t = getTheme();
    setT(t);
    applyTheme(t);
    // Keep "system" in sync with OS changes.
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => { if (getTheme() === "system") applyTheme("system"); };
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  function cycle() {
    const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    setT(next);
    setTheme(next);
  }

  const Icon = ICON[theme];
  return (
    <button
      onClick={cycle}
      title={`Theme: ${LABEL[theme]} (click to change)`}
      aria-label={`Theme: ${LABEL[theme]}`}
      className="lift flex h-9 items-center gap-2 rounded-lg border border-border bg-surface-2/60 px-2.5 text-muted transition-colors hover:text-fg"
    >
      <Icon size={16} />
      {!compact && <span className="text-xs font-medium">{LABEL[theme]}</span>}
    </button>
  );
}
