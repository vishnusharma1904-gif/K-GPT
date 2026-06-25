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

/** Renders a chart from a ```chart JSON spec — zero external chart deps (P-backlog
 *  "auto graphs/charts"). The model emits a block like:
 *    ```chart
 *    {"type":"bar","title":"Marks","x":["A","B"],"series":[{"name":"S1","data":[8,9]}]}
 *    ```
 *  Supported types: bar, line, pie. Falls back to showing the raw block on any
 *  parse error so a malformed spec never breaks the message. */
const CHART_COLORS = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4", "#a855f7", "#ec4899"];

function Chart({ code }: { code: string }) {
  let spec: any;
  try { spec = JSON.parse(code); } catch {
    return <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 text-xs">{code}</pre>;
  }
  const type = (spec.type || "bar").toLowerCase();
  const x: string[] = spec.x || spec.labels || [];
  const series = spec.series || (spec.data ? [{ name: spec.name || "", data: spec.data }] : []);
  const W = 560, H = 300, padL = 44, padB = 36, padT = spec.title ? 30 : 12, padR = 12;
  const iw = W - padL - padR, ih = H - padT - padB;
  const allVals = series.flatMap((s: any) => (s.data || []).filter((n: any) => typeof n === "number"));
  const maxV = Math.max(1, ...allVals), minV = Math.min(0, ...allVals);
  const yOf = (v: number) => padT + ih - ((v - minV) / (maxV - minV || 1)) * ih;
  const title = spec.title ? <text x={W / 2} y={18} textAnchor="middle" fontSize="13" fontWeight="600" fill="currentColor">{spec.title}</text> : null;

  const legend = series.length > 1 || type === "pie" ? (
    <div className="mt-1 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[11px] text-muted">
      {(type === "pie" ? x : series.map((s: any) => s.name)).map((label: string, i: number) => (
        <span key={i} className="inline-flex items-center gap-1">
          <span style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} className="inline-block h-2.5 w-2.5 rounded-sm" />{label}
        </span>
      ))}
    </div>
  ) : null;

  let plot: any = null;
  if (type === "pie") {
    const data: number[] = series[0]?.data || [];
    const total = data.reduce((a, b) => a + b, 0) || 1;
    const cx = W / 2, cy = padT + ih / 2, r = Math.min(iw, ih) / 2 - 4;
    let acc = 0;
    plot = data.map((v, i) => {
      const a0 = (acc / total) * 2 * Math.PI - Math.PI / 2; acc += v;
      const a1 = (acc / total) * 2 * Math.PI - Math.PI / 2;
      const large = a1 - a0 > Math.PI ? 1 : 0;
      const p = (a: number) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
      const [x0, y0] = p(a0), [x1, y1] = p(a1);
      return <path key={i} d={`M${cx},${cy} L${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} Z`} fill={CHART_COLORS[i % CHART_COLORS.length]} stroke="var(--surface, #fff)" strokeWidth="1" />;
    });
  } else {
    const n = x.length || Math.max(...series.map((s: any) => (s.data || []).length), 1);
    const slot = iw / n;
    const grid = [0, 0.25, 0.5, 0.75, 1].map((f, i) => {
      const yy = padT + ih - f * ih; const val = (minV + f * (maxV - minV));
      return <g key={i}><line x1={padL} y1={yy} x2={W - padR} y2={yy} stroke="currentColor" strokeOpacity="0.12" /><text x={padL - 6} y={yy + 3} textAnchor="end" fontSize="9" fill="currentColor" opacity="0.6">{Math.round(val * 100) / 100}</text></g>;
    });
    const xlabels = x.map((lab, i) => <text key={i} x={padL + slot * i + slot / 2} y={H - padB + 14} textAnchor="middle" fontSize="9" fill="currentColor" opacity="0.7">{lab}</text>);
    if (type === "line") {
      plot = series.map((s: any, si: number) => {
        const pts = (s.data || []).map((v: number, i: number) => `${padL + slot * i + slot / 2},${yOf(v)}`).join(" ");
        return <polyline key={si} points={pts} fill="none" stroke={CHART_COLORS[si % CHART_COLORS.length]} strokeWidth="2" />;
      });
      plot = [grid, plot, xlabels];
    } else { // bar (grouped)
      const bw = (slot * 0.7) / (series.length || 1);
      plot = [grid, series.map((s: any, si: number) => (s.data || []).map((v: number, i: number) => (
        <rect key={`${si}-${i}`} x={padL + slot * i + slot * 0.15 + bw * si} y={yOf(v)} width={Math.max(1, bw - 1)} height={padT + ih - yOf(v)} fill={CHART_COLORS[si % CHART_COLORS.length]} rx="1.5" />
      ))), xlabels];
    }
  }

  return (
    <figure className="my-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full text-fg" role="img" aria-label={spec.title || "chart"}>{title}{plot}</svg>
      {legend}
    </figure>
  );
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
  if (lang === "chart") return <Chart code={raw.replace(/\n$/, "")} />;

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
        components={{
          code: CodeBlock as any,
          // Wrap tables so wide ones scroll on phones instead of breaking layout.
          table: ({ children }: any) => (
            <div className="my-3 overflow-x-auto">
              <table className="w-full">{children}</table>
            </div>
          ),
        }}
      >
        {normalizeMath(content)}
      </ReactMarkdown>
    </div>
  );
}
