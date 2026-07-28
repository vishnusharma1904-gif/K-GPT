"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AuthShell, { authLabel, authInput, authButton, authError } from "@/components/AuthShell";
import OtpStep from "@/components/OtpStep";
import { api, setToken } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    full_name: "", email: "", password: "",
    role: "student", department: "", mobile: "",
  });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [otpEmail, setOtpEmail] = useState("");
  const [pending, setPending] = useState(false);
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });
  const isFaculty = form.role === "faculty";

  function finish(r: any) {
    // Faculty accounts are blocked until an admin approves them.
    if (r.approval_pending) { setPending(true); return; }
    setToken(r.access_token);
    const u = r.user;
    if (u.role === "admin") router.push("/admin");
    else if (!u.profile_complete) router.push("/onboarding");
    else router.push("/account");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    if (isFaculty) {
      if (!form.department.trim()) { setErr("Please enter your department."); return; }
      if (!/^[6-9]\d{9}$/.test(form.mobile.replace(/\D/g, "").replace(/^91/, "").replace(/^0/, ""))) {
        setErr("Enter a valid 10-digit mobile number."); return;
      }
    }
    setLoading(true);
    try {
      const r = await api.signup(form);
      if (r.otp_required) { setOtpEmail(r.email); return; }
      finish(r);
    } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }

  return (
    <AuthShell
      biome="forests"
      title={pending ? "Awaiting approval" : otpEmail ? "Verify your email" : "Create your account"}
      subtitle={pending
        ? <>Your faculty account needs admin approval before you can sign in.</>
        : otpEmail
        ? <>Enter the code we emailed you to finish signing up.</>
        : <>Use your <span className="font-medium text-fg">@ksrmce.ac.in</span> college email.</>}
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-fg underline underline-offset-2 hover:text-fg/80">
            Log in
          </Link>
        </>
      }
    >
      {pending ? (
        <div className="space-y-4 text-sm text-muted">
          <p>
            Thanks for registering as faculty. An administrator will review your
            request and approve your account. You'll be able to log in once it's
            approved.
          </p>
          <p className="text-xs text-muted/70">
            Approval is usually quick. If it's urgent, contact your K-GPT admin.
          </p>
          <Link href="/login" className={authButton + " block text-center"}>Back to login</Link>
        </div>
      ) : otpEmail ? (
        <OtpStep email={otpEmail} onVerified={finish} />
      ) : (
      <form onSubmit={submit} className="space-y-4">
        {/* Role selector — student (default) or faculty (admin-approved) */}
        <div className="space-y-1.5">
          <label className={authLabel}>I am a…</label>
          <div className="grid grid-cols-2 gap-2">
            {[["student", "Student"], ["faculty", "Faculty"]].map(([val, lbl]) => (
              <button
                key={val} type="button" onClick={() => setForm({ ...form, role: val })}
                className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                  form.role === val
                    ? "border-fg/70 bg-fg/15 text-fg"
                    : "border-fg/15 text-muted hover:text-fg"}`}>
                {lbl}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1.5">
          <label className={authLabel}>Full name</label>
          <input required value={form.full_name} onChange={set("full_name")} placeholder="Your name" className={authInput} />
        </div>
        <div className="space-y-1.5">
          <label className={authLabel}>College email</label>
          <input type="email" required value={form.email} onChange={set("email")} placeholder="rollno@ksrmce.ac.in" className={authInput} />
        </div>
        {isFaculty && (
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
        )}
        <div className="space-y-1.5">
          <label className={authLabel}>Password</label>
          <input type="password" required minLength={8} value={form.password} onChange={set("password")} placeholder="At least 8 characters" className={authInput} />
        </div>
        {isFaculty && (
          <p className="text-xs text-muted/70">
            Faculty accounts are reviewed by an admin before access is granted.
          </p>
        )}
        {err && <p className={authError}>{err}</p>}
        <button type="submit" disabled={loading} className={authButton}>
          {loading ? "Creating…" : "Create account"}
        </button>
      </form>
      )}
    </AuthShell>
  );
}
