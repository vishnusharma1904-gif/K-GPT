"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AuthShell, { authLabel, authInput, authButton, authError } from "@/components/AuthShell";
import OtpStep from "@/components/OtpStep";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [otpEmail, setOtpEmail] = useState("");
  const [pending, setPending] = useState(false);

  function finish(r: any) {
    // Faculty accounts are blocked until an admin approves them.
    if (r.approval_pending) { setPending(true); setOtpEmail(""); return; }
    setToken(r.access_token);
    const u = r.user;
    if (u.role === "admin") router.push("/admin");
    else if (!u.profile_complete) router.push("/onboarding");
    else router.push("/chat");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      const r = await api.login({ email, password });
      if (r.otp_required) { setOtpEmail(r.email); return; }
      finish(r);
    } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }

  return (
    <AuthShell
      biome="beaches"
      title={pending ? "Awaiting approval" : otpEmail ? "Verify your email" : "Welcome back"}
      subtitle={pending
        ? "Your faculty account is pending admin approval."
        : otpEmail ? "Enter the code we emailed you to continue." : "Log in to your K-GPT account."}
      footer={
        <>
          New here?{" "}
          <Link href="/signup" className="font-medium text-fg underline underline-offset-2 hover:text-fg/80">
            Create an account
          </Link>
        </>
      }
    >
      {pending ? (
        <div className="space-y-4 text-sm text-muted">
          <p>
            Your faculty account hasn't been approved yet. An administrator needs
            to approve it before you can sign in. Please check back later.
          </p>
          <button type="button" onClick={() => setPending(false)} className={authButton}>
            Back to login
          </button>
        </div>
      ) : otpEmail ? (
        <OtpStep email={otpEmail} onVerified={finish} />
      ) : (
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <label className={authLabel}>College email</label>
          <input
            type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="rollno@ksrmce.ac.in" className={authInput}
          />
        </div>
        <div className="space-y-1.5">
          <label className={authLabel}>Password</label>
          <input
            type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••" className={authInput}
          />
        </div>
        {err && <p className={authError}>{err}</p>}
        <button type="submit" disabled={loading} className={authButton}>
          {loading ? "Logging in…" : "Log in"}
        </button>
        <Link href="/forgot" className="block text-center text-sm text-muted transition-colors hover:text-fg">
          Forgot password?
        </Link>
      </form>
      )}
    </AuthShell>
  );
}
