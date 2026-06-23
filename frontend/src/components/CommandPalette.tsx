"use client";
/* Command palette (P28) — ⌘K / Ctrl-K. Keyboard-first navigation and actions.
   Mount once near the app root. Host pages pass `extra` actions; icons + groups
   and fuzzy-ish matching make it a fast power-user surface. */
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus, Settings, User, Activity, Search, CornerDownLeft, ArrowUp, ArrowDown, Command as CmdIcon,
} from "lucide-react";

export type Command = {
  id: string; label: string; hint?: string; group?: string;
  icon?: React.ComponentType<any>; run: () => void;
};

export default function CommandPalette({ extra = [] }: { extra?: Command[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);

  const base: Command[] = useMemo(() => [
    { id: "new", label: "New chat", hint: "C", group: "Navigate", icon: Plus, run: () => router.push("/chat") },
    { id: "settings", label: "Open settings", group: "Navigate", icon: Settings, run: () => router.push("/settings") },
    { id: "account", label: "Account & usage", group: "Navigate", icon: User, run: () => router.push("/account") },
    { id: "status", label: "System status", group: "Navigate", icon: Activity, run: () => router.push("/status") },
  ], [router]);

  const commands = useMemo(() => {
    const all = [...extra, ...base];
    const ql = q.toLowerCase().trim();
    return ql ? all.filter((c) => c.label.toLowerCase().includes(ql)) : all;
  }, [q, extra, base]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setOpen((o) => !o); setQ(""); setActive(0);
      } else if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!open) return null;
  const choose = (c: Command) => { setOpen(false); c.run(); };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-[14vh] backdrop-blur-sm"
        onClick={() => setOpen(false)}>
        <motion.div
          initial={{ opacity: 0, y: -10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          className="glass-strong holo w-full max-w-lg overflow-hidden rounded-2xl"
          onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-2 border-b border-border px-4">
            <Search size={16} className="text-muted" />
            <input autoFocus value={q}
              onChange={(e) => { setQ(e.target.value); setActive(0); }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(commands.length - 1, a + 1)); }
                else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
                else if (e.key === "Enter" && commands[active]) choose(commands[active]);
              }}
              placeholder="Type a command…"
              className="w-full bg-transparent py-3.5 text-sm text-fg placeholder:text-muted focus:outline-none" />
            <kbd className="hidden items-center gap-1 rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted sm:flex"><CmdIcon size={10} />K</kbd>
          </div>
          <ul className="max-h-80 overflow-auto py-1.5">
            {commands.map((c, i) => {
              const Icon = c.icon;
              return (
                <li key={c.id}>
                  <button onClick={() => choose(c)} onMouseEnter={() => setActive(i)}
                    className={`flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors ${i === active ? "bg-brand/15 text-fg" : "text-muted"}`}>
                    <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${i === active ? "bg-brand/20 text-brand" : "bg-surface-2"}`}>
                      {Icon ? <Icon size={14} /> : <CornerDownLeft size={14} />}
                    </span>
                    <span className="flex-1">{c.label}</span>
                    {c.group && <span className="text-[10px] uppercase tracking-wide text-muted/60">{c.group}</span>}
                    {c.hint && <kbd className="rounded bg-surface px-1.5 py-0.5 text-[10px]">{c.hint}</kbd>}
                  </button>
                </li>
              );
            })}
            {!commands.length && <li className="px-4 py-6 text-center text-sm text-muted">No matching commands.</li>}
          </ul>
          <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-[10px] text-muted">
            <span className="flex items-center gap-1"><ArrowUp size={10} /><ArrowDown size={10} /> navigate</span>
            <span className="flex items-center gap-1"><CornerDownLeft size={10} /> select</span>
            <span className="ml-auto">esc to close</span>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
