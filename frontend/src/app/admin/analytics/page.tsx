"use client";
/* Admin analytics route (P45). Mounts the dashboard; redirects non-admins. */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import AnalyticsDashboard from "@/components/AnalyticsDashboard";

export default function AdminAnalyticsPage() {
  const router = useRouter();
  const [ok, setOk] = useState(false);

  useEffect(() => {
    api.me()
      .then((u: any) => (u.role === "admin" ? setOk(true) : router.replace("/chat")))
      .catch(() => router.replace("/login"));
  }, [router]);

  if (!ok) return <main className="p-8 text-sm text-muted">Checking access…</main>;
  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <AnalyticsDashboard />
    </main>
  );
}
