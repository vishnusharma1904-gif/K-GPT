"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { Button, Card, Badge } from "@/components/ui/primitives";
import SereneBackdrop from "@/components/SereneBackdrop";
import { api, getToken, clearToken, uploadFile } from "@/lib/api";
import { Database, Upload, Trash2, FileText, ArrowLeft, LogOut, Loader2 } from "lucide-react";

type Doc = {
  source: string; chunks: number; created_at?: string | null;
  scope_branch?: string | null; scope_year?: number | null; scope_section?: string | null;
  status?: string; error?: string | null;
};

const BRANCHES = ["CSE", "CSE (AI & ML)", "CSE (Data Science)", "AI & DS", "ECE", "EEE", "Mechanical", "Civil", "IT"];
const SECTIONS = ["A", "B", "C", "D", "E", "F"];

function scopeLabel(d: Doc): string {
  const parts: string[] = [];
  if (d.scope_branch) parts.push(String(d.scope_branch).toUpperCase());
  if (d.scope_year) parts.push(`Year ${d.scope_year}`);
  if (d.scope_section) parts.push(`Sec ${String(d.scope_section).toUpperCase()}`);
  return parts.length ? parts.join(" · ") : "Everyone";
}

export default function KnowledgeBasePage() {
  const router = useRouter();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState<string>("");
  const [toast, setToast] = useState("");
  const [scope, setScope] = useState<{ branch: string; year: string; section: string }>({ branch: "", year: "", section: "" });
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    try { const r = await api.admin.knowledge.list(); setDocs(r.documents || []); }
    catch (e: any) { setToast(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api.me().then((m) => { if (m.role !== "admin") router.push("/chat"); else load(); })
      .catch(() => router.push("/login"));
  }, [router]);

  // Polling for document processing status
  useEffect(() => {
    const hasActive = docs.some(d => d.status === "pending" || d.status === "processing");
    if (!hasActive) return;

    const timer = window.setInterval(async () => {
      try {
        const r = await api.admin.knowledge.list();
        setDocs(r.documents || []);
      } catch (e: any) {
        console.error("Failed to poll knowledge base list", e);
      }
    }, 2500);

    return () => {
      window.clearInterval(timer);
    };
  }, [docs]);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(f.name);
    try {
      const r = await uploadFile(f, undefined, true, {
        branch: scope.branch || undefined,
        year: scope.year || undefined,
        section: scope.section || undefined,
      });
      const where = scopeLabel({ source: "", chunks: 0, scope_branch: scope.branch || null, scope_year: scope.year ? Number(scope.year) : null, scope_section: scope.section || null });
      if (r.queued) {
        setToast(`Queued "${f.name}" → ${where} for background OCR & indexing.`);
      } else {
        setToast(`Added "${f.name}" → ${where} (${r.chunks_stored} chunks).`);
      }
      await load();
    } catch (err: any) { setToast(`⚠️ ${err.message}`); }
    finally { setUploading(""); if (fileRef.current) fileRef.current.value = ""; setTimeout(() => setToast(""), 4000); }
  }

  async function remove(source: string) {
    if (!window.confirm(`Remove "${source}" from the shared knowledge base? Users will no longer get answers from it.`)) return;
    try { await api.admin.knowledge.remove(source); setToast(`Removed "${source}".`); await load(); }
    catch (e: any) { setToast(`⚠️ ${e.message}`); }
    finally { setTimeout(() => setToast(""), 4000); }
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <SereneBackdrop />
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Logo /><Badge className="bg-brand/15 text-brand">Knowledge Base</Badge>
        </div>
        <div className="flex gap-2">
          <Link href="/admin"><Button variant="outline" size="sm"><ArrowLeft size={15} /> Admin</Button></Link>
          <Button variant="ghost" size="sm" onClick={() => { api.logout().catch(() => {}).finally(() => { clearToken(); router.push("/login"); }); }}><LogOut size={16} /> Log out</Button>
        </div>
      </div>

      <Card className="mb-6 p-6">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/15 text-brand"><Database size={20} /></span>
          <div className="flex-1">
            <h2 className="text-lg font-semibold">Shared knowledge base</h2>
            <p className="mt-1 text-sm text-muted">
              Documents are verified by you and ground students' answers. <strong>Target</strong> a
              document to a cohort below — leave a field blank for "any". Leave all three blank to
              share with <strong>Everyone</strong>. Students only retrieve from docs that match their
              branch / current year / section (or Everyone). Scanned notes, handwritten pages,
              and note photos are OCR'd into the KB too.
            </p>
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <div>
                <label className="mb-1 block text-xs text-muted">Branch</label>
                <select value={scope.branch} onChange={(e) => setScope({ ...scope, branch: e.target.value })}
                  className="h-9 rounded-lg border border-border bg-surface-2 px-2 text-sm text-fg focus:border-brand focus:outline-none">
                  <option value="">Any branch</option>
                  {BRANCHES.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted">Year</label>
                <select value={scope.year} onChange={(e) => setScope({ ...scope, year: e.target.value })}
                  className="h-9 rounded-lg border border-border bg-surface-2 px-2 text-sm text-fg focus:border-brand focus:outline-none">
                  <option value="">Any year</option>
                  {[1, 2, 3, 4, 5].map((y) => <option key={y} value={y}>Year {y}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted">Section</label>
                <select value={scope.section} onChange={(e) => setScope({ ...scope, section: e.target.value })}
                  className="h-9 rounded-lg border border-border bg-surface-2 px-2 text-sm text-fg focus:border-brand focus:outline-none">
                  <option value="">Any section</option>
                  {SECTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <input ref={fileRef} type="file" className="hidden" onChange={onFile}
                accept=".pdf,.docx,.pptx,.xlsx,.xls,.csv,.txt,.md,.png,.jpg,.jpeg,.webp,.bmp,.tiff,.tif" />
              <Button onClick={() => fileRef.current?.click()} disabled={!!uploading}>
                {uploading ? <><Loader2 size={16} className="animate-spin" /> Uploading {uploading}…</> : <><Upload size={16} /> Upload document</>}
              </Button>
            </div>
            <p className="mt-2 text-xs text-muted">
              Target: <span className="font-medium text-fg">{scopeLabel({ source: "", chunks: 0, scope_branch: scope.branch || null, scope_year: scope.year ? Number(scope.year) : null, scope_section: scope.section || null })}</span>
            </p>
          </div>
        </div>
      </Card>

      <Card className="p-0">
        <div className="border-b px-5 py-3 text-sm font-medium">Documents ({docs.length})</div>
        {loading ? (
          <div className="flex items-center gap-2 px-5 py-8 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> Loading…</div>
        ) : docs.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-muted">
             No documents yet. Upload a file above and it becomes available to all users.
          </div>
        ) : (
          <ul className="divide-y">
            {docs.map((d) => (
              <li key={d.source} className="flex items-center gap-3 px-5 py-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-brand"><FileText size={16} /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">{d.source}</span>
                    <Badge className={scopeLabel(d) === "Everyone" ? "bg-surface-2 text-muted" : "bg-brand/15 text-brand"}>{scopeLabel(d)}</Badge>
                    {d.status === "pending" && <Badge className="bg-amber-500/15 text-amber-500 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Queued</Badge>}
                    {d.status === "processing" && <Badge className="bg-amber-500/15 text-amber-500 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Indexing</Badge>}
                    {d.status === "failed" && <Badge className="bg-danger/15 text-danger">Failed</Badge>}
                  </div>
                  {d.status === "failed" && d.error && (
                    <div className="mt-1 text-xs text-danger font-mono bg-danger/5 rounded px-2 py-1 max-w-full overflow-x-auto">
                      {d.error}
                    </div>
                  )}
                  <div className="text-xs text-muted">
                    {d.status === "pending" || d.status === "processing" ? (
                      <span>Processing in background</span>
                    ) : (
                      <span>{d.chunks} chunk{d.chunks === 1 ? "" : "s"}</span>
                    )}
                    {d.created_at ? ` · added ${new Date(d.created_at).toLocaleDateString()}` : ""}
                  </div>
                </div>
                <button onClick={() => remove(d.source)} title="Remove from knowledge base"
                  className="rounded-lg p-2 text-muted transition-colors hover:bg-danger/10 hover:text-danger">
                  <Trash2 size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-xl border border-border bg-surface px-4 py-2 text-sm shadow-lg">
          {toast}
        </div>
      )}
    </main>
  );
}
