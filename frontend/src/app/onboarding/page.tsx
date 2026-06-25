"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AuthShell, { authLabel, authInput, authButton, authError } from "@/components/AuthShell";
import { api, getToken } from "@/lib/api";

const COURSES = ["B.Tech", "M.Tech", "MBA", "MCA", "Diploma"];
const BRANCHES = [
  "CSE", "CSE (AI & ML)", "CSE (Data Science)", "AI & DS", "ECE", "EEE",
  "Mechanical", "Civil", "IT", "Other",
];
const SECTIONS = ["A", "B", "C", "D", "E", "F"];
const NOW_YEAR = new Date().getFullYear();
// Joining / batch year — current year back to 6 years ago.
const ADMISSION_YEARS = Array.from({ length: 7 }, (_, i) => NOW_YEAR - i);

export default function OnboardingPage() {
  const router = useRouter();
  const [form, setForm] = useState<any>({
    full_name: "", roll_no: "", course: "", branch: "", branchOther: "",
    admission_year: "", section: "",
  });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    // Prefill anything already known (name from signup, etc.).
    api.getPrefs().then((p) => {
      setForm((f: any) => ({
        ...f,
        full_name: p.full_name || "", roll_no: p.roll_no || "",
        course: p.course || "", branch: p.branch || "",
        admission_year: p.admission_year || "", section: p.section || "",
      }));
    }).catch(() => {});
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    for (const [k, label] of [["full_name", "Full name"], ["roll_no", "Roll number"],
      ["course", "Course"], ["branch", "Branch"], ["admission_year", "Admission year"],
      ["section", "Section"]] as const) {
      if (!String(form[k] || "").trim()) { setErr(`Please fill in your ${label}.`); return; }
    }
    if (form.branch === "Other" && !String(form.branchOther || "").trim()) {
      setErr("Please specify your branch."); return;
    }
    const branch = form.branch === "Other" ? form.branchOther.trim() : form.branch;
    setLoading(true);
    try {
      const r = await api.setPrefs({
        full_name: form.full_name, roll_no: form.roll_no, course: form.course,
        branch, admission_year: Number(form.admission_year), section: form.section,
      });
      if (r.profile_complete === false) { setErr("Some details are still missing."); return; }
      router.push("/chat");
    } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }

  return (
    <AuthShell
      biome="forests"
      title="Complete your profile"
      subtitle="A few details so K-GPT can tailor answers to your course. Required to continue."
    >
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <label className={authLabel}>Full name</label>
          <input required value={form.full_name} onChange={set("full_name")} placeholder="Your full name" className={authInput} />
        </div>
        <div className="space-y-1.5">
          <label className={authLabel}>Roll number</label>
          <input required value={form.roll_no} onChange={set("roll_no")} placeholder="e.g. 22CSE001" className={authInput} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label className={authLabel}>Course</label>
            <select required value={form.course} onChange={set("course")} className={authInput}>
              <option value="">Select…</option>
              {COURSES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className={authLabel}>Branch</label>
            <select required value={form.branch} onChange={set("branch")} className={authInput}>
              <option value="">Select…</option>
              {BRANCHES.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
        </div>
        {form.branch === "Other" && (
          <div className="space-y-1.5">
            <label className={authLabel}>Specify your branch</label>
            <input required value={form.branchOther} onChange={set("branchOther")} placeholder="e.g. Chemical, Aeronautical…" className={authInput} />
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label className={authLabel}>Admission year (batch)</label>
            <select required value={form.admission_year} onChange={set("admission_year")} className={authInput}>
              <option value="">—</option>
              {ADMISSION_YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className={authLabel}>Section</label>
            <select required value={form.section} onChange={set("section")} className={authInput}>
              <option value="">—</option>
              {SECTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
        <p className="text-xs text-white/50">Your current year &amp; semester are calculated automatically from your batch and update each term.</p>
        {err && <p className={authError}>{err}</p>}
        <button type="submit" disabled={loading} className={authButton}>
          {loading ? "Saving…" : "Save & continue"}
        </button>
      </form>
    </AuthShell>
  );
}
