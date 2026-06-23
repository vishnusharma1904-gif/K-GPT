"use client";
/* Public status page (P47). Unauthenticated; reads /api/status. */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, Badge } from "@/components/ui/primitives";
import { Logo } from "@/components/Logo";

type Status = {
  status: "operational" | "degraded" | "outage";
  checked_at: string;
  degraded_models: string[];
  incidents: { id: string; title: string; severity: string; status: string; created_at: string }[];
};

const TONE: Record<string, string> = {
  operational: "bg-success/15 text-success",
  degraded: "bg-warning/15 text-warning",
  outage: "bg-danger/15 text-danger",
};
const LABEL: Record<string, string> = {
  operational: "All systems operational",
  degraded: "Partial degradation",
  outage: "Major outage",
};

export default function StatusPage() {
  const [s, setS] = useState<Status | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const load = () => api.status.public().then(setS).catch((e) => setErr(e.message));
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <div className="mb-8 flex items-center gap-3">
        <Logo />
        <h1 className="text-xl font-semibold text-fg">K-GPT Status</h1>
      </div>

      {err && <Card className="p-4 text-sm text-danger">{err}</Card>}

      {s && (
        <>
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <span className="text-lg font-medium text-fg">{LABEL[s.status]}</span>
              <Badge className={TONE[s.status]}>{s.status}</Badge>
            </div>
            <div className="mt-2 text-xs text-muted">
              Last checked {new Date(s.checked_at).toLocaleString()}
            </div>
          </Card>

          {s.degraded_models.length > 0 && (
            <Card className="mt-4 p-4">
              <div className="text-sm font-medium text-fg mb-2">Temporarily routed around</div>
              <div className="flex flex-wrap gap-2">
                {s.degraded_models.map((m) => (
                  <Badge key={m} className="bg-warning/10 text-warning">{m}</Badge>
                ))}
              </div>
              <p className="mt-2 text-xs text-muted">
                These models tripped a circuit breaker; requests automatically fail over to
                healthy alternatives, so chat keeps working.
              </p>
            </Card>
          )}

          <div className="mt-6">
            <h2 className="mb-2 text-sm font-medium text-fg">Incidents</h2>
            {s.incidents.length === 0 ? (
              <Card className="p-4 text-sm text-muted">No incidents reported.</Card>
            ) : (
              <div className="space-y-2">
                {s.incidents.map((i) => (
                  <Card key={i.id} className="p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-fg">{i.title}</span>
                      <Badge className={TONE[i.severity === "critical" ? "outage" : "degraded"]}>
                        {i.severity}
                      </Badge>
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      {i.status} · {new Date(i.created_at).toLocaleString()}
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </main>
  );
}
