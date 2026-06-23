"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AuthShell, { authLabel, authInput, authButton, authError } from "@/components/AuthShell";
import { api, setToken } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      const r = await api.signup(form);
      setToken(r.access_token);
      router.push(r.user.role === "admin" ? "/admin" : "/account");
    } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }

  return (
    <AuthShell
      biome="forests"
      title="Create your account"
      subtitle={<>Use your <span className="font-medium text-white">@ksrmce.ac.in</span> college email.</>}
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-white underline underline-offset-2 hover:text-white/80">
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <label className={authLabel}>Full name</label>
          <input required value={form.full_name} onChange={set("full_name")} placeholder="Your name" className={authInput} />
        </div>
        <div className="space-y-1.5">
          <label className={authLabel}>College email</label>
          <input type="email" required value={form.email} onChange={set("email")} placeholder="rollno@ksrmce.ac.in" className={authInput} />
        </div>
        <div className="space-y-1.5">
          <label className={authLabel}>Password</label>
          <input type="password" required minLength={8} value={form.password} onChange={set("password")} placeholder="At least 8 characters" className={authInput} />
        </div>
        {err && <p className={authError}>{err}</p>}
        <button type="submit" disabled={loading} className={authButton}>
          {loading ? "Creating…" : "Create account"}
        </button>
      </form>
    </AuthShell>
  );
}
