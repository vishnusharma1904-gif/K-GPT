"use client";
/* Keyboard shortcuts help — press "?" (Shift+/) to toggle. Ignores typing in
   inputs/textareas so it never interrupts composing a message. */
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Keyboard, X } from "lucide-react";

const GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: "General",
    items: [
      ["⌘ / Ctrl + K", "Open command palette"],
      ["?", "Toggle this help"],
      ["Esc", "Close panels / stop input"],
    ],
  },
  {
    title: "Chat",
    items: [
      ["Enter", "Send message"],
      ["Shift + Enter", "New line"],
      ["⌘ / Ctrl + Enter", "Send (from anywhere)"],
      ["/", "Insert a saved prompt"],
      ["⌘ / Ctrl + F", "Search your chats"],
      ["⌘ / Ctrl + B", "Toggle sidebar"],
    ],
  },
  {
    title: "Compose",
    items: [
      ["⌘ / Ctrl + Shift + V", "Voice input (push-to-talk)"],
      ["⌘ / Ctrl + Shift + R", "Regenerate last reply"],
      ["⌘ / Ctrl + Shift + O", "New chat"],
    ],
  },
];

export default function KeyboardShortcuts() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (e.key === "?" && !typing) { e.preventDefault(); setOpen((o) => !o); }
      else if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setOpen(false)}>
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 360, damping: 28 }}
            className="glass-strong holo w-full max-w-2xl overflow-hidden rounded-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
              <div className="flex items-center gap-2 font-semibold">
                <Keyboard size={18} className="text-brand" /> Keyboard shortcuts
              </div>
              <button onClick={() => setOpen(false)} className="text-muted hover:text-fg"><X size={18} /></button>
            </div>
            <div className="grid grid-cols-1 gap-6 p-5 sm:grid-cols-3">
              {GROUPS.map((g) => (
                <div key={g.title}>
                  <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-muted">{g.title}</h3>
                  <ul className="space-y-2">
                    {g.items.map(([k, label]) => (
                      <li key={k} className="flex items-center justify-between gap-3 text-sm">
                        <span className="text-muted">{label}</span>
                        <kbd className="shrink-0 rounded-md border border-border bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-fg">{k}</kbd>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
