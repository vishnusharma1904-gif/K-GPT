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

  function finish(r: any) {
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
      title={otpEmail ? "Verify your email" : "Welcome back"}
      subtitle={otpEmail ? "Enter the code we emailed you to continue." : "Log in to your K-GPT account."}
      footer={
        <>
          New here?{" "}
          <Link href="/signup" className="font-medium text-white underline underline-offset-2 hover:text-white/80">
            Create an account
          </Link>
        </>
      }
    >
      {otpEmail ? (
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
        <Link href="/forgot" className="block text-center text-sm text-white/60 transition-colors hover:text-white">
          Forgot password?
        </Link>
      </form>
      )}
    </AuthShell>
  );
}
