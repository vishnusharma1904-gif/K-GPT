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
// Programme length per course → caps the "current year" options (e.g. M.Tech = 2).
const COURSE_YEARS: Record<string, number> = {
  "B.Tech": 4, "M.Tech": 2, "MBA": 2, "MCA": 2, "Diploma": 3,
};
const yearsFor = (course: string) =>
  Array.from({ length: COURSE_YEARS[course] || 4 }, (_, i) => i + 1);

export default function OnboardingPage() {
  const router = useRouter();
  const [role, setRole] = useState<string>("student");
  const [form, setForm] = useState<any>({
    full_name: "", roll_no: "", course: "", branch: "", branchOther: "",
    year: "", section: "", department: "", mobile: "",
  });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });
  const setCourse = (e: any) => {
    const course = e.target.value;
    // Programme length changes with course (e.g. B.Tech=4yr, M.Tech=2yr), so a
    // previously-picked year can become invalid for the new course (e.g. Year 4
    // selected, then switching to a 2-year M.Tech). Clear it instead of leaving
    // a stale value silently selected in a <select> with no matching option.
    const maxYears = COURSE_YEARS[course] || 4;
    setForm((f: any) => ({
      ...f,
      course,
      year: f.year && Number(f.year) <= maxYears ? f.year : "",
    }));
  };

  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    // Prefill anything already known (name from signup, etc.).
    api.getPrefs().then((p) => {
      setRole(p.role || "student");
      setForm((f: any) => ({
        ...f,
        full_name: p.full_name || "", roll_no: p.roll_no || "",
        course: p.course || "", branch: p.branch || "",
        year: p.year || "", section: p.section || "",
        department: p.department || "", mobile: p.mobile || "",
      }));
    }).catch(() => {});
  }, [router]);

  async function submitFaculty() {
    setErr("");
    if (!form.full_name.trim()) { setErr("Please fill in your Full name."); return; }
    if (!form.department.trim()) { setErr("Please enter your Department."); return; }
    if (!/^[6-9]\d{9}$/.test(String(form.mobile).replace(/\D/g, "").replace(/^91/, "").replace(/^0/, ""))) {
      setErr("Enter a valid 10-digit mobile number."); return;
    }
    setLoading(true);
    try {
      const r = await api.setPrefs({
        full_name: form.full_name, department: form.department, mobile: form.mobile,
      });
      if (r.profile_complete === false) { setErr("Some details are still missing."); return; }
      router.push("/chat");
    } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }

  async function submitStudent() {
    setErr("");
    for (const [k, label] of [["full_name", "Full name"], ["roll_no", "Roll number"],
      ["course", "Course"], ["branch", "Branch"], ["year", "Current year"],
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
        branch, year: Number(form.year), section: form.section,
      });
      if (r.profile_complete === false) { setErr("Some details are still missing."); return; }
      router.push("/chat");
    } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    return role === "faculty" ? submitFaculty() : submitStudent();
  }

  return (
    <AuthShell
      biome="forests"
      title="Complete your profile"
      subtitle={role === "faculty"
        ? "A few details to finish setting up your faculty account."
        : "A few details so K-GPT can tailor answers to your course. Required to continue."}
    >
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <label className={authLabel}>Full name</label>
          <input required value={form.full_name} onChange={set("full_name")} placeholder="Your full name" className={authInput} />
        </div>

        {role === "faculty" ? (
          <>
            <div className="space-y-1.5">
              <label className={authLabel}>Department</label>
              <input required value={form.department} onChange={set("department")} placeholder="e.g. Computer Science & Engineering" className={authInput} />
            </div>
            <div className="space-y-1.5">
              <label className={authLabel}>Mobile number</label>
              <input type="tel" required inputMode="numeric" value={form.mobile} onChange={set("mobile")} placeholder="10-digit mobile" className={authInput} />
            </div>
          </>
        ) : (
          <>
            <div className="space-y-1.5">
              <label className={authLabel}>Roll number</label>
              <input required value={form.roll_no} onChange={set("roll_no")} placeholder="e.g. 22CSE001" className={authInput} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className={authLabel}>Course</label>
                <select required value={form.course} onChange={setCourse} className={authInput}>
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
                <label className={authLabel}>Current year</label>
                <select required value={form.year} onChange={set("year")} className={authInput}>
                  <option value="">—</option>
                  {yearsFor(form.course).map((y) => <option key={y} value={y}>Year {y}</option>)}
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
            <p className="text-xs text-muted/70">Pick the year you're studying in <span className="text-muted">right now</span> (so it's correct even if you're repeating a year). Your odd/even semester updates automatically each term.</p>
          </>
        )}

        {err && <p className={authError}>{err}</p>}
        <button type="submit" disabled={loading} className={authButton}>
          {loading ? "Saving…" : "Save & continue"}
        </button>
      </form>
    </AuthShell>
  );
}
