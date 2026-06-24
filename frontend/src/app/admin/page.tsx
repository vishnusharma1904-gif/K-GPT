"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Logo } from "@/components/Logo";
import { Button, Card, Badge } from "@/components/ui/primitives";
import Link from "next/link";
import { api, getToken, clearToken } from "@/lib/api";
import AdminOps from "@/components/AdminOps";
import SereneBackdrop from "@/components/SereneBackdrop";
import { Users, Check, Zap, Coins, LogOut, RotateCcw, Gift, Ban, ShieldCheck, RefreshCw, ShieldAlert, Eye, Database } from "lucide-react";

export default function AdminPage() {
  const router = useRouter();
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [plans, setPlans] = useState<any[]>([]);
  const [plan, setPlan] = useState("monthly");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  async function load() {
    setStats(await api.admin.stats());
    setUsers(await api.admin.users());
    try { setPlans(await api.billing.plans()); } catch {}
  }
  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api.me().then((m) => { if (m.role !== "admin") router.push("/chat"); else load(); })
      .catch(() => router.push("/login"));
  }, [router]);

  const ids = () => Array.from(sel);
  function toggle(id: string) {
    const n = new Set(sel); n.has(id) ? n.delete(id) : n.add(id); setSel(n);
  }
  async function run(fn: () => Promise<any>, note: string) {
    setBusy(true);
    try { await fn(); await load(); setSel(new Set()); setToast(note); setTimeout(() => setToast(""), 2500); }
    catch (e: any) { setToast(e.message); setTimeout(() => setToast(""), 4000); }
    finally { setBusy(false); }
  }

  const filtered = users.filter((u) =>
    (u.full_name + u.email + (u.roll_no || "")).toLowerCase().includes(q.toLowerCase()));

  const cards = stats ? [
    { label: "Total users", value: stats.total_users, icon: Users },
    { label: "Active subs", value: stats.active_subs, icon: Check },
    { label: "Heavy tier", value: stats.heavy_tier, icon: Zap },
    { label: "Suspended", value: stats.suspended, icon: Ban },
  ] : [];

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <SereneBackdrop />
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3"><Logo /><Badge className="bg-brand/15 text-brand">Admin</Badge></div>
        <div className="flex gap-2">
          <Link href="/admin/knowledge"><Button variant="outline" size="sm"><Database size={15} /> Knowledge</Button></Link>
          <Link href="/admin/monitor"><Button variant="outline" size="sm"><ShieldAlert size={15} /> Monitor</Button></Link>
          <Link href="/admin/analytics"><Button variant="outline" size="sm">Analytics</Button></Link>
          <Button variant="outline" size="sm" disabled={busy}
            onClick={() => run(() => api.admin.runNightly(), "Nightly sweep complete")}>
            <RefreshCw size={15} /> Run nightly
          </Button>
          <Button variant="ghost" size="sm" onClick={() => { clearToken(); router.push("/login"); }}><LogOut size={16} /> Log out</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {cards.map((c, i) => (
          <motion.div key={c.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
            <Card className="p-5">
              <div className="flex items-center gap-2 text-muted"><c.icon size={16} /><span className="text-sm">{c.label}</span></div>
              <div className="mt-2 text-3xl font-extrabold">{c.value}</div>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Bulk action bar */}
      {sel.size > 0 && (
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
          className="glass mt-5 flex flex-wrap items-center gap-2 rounded-xl p-3">
          <span className="px-2 text-sm font-medium">{sel.size} selected</span>
          <span className="flex items-center gap-1.5">
            <select value={plan} onChange={(e) => setPlan(e.target.value)}
              className="h-8 rounded-lg border border-border bg-surface-2 px-2 text-sm text-fg focus:border-brand focus:outline-none">
              {(plans.length ? plans : [{ code: "monthly", name: "Monthly" }, { code: "semester", name: "Semester" }, { code: "annual", name: "Annual" }]).map((pl: any) => (
                <option key={pl.code} value={pl.code}>{pl.name || pl.code}</option>
              ))}
            </select>
            <Button size="sm" disabled={busy} onClick={() => run(() => api.admin.grantPlan(ids(), plan), `Granted ${plan} plan`)}><Check size={14} /> Grant plan</Button>
          </span>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.admin.resetDaily(ids()), "Daily usage reset")}><RotateCcw size={14} /> Reset daily</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => { const t = Number(prompt("Grant how many extra tokens?", "200000")); if (t > 0) run(() => api.admin.grantTokens(ids(), t), "Tokens granted"); }}><Coins size={14} /> Grant tokens</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.admin.setTier(ids(), "heavy"), "Set to Heavy tier")}><Zap size={14} /> → Heavy</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.admin.setTier(ids(), "normal"), "Set to Normal tier")}>→ Normal</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.admin.clearOverride(ids()), "Auto-tiering re-enabled")}>Auto tier</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.admin.refreshBonus(ids()), "Weekly bonus refreshed")}><Gift size={14} /> Refresh bonus</Button>
          <Button size="sm" variant="danger" disabled={busy} onClick={() => run(() => api.admin.suspend(ids(), true), "Suspended")}><Ban size={14} /> Suspend</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.admin.suspend(ids(), false), "Restored")}><ShieldCheck size={14} /> Restore</Button>
        </motion.div>
      )}

      <Card className="mt-5 overflow-hidden">
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="font-semibold">Students</h2>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name / roll…"
            className="h-9 w-64 rounded-lg border border-border bg-surface-2 px-3 text-sm text-fg focus:border-brand focus:outline-none" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-muted">
              <tr className="border-b">
                <th className="w-10 px-4 py-2"></th>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Tier</th>
                <th className="px-4 py-2 font-medium">Today</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 text-right font-medium">Access</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id} className="border-b last:border-0 hover:bg-surface-2/50">
                  <td className="px-4 py-2.5">
                    <input type="checkbox" checked={sel.has(u.id)} onChange={() => toggle(u.id)} className="accent-[hsl(var(--brand))]" />
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="font-medium">{u.full_name}</div>
                    <div className="text-xs text-muted">{u.email}</div>
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge className={u.tier === "heavy" ? "bg-brand/15 text-brand" : "bg-surface-2 text-muted"}>
                      {u.tier}{u.tier_override ? " ·pin" : ""}
                    </Badge>
                  </td>
                  <td className="px-4 py-2.5 text-muted">{u.percent_used}%</td>
                  <td className="px-4 py-2.5">
                    <Badge className={u.suspended ? "bg-danger/15 text-danger" : u.sub_status === "active" ? "bg-accent/15 text-accent" : "bg-surface-2 text-muted"}>
                      {u.suspended ? "suspended" : u.sub_status}
                    </Badge>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {u.monitored && (
                        <Link href={`/admin/monitor?user=${u.id}`} title="View chats (safety monitoring)">
                          <span className="inline-flex text-muted hover:text-brand"><Eye size={16} /></span>
                        </Link>
                      )}
                      {u.sub_status === "active"
                        ? <span className="text-xs text-muted">—</span>
                        : <Button size="sm" onClick={() => run(() => api.admin.grantAccess(u.id), "Access granted")}>Grant access</Button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <AdminOps />

      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-lg bg-fg px-4 py-2 text-sm text-bg shadow-soft">{toast}</div>}
    </main>
  );
}
