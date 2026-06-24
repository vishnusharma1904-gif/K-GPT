"use client";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";

/** Renders a Mermaid diagram client-side (P22). Falls back to the code on error. */
function Mermaid({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
        const id = "m" + Math.random().toString(36).slice(2);
        const { svg } = await mermaid.render(id, code);
        if (alive && ref.current) ref.current.innerHTML = svg;
      } catch {
        if (alive) setErr(true);
      }
    })();
    return () => { alive = false; };
  }, [code]);
  if (err) return <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 text-xs">{code}</pre>;
  return <div ref={ref} className="my-3 flex justify-center overflow-x-auto" />;
}

/** Recursively pull plain text out of React children (syntax-highlighting wraps
 *  code in <span> nodes, so String(children) would yield "[object Object]"). */
function extractText(node: any): string {
  if (node == null || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (typeof node === "object" && node.props) return extractText(node.props.children);
  return "";
}

function CodeBlock({ className, children }: any) {
  const [copied, setCopied] = useState(false);
  const raw = extractText(children);
  const lang = /language-(\w+)/.exec(className || "")?.[1];

  if (lang === "mermaid") return <Mermaid code={raw.replace(/\n$/, "")} />;

  // Inline code (no language, single line) → render plainly.
  if (!className && !raw.includes("\n")) {
    return <code className="rounded bg-surface-2 px-1.5 py-0.5 text-[0.85em]">{children}</code>;
  }
  async function copy() {
    try { await navigator.clipboard.writeText(raw); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {}
  }
  return (
    <div className="group relative my-3">
      <button onClick={copy}
        className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded-md bg-surface-2/90 px-2 py-1 text-[11px] text-muted opacity-0 transition-opacity group-hover:opacity-100 hover:text-fg">
        {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? "Copied" : "Copy"}
      </button>
      <pre className="overflow-x-auto rounded-lg bg-[#0d1117] p-3 text-xs leading-relaxed">
        <code className={className}>{children}</code>
      </pre>
    </div>
  );
}

/** Normalise LaTeX delimiters so KaTeX renders regardless of which style the
 *  model emits: \(...\) -> $...$ (inline) and \[...\] -> $$...$$ (display).
 *  remark-math only understands $ / $$, so models that use the \( \[ style
 *  would otherwise show raw. Skips fenced code blocks. */
function normalizeMath(src: string): string {
  if (!src) return src;
  const parts = src.split(/(```[\s\S]*?```|`[^`]*`)/g);
  return parts
    .map((seg, i) =>
      i % 2 === 1 // odd segments are code (kept verbatim)
        ? seg
        : seg
            .replace(/\\\[([\s\S]+?)\\\]/g, (_m, e) => `$$${e}$$`)
            .replace(/\\\(([\s\S]+?)\\\)/g, (_m, e) => `$${e}$`)
    )
    .join("");
}

export function Markdown({ content }: { content: string }) {
  return (
    <div className="prose-chat text-sm">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, [rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{ code: CodeBlock as any }}
      >
        {normalizeMath(content)}
      </ReactMarkdown>
    </div>
  );
}
