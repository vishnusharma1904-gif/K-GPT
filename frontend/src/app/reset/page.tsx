"use client";
import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Logo } from "@/components/Logo";
import { Button, Card, Input, Label } from "@/components/ui/primitives";
import { api } from "@/lib/api";

function ResetInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const token = params.get("token");
    if (!token) { setErr("Missing reset token."); return; }
    try { await api.reset(token, password); setDone(true); }
    catch (e: any) { setErr(e.message); }
  }
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm p-8">
        <Logo size={28} className="mx-auto mb-6" />
        {done ? (
          <div className="text-center">
            <h1 className="mb-2 text-lg font-bold">Password updated ✓</h1>
            <Button className="mt-2 w-full" onClick={() => router.push("/login")}>Log in</Button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <h1 className="text-center text-lg font-bold">Choose a new password</h1>
            <div><Label>New password</Label><Input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1.5" /></div>
            {err && <p className="text-sm text-danger">{err}</p>}
            <Button type="submit" className="w-full">Update password</Button>
          </form>
        )}
      </Card>
    </div>
  );
}

export default function ResetPage() {
  return <Suspense fallback={null}><ResetInner /></Suspense>;
}
