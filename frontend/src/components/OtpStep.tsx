"use client";
import { useState } from "react";
import { authLabel, authInput, authButton, authError } from "@/components/AuthShell";
import { api } from "@/lib/api";

/** Email-OTP verification step. Shown after signup/login returns otp_required.
 *  Calls onVerified with the auth response ({ access_token, user }) on success. */
export default function OtpStep({ email, onVerified }: { email: string; onVerified: (r: any) => void }) {
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setInfo(""); setLoading(true);
    try {
      const r = await api.verifyOtp(email, code.trim());
      onVerified(r);
    } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }

  async function resend() {
    setErr(""); setInfo(""); setResending(true);
    try {
      await api.resendOtp(email);
      setInfo("A new code is on its way. Check your inbox.");
    } catch (e: any) { setErr(e.message); } finally { setResending(false); }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-sm text-white/70">
        We sent a 6-digit verification code to{" "}
        <span className="font-medium text-white">{email}</span>. Enter it below to activate your account.
      </p>
      <p className="text-xs text-white/50">
        Don't see it? Please check your <span className="font-medium text-white/70">Spam / Junk</span> folder too.
      </p>
      <div className="space-y-1.5">
        <label className={authLabel}>Verification code</label>
        <input
          required inputMode="numeric" autoComplete="one-time-code" maxLength={6}
          value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          placeholder="123456"
          className={`${authInput} text-center text-lg tracking-[0.5em]`}
        />
      </div>
      {err && <p className={authError}>{err}</p>}
      {info && <p className="text-sm text-emerald-400">{info}</p>}
      <button type="submit" disabled={loading || code.length < 4} className={authButton}>
        {loading ? "Verifying…" : "Verify & continue"}
      </button>
      <button
        type="button" onClick={resend} disabled={resending}
        className="block w-full text-center text-sm text-white/60 transition-colors hover:text-white disabled:opacity-50"
      >
        {resending ? "Sending…" : "Didn't get it? Resend code"}
      </button>
    </form>
  );
}
