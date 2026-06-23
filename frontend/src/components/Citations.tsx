"use client";
import { BookOpen, Globe } from "lucide-react";

type Citation = {
  type: "memory" | "web";
  source?: string; title?: string; url?: string; snippet?: string; n?: number;
};

/** Inline source chips for RAG/web-grounded answers (P32). */
export function Citations({ items }: { items: Citation[] }) {
  if (!items?.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {items.map((c, i) =>
        c.type === "web" ? (
          <a key={i} href={c.url} target="_blank" rel="noopener noreferrer nofollow"
            title={c.snippet || c.title}
            className="inline-flex max-w-[220px] items-center gap-1 truncate rounded-full border border-border bg-surface-2/60 px-2 py-0.5 text-[11px] text-muted hover:text-brand">
            <Globe size={11} /> <span className="truncate">{c.title || c.url}</span>
          </a>
        ) : (
          <span key={i} title={c.snippet}
            className="inline-flex max-w-[220px] items-center gap-1 truncate rounded-full border border-border bg-surface-2/60 px-2 py-0.5 text-[11px] text-muted">
            <BookOpen size={11} /> <span className="truncate">{c.source || "memory"}</span>
          </span>
        ),
      )}
    </div>
  );
}
