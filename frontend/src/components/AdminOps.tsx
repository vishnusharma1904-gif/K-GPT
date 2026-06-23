"use client";
/* Admin operations console (P4/P46/P47/P18/P50) — feature flags, cohort budgets,
   incidents, coupons, bulk activation, and the pilot NPS report. Consumes the
   existing admin/status/feedback APIs. Mounted under the main admin dashboard. */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button, Card, Input, Badge } from "@/components/ui/primitives";

type Tab = "logs" | "flags" | "budgets" | "incidents" | "coupons" | "bulk" | "nps";
const TABS: { id: Tab; label: string }[] = [
  { id: "logs", label: "Usage logs" },
  { id: "flags", label: "Feature flags" },
  { id: "budgets", label: "Cohort budgets" },
  { id: "incidents", label: "Incidents" },
  { id: "coupons", label: "Coupons" },
  { id: "bulk", label: "Bulk activate" },
  { id: "nps", label: "Pilot NPS" },
];

function useToast() {
  const [msg, setMsg] = useState("");
  const show = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 2500); };
  return { msg, show };
}

export default function AdminOps() {
  const [tab, setTab] = useState<Tab>("logs");
  return (
    <Card className="mt-6 p-0 overflow-hidden">
      <div className="flex flex-wrap gap-1 border-b border-border p-2">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`rounded-lg px-3 py-1.5 text-sm ${tab === t.id ? "bg-brand text-brand-fg" : "text-muted hover:bg-surface-2"}`}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="p-5">
        {tab === "logs" && <Logs />}
        {tab === "flags" && <Flags />}
        {tab === "budgets" && <Budgets />}
        {tab === "incidents" && <Incidents />}
        {tab === "coupons" && <Coupons />}
        {tab === "bulk" && <Bulk />}
        {tab === "nps" && <Nps />}
      </div>
    </Card>
  );
}

function Flags() {
  const [rows, setRows] = useState<any[]>([]);
  const { msg, show } = useToast();
  const load = () => api.admin.flags().then(setRows).catch((e) => show(e.message));
  useEffect(() => { load(); }, []);
  const toggle = async (key: string, enabled: boolean) => {
    try { await api.admin.setFlag(key, enabled); show("Saved"); load(); }
    catch (e: any) { show(e.message); }
  };
  return (
    <div className="space-y-2">
      {rows.map((f) => (
        <div key={f.key} className="flex items-center justify-between rounded-lg border border-border p-3">
          <div>
            <div className="font-medium">{f.key}</div>
            <div className="text-xs text-muted">{f.description}</div>
          </div>
          <button onClick={() => toggle(f.key, !f.enabled)}
            className={`h-6 w-11 rounded-full transition-colors ${f.enabled ? "bg-brand" : "bg-surface-2"}`}>
            <span className={`block h-5 w-5 rounded-full bg-white transition-transform ${f.enabled ? "translate-x-5" : "translate-x-0.5"}`} />
          </button>
        </div>
      ))}
      {!rows.length && <p className="text-sm text-muted">No flags.</p>}
      <p className="text-xs text-brand">{msg}</p>
    </div>
  );
}

function Budgets() {
  const [rows, setRows] = useState<any[]>([]);
  const [cohort, setCohort] = useState("");
  const [usd, setUsd] = useState("50");
  const { msg, show } = useToast();
  const load = () => api.admin.budgets().then(setRows).catch((e) => show(e.message));
  useEffect(() => { load(); }, []);
  const save = async () => {
    if (!cohort.trim()) return;
    try { await api.admin.setBudget({ cohort: cohort.trim(), monthly_usd: Number(usd), alert_pct: 80 }); show("Saved"); setCohort(""); load(); }
    catch (e: any) { show(e.message); }
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div><div className="mb-1 text-xs text-muted">Cohort</div><Input value={cohort} onChange={(e) => setCohort(e.target.value)} placeholder="CSE-2026-A" className="h-9 w-44" /></div>
        <div><div className="mb-1 text-xs text-muted">Monthly $ cap</div><Input value={usd} onChange={(e) => setUsd(e.target.value)} className="h-9 w-28" /></div>
        <Button size="sm" onClick={save}>Set budget</Button>
        <Button size="sm" variant="outline" onClick={() => api.admin.enforceBudgets().then(() => { show("Sweep ran"); load(); })}>Run sweep</Button>
      </div>
      <div className="space-y-2">
        {rows.map((b) => (
          <div key={b.cohort} className="flex items-center justify-between rounded-lg border border-border p-3 text-sm">
            <span className="font-medium">{b.cohort}</span>
            <span className="text-muted">${b.spend_usd} / ${b.monthly_usd} ({b.percent}%)</span>
            <Badge className={b.breached ? "bg-danger/15 text-danger" : b.alerting ? "bg-warning/15 text-warning" : "bg-accent/15 text-accent"}>
              {b.breached ? "throttled" : b.alerting ? "alerting" : "ok"}
            </Badge>
          </div>
        ))}
        {!rows.length && <p className="text-sm text-muted">No budgets set.</p>}
      </div>
      <p className="text-xs text-brand">{msg}</p>
    </div>
  );
}

function Incidents() {
  const [rows, setRows] = useState<any[]>([]);
  const [title, setTitle] = useState("");
  const [sev, setSev] = useState("minor");
  const { msg, show } = useToast();
  const load = () => api.admin.incidents().then(setRows).catch((e) => show(e.message));
  useEffect(() => { load(); }, []);
  const create = async () => {
    if (!title.trim()) return;
    try { await api.admin.createIncident({ title: title.trim(), severity: sev }); show("Posted"); setTitle(""); load(); }
    catch (e: any) { show(e.message); }
  };
  const resolve = async (id: string) => { await api.admin.updateIncident(id, { status: "resolved" }); show("Resolved"); load(); };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex-1"><div className="mb-1 text-xs text-muted">Title</div><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Provider X degraded" className="h-9" /></div>
        <select value={sev} onChange={(e) => setSev(e.target.value)} className="h-9 rounded-lg border border-border bg-surface-2 px-2 text-sm text-fg">
          <option value="minor">minor</option><option value="major">major</option><option value="critical">critical</option>
        </select>
        <Button size="sm" onClick={create}>Post incident</Button>
      </div>
      <div className="space-y-2">
        {rows.map((i) => (
          <div key={i.id} className="flex items-center justify-between rounded-lg border border-border p-3 text-sm">
            <div><div className="font-medium">{i.title}</div><div className="text-xs text-muted">{i.severity} · {i.status}</div></div>
            {i.status !== "resolved" && <Button size="sm" variant="outline" onClick={() => resolve(i.id)}>Resolve</Button>}
          </div>
        ))}
        {!rows.length && <p className="text-sm text-muted">No incidents.</p>}
      </div>
      <p className="text-xs text-brand">{msg}</p>
    </div>
  );
}

function Coupons() {
  const [rows, setRows] = useState<any[]>([]);
  const [code, setCode] = useState("");
  const [pct, setPct] = useState("10");
  const { msg, show } = useToast();
  const load = () => api.admin.coupons().then(setRows).catch((e) => show(e.message));
  useEffect(() => { load(); }, []);
  const create = async () => {
    if (!code.trim()) return;
    try { await api.admin.createCoupon({ code: code.trim(), percent_off: Number(pct) }); show("Created"); setCode(""); load(); }
    catch (e: any) { show(e.message); }
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div><div className="mb-1 text-xs text-muted">Code</div><Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="WELCOME10" className="h-9 w-44" /></div>
        <div><div className="mb-1 text-xs text-muted">% off</div><Input value={pct} onChange={(e) => setPct(e.target.value)} className="h-9 w-20" /></div>
        <Button size="sm" onClick={create}>Create coupon</Button>
      </div>
      <div className="space-y-2">
        {rows.map((c) => (
          <div key={c.code} className="flex items-center justify-between rounded-lg border border-border p-3 text-sm">
            <span className="font-medium">{c.code}</span>
            <span className="text-muted">{c.percent_off}% off · {c.redeemed || 0} used</span>
          </div>
        ))}
        {!rows.length && <p className="text-sm text-muted">No coupons.</p>}
      </div>
      <p className="text-xs text-brand">{msg}</p>
    </div>
  );
}

function Bulk() {
  const [rolls, setRolls] = useState("");
  const [months, setMonths] = useState("6");
  const { msg, show } = useToast();
  const run = async () => {
    const list = rolls.split(/[\s,]+/).map((r) => r.trim()).filter(Boolean);
    if (!list.length) return;
    try { const r = await api.admin.bulkActivate(list, Number(months)); show(`Activated ${r.activated}/${r.requested}`); }
    catch (e: any) { show(e.message); }
  };
  return (
    <div className="space-y-3">
      <div className="text-sm text-muted">Paste roll numbers (comma, space, or newline separated). Matching accounts are activated.</div>
      <textarea value={rolls} onChange={(e) => setRolls(e.target.value)} rows={4}
        placeholder="22091A0501, 22091A0502, ..."
        className="w-full rounded-lg border border-border bg-surface/60 p-3 text-sm focus:border-brand focus:outline-none" />
      <div className="flex items-end gap-2">
        <div><div className="mb-1 text-xs text-muted">Months</div><Input value={months} onChange={(e) => setMonths(e.target.value)} className="h-9 w-24" /></div>
        <Button size="sm" onClick={run}>Activate cohort</Button>
      </div>
      <p className="text-xs text-brand">{msg}</p>
    </div>
  );
}

function Nps() {
  const [d, setD] = useState<any>(null);
  const { msg, show } = useToast();
  useEffect(() => { api.feedback.nps().then(setD).catch((e) => show(e.message)); }, []);
  if (!d) return <p className="text-sm text-muted">{msg || "Loading…"}</p>;
  if (!d.responses) return <p className="text-sm text-muted">No feedback responses yet.</p>;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[["NPS", d.nps], ["Responses", d.responses], ["Promoters", d.promoters], ["Detractors", d.detractors]].map(([k, v]) => (
        <div key={k} className="rounded-lg border border-border p-4">
          <div className="text-2xl font-bold">{String(v)}</div>
          <div className="text-xs text-muted">{k}</div>
        </div>
      ))}
    </div>
  );
}


function fmtNum(n: number) { return (n ?? 0).toLocaleString(); }
function fmtTime(s: string) { try { return new Date(s).toLocaleString(); } catch { return s; } }
function shortModel(m: string) { return (m || "—").split("/").pop() || m; }

function Logs() {
  const [d, setD] = useState<any>(null);
  const [limit, setLimit] = useState(100);
  const { msg, show } = useToast();
  const load = (n = limit) => api.admin.usageLog(n).then(setD).catch((e) => show(e.message));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [limit]);
  if (!d) return <p className="text-sm text-muted">{msg || "Loading…"}</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="rounded-lg border border-border px-3 py-2"><div className="text-lg font-bold">{fmtNum(d.count)}</div><div className="text-xs text-muted">requests</div></div>
        <div className="rounded-lg border border-border px-3 py-2"><div className="text-lg font-bold">{fmtNum(d.total_tokens)}</div><div className="text-xs text-muted">total tokens</div></div>
        <div className="rounded-lg border border-border px-3 py-2"><div className="text-lg font-bold">${d.total_cost_usd}</div><div className="text-xs text-muted">total cost</div></div>
        <div className="ml-auto flex items-center gap-2">
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="h-9 rounded-lg border border-border bg-surface-2 px-2 text-sm text-fg">
            {[50, 100, 200, 500].map((n) => <option key={n} value={n}>last {n}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={() => load()}>Refresh</Button>
        </div>
      </div>

      {d.by_model?.length > 0 && (
        <div>
          <div className="mb-2 text-sm font-medium">By model</div>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="text-left text-muted"><tr className="border-b border-border">
                <th className="px-3 py-2 font-medium">Model</th><th className="px-3 py-2 font-medium">Requests</th>
                <th className="px-3 py-2 font-medium">Tokens</th><th className="px-3 py-2 font-medium">Cost</th>
              </tr></thead>
              <tbody>
                {d.by_model.map((m: any) => (
                  <tr key={m.model} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 font-mono text-xs">{shortModel(m.model)}</td>
                    <td className="px-3 py-2">{fmtNum(m.requests)}</td>
                    <td className="px-3 py-2">{fmtNum(m.tokens)}</td>
                    <td className="px-3 py-2">${m.cost_usd}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div>
        <div className="mb-2 text-sm font-medium">Recent requests</div>
        <div className="max-h-[420px] overflow-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface text-left text-muted"><tr className="border-b border-border">
              <th className="px-3 py-2 font-medium">Time</th><th className="px-3 py-2 font-medium">Student</th>
              <th className="px-3 py-2 font-medium">Model</th><th className="px-3 py-2 font-medium">Prompt</th>
              <th className="px-3 py-2 font-medium">Completion</th><th className="px-3 py-2 font-medium">Total</th>
              <th className="px-3 py-2 font-medium">Cost</th>
            </tr></thead>
            <tbody>
              {d.rows.map((r: any, i: number) => (
                <tr key={i} className="border-b border-border last:border-0 hover:bg-surface-2/50">
                  <td className="px-3 py-2 whitespace-nowrap text-xs text-muted">{fmtTime(r.created_at)}</td>
                  <td className="px-3 py-2"><div className="font-medium">{r.user}</div><div className="text-xs text-muted">{r.email}</div></td>
                  <td className="px-3 py-2 font-mono text-xs">{shortModel(r.model)}</td>
                  <td className="px-3 py-2">{fmtNum(r.prompt_tokens)}</td>
                  <td className="px-3 py-2">{fmtNum(r.completion_tokens)}</td>
                  <td className="px-3 py-2 font-medium">{fmtNum(r.total_tokens)}</td>
                  <td className="px-3 py-2 text-muted">${r.cost_usd}</td>
                </tr>
              ))}
              {!d.rows.length && <tr><td colSpan={7} className="px-3 py-6 text-center text-sm text-muted">No requests logged yet — send a chat message and refresh.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      <p className="text-xs text-brand">{msg}</p>
    </div>
  );
}
