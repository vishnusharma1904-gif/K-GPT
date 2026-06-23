"use client";
/* Slash-command menu (P24). Render below the composer when the input starts with
   "/". Filters the user's prompt library (own + shared starters) and inserts the
   selected prompt body. Host wires `onPick` to set the composer value. */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type Prompt = { id: string; slug: string; title: string; body: string; shared?: boolean };

export default function SlashMenu({
  query, onPick, onClose,
}: { query: string; onPick: (body: string) => void; onClose: () => void }) {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [active, setActive] = useState(0);

  useEffect(() => { api.prompts.list().then(setPrompts).catch(() => {}); }, []);

  const filtered = useMemo(() => {
    const q = query.replace(/^\//, "").toLowerCase();
    return prompts.filter((p) =>
      p.slug.toLowerCase().includes(q) || p.title.toLowerCase().includes(q)).slice(0, 8);
  }, [query, prompts]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(filtered.length - 1, a + 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
      else if (e.key === "Enter" && filtered[active]) { e.preventDefault(); onPick(filtered[active].body); }
      else if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filtered, active, onPick, onClose]);

  if (!filtered.length) return null;

  return (
    <div className="glass absolute bottom-full mb-2 left-0 w-80 rounded-xl shadow-soft overflow-hidden z-30">
      <ul className="max-h-64 overflow-auto py-1">
        {filtered.map((p, i) => (
          <li key={p.id}>
            <button onMouseEnter={() => setActive(i)} onClick={() => onPick(p.body)}
              className={`flex w-full flex-col items-start px-3 py-2 text-left ${i === active ? "bg-surface-2" : ""}`}>
              <span className="text-sm font-medium text-fg">
                <span className="text-brand">{p.slug}</span> · {p.title}
              </span>
              <span className="line-clamp-1 text-xs text-muted">{p.body}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
