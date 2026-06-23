"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Logo } from "@/components/Logo";
import { Button, Card, Input, Label } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export default function ForgotPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try { await api.forgot(email); } catch {}
    setSent(true);
  }
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm p-8">
        <Logo size={28} className="mx-auto mb-6" />
        {sent ? (
          <div className="text-center">
            <h1 className="mb-2 text-lg font-bold">Check your email</h1>
            <p className="mb-4 text-sm text-muted">If an account exists for {email}, we sent a reset link.</p>
            <Button variant="outline" className="w-full" onClick={() => router.push("/login")}>Back to login</Button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <h1 className="text-center text-lg font-bold">Reset your password</h1>
            <div><Label>College email</Label><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1.5" placeholder="rollno@ksrmce.ac.in" /></div>
            <Button type="submit" className="w-full">Send reset link</Button>
          </form>
        )}
      </Card>
    </div>
  );
}
