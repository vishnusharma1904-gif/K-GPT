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
  const [fYear, setFYear] = useState("");
  const [fSem, setFSem] = useState("");
  const [fSection, setFSection] = useState("");
  const [fCourse, setFCourse] = useState("");
  const [fBranch, setFBranch] = useState("");
  const [editU, setEditU] = useState<any>(null);
  const [ef, setEf] = useState<any>({});
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
    (u.full_name + u.email + (u.roll_no || "")).toLowerCase().includes(q.toLowerCase())
    && (!fYear || String(u.year ?? "") === fYear)
    && (!fSem || String(u.semester ?? "") === fSem)
    && (!fSection || (u.section || "") === fSection)
    && (!fCourse || (u.course || "") === fCourse)
    && (!fBranch || (u.branch || "") === fBranch));

  // Distinct cohort values present, for the filter dropdowns.
  const uniq = (key: string) => Array.from(new Set(users.map((u) => u[key]).filter(Boolean)))
    .sort((a, b) => String(a).localeCompare(String(b)));

  const COURSES = ["B.Tech", "M.Tech", "MBA", "MCA", "Diploma"];
  const BRANCHES = ["CSE", "CSE (AI & ML)", "CSE (Data Science)", "AI & DS", "ECE", "EEE", "Mechanical", "Civil", "IT", "Other"];
  const ADM_YEARS = Array.from({ length: 8 }, (_, i) => new Date().getFullYear() - i);

  function openEdit(u: any) {
    setEditU(u);
    setEf({ full_name: u.full_name || "", roll_no: u.roll_no || "", course: u.course || "",
      branch: u.branch || "", admission_year: u.admission_year || "", section: u.section || "" });
  }
  async function saveEdit() {
    const id = editU.id;
    setEditU(null);
    await run(() => api.admin.setProfile(id, {
      full_name: ef.full_name, roll_no: ef.roll_no, course: ef.course, branch: ef.branch,
      admission_year: ef.admission_year ? Number(ef.admission_year) : null,
      section: ef.section,
    }), "Profile updated");
  }

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
        <div className="border-b p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Students <span className="text-sm font-normal text-muted">({filtered.length})</span></h2>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name / roll…"
              className="h-9 w-64 rounded-lg border border-border bg-surface-2 px-3 text-sm text-fg focus:border-brand focus:outline-none" />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            {([
              ["Course", fCourse, setFCourse, uniq("course")],
              ["Branch", fBranch, setFBranch, uniq("branch")],
              ["Year", fYear, setFYear, uniq("year")],
              ["Sem", fSem, setFSem, uniq("semester")],
              ["Section", fSection, setFSection, uniq("section")],
            ] as const).map(([label, val, setter, opts]) => (
              <select key={label} value={val as string} onChange={(e) => (setter as any)(e.target.value)}
                className="h-8 rounded-lg border border-border bg-surface-2 px-2 text-fg focus:border-brand focus:outline-none">
                <option value="">{label}: all</option>
                {(opts as any[]).map((o) => <option key={String(o)} value={String(o)}>{label} {String(o)}</option>)}
              </select>
            ))}
            {(fCourse || fBranch || fYear || fSem || fSection) && (
              <button onClick={() => { setFCourse(""); setFBranch(""); setFYear(""); setFSem(""); setFSection(""); }}
                className="h-8 rounded-lg px-2 text-muted hover:text-fg">Clear</button>
            )}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-muted">
              <tr className="border-b">
                <th className="w-10 px-4 py-2"></th>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Class</th>
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
                  <td className="px-4 py-2.5 text-xs text-muted">
                    {[u.course, u.branch].filter(Boolean).join(" ") || "—"}
                    {(u.year || u.section) && (
                      <div>{[u.year && `Y${u.year}`, u.semester && `S${u.semester}`, u.section && `Sec ${u.section}`].filter(Boolean).join(" · ")}</div>
                    )}
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
                      <button onClick={() => openEdit(u)} title="Edit student profile"
                        className="text-xs text-muted hover:text-brand">Edit</button>
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

      {editU && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setEditU(null)}>
          <Card className="w-full max-w-md p-5" onClick={(e: any) => e.stopPropagation()}>
            <h3 className="mb-1 font-semibold">Edit profile</h3>
            <p className="mb-4 text-xs text-muted">{editU.email}</p>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-muted">Full name</label>
                <input value={ef.full_name} onChange={(e) => setEf({ ...ef, full_name: e.target.value })}
                  className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm focus:border-brand focus:outline-none" />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted">Roll number</label>
                <input value={ef.roll_no} onChange={(e) => setEf({ ...ef, roll_no: e.target.value })}
                  className="w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm focus:border-brand focus:outline-none" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs text-muted">Course</label>
                  <select value={ef.course} onChange={(e) => setEf({ ...ef, course: e.target.value })}
                    className="w-full rounded-lg border border-border bg-surface-2 px-2 py-2 text-sm focus:border-brand focus:outline-none">
                    <option value="">—</option>{COURSES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-muted">Branch</label>
                  <select value={ef.branch} onChange={(e) => setEf({ ...ef, branch: e.target.value })}
                    className="w-full rounded-lg border border-border bg-surface-2 px-2 py-2 text-sm focus:border-brand focus:outline-none">
                    <option value="">—</option>{BRANCHES.map((b) => <option key={b} value={b}>{b}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs text-muted">Admission year (batch)</label>
                  <select value={ef.admission_year} onChange={(e) => setEf({ ...ef, admission_year: e.target.value })}
                    className="w-full rounded-lg border border-border bg-surface-2 px-2 py-2 text-sm focus:border-brand focus:outline-none">
                    <option value="">—</option>{ADM_YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-muted">Section</label>
                  <select value={ef.section} onChange={(e) => setEf({ ...ef, section: e.target.value })}
                    className="w-full rounded-lg border border-border bg-surface-2 px-2 py-2 text-sm focus:border-brand focus:outline-none">
                    <option value="">—</option>{["A","B","C","D","E","F"].map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              </div>
              <p className="text-xs text-muted">Current year &amp; semester are derived from the batch year automatically.</p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setEditU(null)}>Cancel</Button>
              <Button size="sm" onClick={saveEdit}>Save</Button>
            </div>
          </Card>
        </div>
      )}

      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-lg bg-fg px-4 py-2 text-sm text-bg shadow-soft">{toast}</div>}
    </main>
  );
}
