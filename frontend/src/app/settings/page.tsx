"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Logo } from "@/components/Logo";
import { Button, Card } from "@/components/ui/primitives";
import { api, getToken } from "@/lib/api";
import SereneBackdrop from "@/components/SereneBackdrop";
import { ArrowLeft, Trash2, Download, Shield, Brain, Sliders } from "lucide-react";

const STYLES = ["concise", "balanced", "detailed", "formal"];

export default function SettingsPage() {
  const router = useRouter();
  const [prefs, setPrefs] = useState<any>(null);
  const [notes, setNotes] = useState<any[]>([]);
  const [payments, setPayments] = useState<any[]>([]);
  const [saved, setSaved] = useState("");

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api.getPrefs().then(setPrefs).catch(() => {});
    api.memory.list().then(setNotes).catch(() => {});
    api.payments().then(setPayments).catch(() => {});
  }, [router]);

  async function save(patch: any) {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    try { await api.setPrefs(patch); setSaved("Saved"); setTimeout(() => setSaved(""), 1500); } catch {}
  }

  async function delNote(id: string) {
    await api.memory.remove(id);
    setNotes((n) => n.filter((x) => x.id !== id));
  }

  async function exportData() {
    const data = await api.exportData();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "kgpt-my-data.json";
    a.click();
  }

  async function deleteAccount() {
    if (!confirm("Permanently delete your account and all data? This cannot be undone.")) return;
    await api.deleteAccount();
    localStorage.removeItem("kgpt_token");
    router.push("/");
  }

  if (!prefs) return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <SereneBackdrop />
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3"><Logo size={24} /><h1 className="text-xl font-bold">Settings</h1></div>
        <Button variant="ghost" size="sm" onClick={() => router.push("/chat")}><ArrowLeft size={16} /> Back to chat</Button>
      </div>
      {saved && <p className="mb-3 text-sm text-brand">{saved}</p>}

      <Card className="mb-5 p-5">
        <h2 className="mb-4 flex items-center gap-2 font-semibold"><Sliders size={16} /> Response & personalization</h2>
        <label className="mb-1 block text-sm font-medium">Response style</label>
        <div className="mb-4 flex flex-wrap gap-2">
          {STYLES.map((s) => (
            <button key={s} onClick={() => save({ response_style: s })}
              className={`rounded-lg px-3 py-1.5 text-sm capitalize transition-colors ${prefs.response_style === s ? "bg-brand text-brand-fg" : "bg-surface-2 text-muted hover:text-fg"}`}>{s}</button>
          ))}
        </div>
        <label className="mb-1 block text-sm font-medium">Custom instructions</label>
        <textarea defaultValue={prefs.custom_instructions || ""} rows={3}
          onBlur={(e) => save({ custom_instructions: e.target.value })}
          placeholder="e.g. I'm a 2nd-year CSE student. Explain with code examples and keep it brief."
          className="w-full resize-none rounded-lg border border-border bg-surface/60 px-3 py-2 text-sm focus:border-brand focus:outline-none" />
      </Card>

      <Card className="mb-5 p-5">
        <h2 className="mb-4 flex items-center gap-2 font-semibold"><Shield size={16} /> Study & integrity</h2>
        <Toggle label="Exam / academic-integrity mode" hint="Coaches understanding instead of handing over submittable answers."
          on={prefs.exam_mode} onChange={(v) => save({ exam_mode: v })} />
        <Toggle label="Memory" hint="Let K-GPT remember your notes and use them in answers."
          on={prefs.memory_enabled} onChange={(v) => save({ memory_enabled: v })} />
        <Toggle label="Web search by default" hint="Ground answers with cited web results."
          on={prefs.web_search_enabled} onChange={(v) => save({ web_search_enabled: v })} />
      </Card>

      <Card className="mb-5 p-5">
        <h2 className="mb-4 flex items-center gap-2 font-semibold"><Brain size={16} /> Memory ({notes.length})</h2>
        {notes.length === 0 ? <p className="text-sm text-muted">No saved notes or documents yet.</p> : (
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {notes.map((n) => (
              <div key={n.id} className="flex items-start justify-between gap-2 rounded-lg bg-surface-2/50 px-3 py-2 text-sm">
                <div className="min-w-0"><span className="rounded bg-brand/15 px-1.5 py-0.5 text-[10px] text-brand">{n.kind}</span>
                  <p className="mt-1 line-clamp-2 text-muted">{n.content}</p></div>
                <button onClick={() => delNote(n.id)} className="shrink-0 text-muted hover:text-danger"><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
        )}
      </Card>

      {payments.length > 0 && (
        <Card className="mb-5 p-5">
          <h2 className="mb-4 font-semibold">Billing history</h2>
          <div className="space-y-2 text-sm">
            {payments.map((p, i) => (
              <div key={i} className="flex justify-between border-b border-border/50 pb-2">
                <span className="text-muted">{p.receipt_no || p.plan} · {p.status}</span>
                <span>₹{p.amount_inr}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="p-5">
        <h2 className="mb-4 font-semibold">Your data</h2>
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" size="sm" onClick={exportData}><Download size={14} /> Export my data</Button>
          <Button variant="danger" size="sm" onClick={deleteAccount}><Trash2 size={14} /> Delete account</Button>
        </div>
      </Card>
    </div>
  );
}

function Toggle({ label, hint, on, onChange }: { label: string; hint: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-4">
      <div><p className="text-sm font-medium">{label}</p><p className="text-xs text-muted">{hint}</p></div>
      <button onClick={() => onChange(!on)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${on ? "bg-brand" : "bg-surface-2"}`}>
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${on ? "translate-x-5" : "translate-x-0.5"}`} />
      </button>
    </div>
  );
}
