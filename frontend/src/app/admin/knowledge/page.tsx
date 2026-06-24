"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { Button, Card, Badge } from "@/components/ui/primitives";
import SereneBackdrop from "@/components/SereneBackdrop";
import { api, getToken, clearToken, uploadFile } from "@/lib/api";
import { Database, Upload, Trash2, FileText, ArrowLeft, LogOut, Loader2 } from "lucide-react";

type Doc = { source: string; chunks: number; created_at?: string | null };

export default function KnowledgeBasePage() {
  const router = useRouter();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState<string>("");
  const [toast, setToast] = useState("");
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

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(f.name);
    try {
      const r = await uploadFile(f, undefined, true);   // shared = true
      setToast(`Added "${f.name}" to the knowledge base (${r.chunks_stored} chunks).`);
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
          <Button variant="ghost" size="sm" onClick={() => { clearToken(); router.push("/login"); }}><LogOut size={16} /> Log out</Button>
        </div>
      </div>

      <Card className="mb-6 p-6">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/15 text-brand"><Database size={20} /></span>
          <div className="flex-1">
            <h2 className="text-lg font-semibold">Shared knowledge base</h2>
            <p className="mt-1 text-sm text-muted">
              Documents here are verified by you and used to answer <strong>every</strong> user's questions.
              When a student asks something covered by these files, the AI grounds its answer on them first.
            </p>
            <div className="mt-4">
              <input ref={fileRef} type="file" className="hidden" onChange={onFile}
                accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md" />
              <Button onClick={() => fileRef.current?.click()} disabled={!!uploading}>
                {uploading ? <><Loader2 size={16} className="animate-spin" /> Uploading {uploading}…</> : <><Upload size={16} /> Upload document</>}
              </Button>
            </div>
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
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-brand"><FileText size={16} /></span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{d.source}</div>
                  <div className="text-xs text-muted">{d.chunks} chunk{d.chunks === 1 ? "" : "s"}{d.created_at ? ` · added ${new Date(d.created_at).toLocaleDateString()}` : ""}</div>
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
