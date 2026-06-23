"use client";
import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Logo } from "@/components/Logo";
import { Button, Card } from "@/components/ui/primitives";
import { api } from "@/lib/api";

function VerifyInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  useEffect(() => {
    const token = params.get("token");
    if (!token) { setState("error"); return; }
    api.verifyEmail(token).then(() => setState("ok")).catch(() => setState("error"));
  }, [params]);
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm p-8 text-center">
        <Logo size={28} className="mx-auto mb-4" />
        {state === "working" && <p className="text-muted">Verifying your email…</p>}
        {state === "ok" && (<>
          <h1 className="mb-2 text-lg font-bold">Email verified ✓</h1>
          <p className="mb-4 text-sm text-muted">Your account is confirmed.</p>
          <Button className="w-full" onClick={() => router.push("/chat")}>Start chatting</Button>
        </>)}
        {state === "error" && (<>
          <h1 className="mb-2 text-lg font-bold">Link invalid or expired</h1>
          <p className="mb-4 text-sm text-muted">Request a new verification email from your account.</p>
          <Button variant="outline" className="w-full" onClick={() => router.push("/login")}>Back to login</Button>
        </>)}
      </Card>
    </div>
  );
}

export default function VerifyPage() {
  return <Suspense fallback={null}><VerifyInner /></Suspense>;
}
