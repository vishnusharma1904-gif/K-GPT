"use client";
/* Artifacts / Canvas (P23) — a live side panel for generated HTML/code.

   `extractArtifact()` scans an assistant reply for a fenced ```html / ```svg
   block (or a full HTML document) and returns runnable source. The pane renders
   it in a sandboxed iframe (no same-origin, no top navigation), keeps a version
   history, and supports refresh, download, open-in-new-tab and fullscreen. */
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/primitives";
import {
  RefreshCw, Download, ExternalLink, Maximize2, Minimize2, Copy, Check, X, Code2, Eye,
} from "lucide-react";

export type Artifact = { lang: "html" | "svg" | "code"; code: string; title: string };

const FENCE = /```(html|svg|xml|jsx|tsx|javascript|js)\s*\n([\s\S]*?)```/i;

export function extractArtifact(reply: string): Artifact | null {
  const trimmed = reply.trim();
  if (/^<!doctype html|^<html[\s>]/i.test(trimmed)) {
    return { lang: "html", code: trimmed, title: "Document" };
  }
  const m = reply.match(FENCE);
  if (!m) return null;
  const lang = m[1].toLowerCase();
  const code = m[2].trim();
  if (lang === "svg" || lang === "xml") return { lang: "svg", code, title: "SVG" };
  if (lang === "html") return { lang: "html", code, title: "Web page" };
  return { lang: "code", code, title: "Code" };
}

function toSrcDoc(a: Artifact): string {
  if (a.lang === "html") return a.code;
  if (a.lang === "svg")
    return `<!doctype html><html><body style="margin:0;display:grid;place-items:center;height:100vh;background:#0b0b12">${a.code}</body></html>`;
  return `<!doctype html><html><body style="margin:0;padding:16px;font:13px/1.5 ui-monospace,monospace;background:#0b0b12;color:#e6e6f0"><pre>${a.code
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")}</pre></body></html>`;
}

const EXT = { html: "html", svg: "svg", code: "txt" } as const;

export default function ArtifactPane({
  artifact, onClose,
}: { artifact: Artifact; onClose: () => void }) {
  const [versions, setVersions] = useState<Artifact[]>([artifact]);
  const [idx, setIdx] = useState(0);
  const [tab, setTab] = useState<"preview" | "code">("preview");
  const [copied, setCopied] = useState(false);
  const [full, setFull] = useState(false);
  const [nonce, setNonce] = useState(0); // forces iframe reload
  const lastKey = useRef("");

  useEffect(() => {
    const key = artifact.code;
    if (key && key !== lastKey.current) {
      lastKey.current = key;
      setVersions((v) => (v[v.length - 1]?.code === key ? v : [...v, artifact]));
      setIdx((i) => (versions[versions.length - 1]?.code === key ? i : versions.length));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifact]);

  const current = versions[idx] ?? artifact;

  function copy() {
    navigator.clipboard?.writeText(current.code).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }
  function download() {
    const blob = new Blob([current.code], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `kgpt-artifact.${EXT[current.lang]}`;
    a.click();
    URL.revokeObjectURL(url);
  }
  function openTab() {
    const w = window.open();
    if (!w) return;
    // SECURITY: the artifact is untrusted (model-generated) code. Render it inside
    // a sandboxed, null-origin iframe so it can never reach this app's origin,
    // cookies, or the auth token in localStorage — even in the new tab.
    const doc = toSrcDoc(current).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
    const shell =
      '<!doctype html><html><head><meta charset="utf-8"><title>K-GPT artifact</title>' +
      "<style>html,body{margin:0;height:100%}iframe{border:0;width:100%;height:100%}</style></head>" +
      '<body><iframe sandbox="allow-scripts allow-popups allow-forms" srcdoc="' +
      doc +
      '"></iframe></body></html>';
    w.document.open();
    w.document.write(shell);
    w.document.close();
  }

  const wrap = full
    ? "fixed inset-3 z-[60]"
    : "flex h-full w-full";

  return (
    <div className={`${wrap} flex flex-col glass-strong rounded-2xl overflow-hidden`}>
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-fg">{current.title}</span>
          <span className="chip text-muted">{current.lang.toUpperCase()}</span>
          <div className="flex rounded-lg bg-surface-2 p-0.5 text-xs">
            <button onClick={() => setTab("preview")}
              className={`flex items-center gap-1 rounded-md px-2 py-1 ${tab === "preview" ? "bg-gradient-to-br from-brand to-brand-2 text-brand-fg" : "text-muted"}`}><Eye size={12} /> Preview</button>
            <button onClick={() => setTab("code")}
              className={`flex items-center gap-1 rounded-md px-2 py-1 ${tab === "code" ? "bg-gradient-to-br from-brand to-brand-2 text-brand-fg" : "text-muted"}`}><Code2 size={12} /> Code</button>
          </div>
        </div>
        <div className="flex items-center gap-0.5 text-muted">
          {versions.length > 1 && (
            <div className="mr-1 flex items-center gap-1 text-xs">
              <button disabled={idx === 0} onClick={() => setIdx((i) => Math.max(0, i - 1))}
                className="rounded px-1.5 py-0.5 hover:bg-surface-2 disabled:opacity-40">‹</button>
              <span>v{idx + 1}/{versions.length}</span>
              <button disabled={idx === versions.length - 1} onClick={() => setIdx((i) => Math.min(versions.length - 1, i + 1))}
                className="rounded px-1.5 py-0.5 hover:bg-surface-2 disabled:opacity-40">›</button>
            </div>
          )}
          <IconBtn title="Reload preview" onClick={() => setNonce((n) => n + 1)}><RefreshCw size={15} /></IconBtn>
          <IconBtn title="Open in new tab" onClick={openTab}><ExternalLink size={15} /></IconBtn>
          <IconBtn title="Download" onClick={download}><Download size={15} /></IconBtn>
          <IconBtn title="Copy code" onClick={copy}>{copied ? <Check size={15} className="text-success" /> : <Copy size={15} />}</IconBtn>
          <IconBtn title={full ? "Exit fullscreen" : "Fullscreen"} onClick={() => setFull((f) => !f)}>{full ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</IconBtn>
          <IconBtn title="Close" onClick={onClose}><X size={16} /></IconBtn>
        </div>
      </div>
      <div className="flex-1 overflow-auto bg-[#0b0b12]">
        {tab === "preview" ? (
          <iframe key={nonce} title="artifact" sandbox="allow-scripts allow-popups allow-forms"
            className="h-full w-full border-0" srcDoc={toSrcDoc(current)} />
        ) : (
          <pre className="p-4 text-xs text-fg whitespace-pre-wrap break-words">{current.code}</pre>
        )}
      </div>
    </div>
  );
}

function IconBtn({ children, title, onClick }: { children: React.ReactNode; title: string; onClick: () => void }) {
  return (
    <button title={title} onClick={onClick}
      className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-surface-2 hover:text-fg">
      {children}
    </button>
  );
}
