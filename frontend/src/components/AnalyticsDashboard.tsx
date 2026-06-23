"use client";
/* Admin analytics dashboard (P45) — consumes /api/admin/analytics.
   Dependency-free SVG charts so there's no bundle cost. Raw token counts are
   admin-only here (per the percentage-only contract, students never see these). */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, Badge } from "@/components/ui/primitives";

type Analytics = {
  window_days: number;
  totals: { students: number; active_subs: number; wau: number; cost_usd: number };
  tier_distribution: Record<string, number>;
  sub_distribution: Record<string, number>;
  model_mix: [string, number][];
  daily: { day: string; active_users: number; tokens: number }[];
};

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Card className="p-4">
      <div className="text-2xl font-semibold text-fg">{value}</div>
      <div className="text-xs text-muted mt-1">{label}</div>
    </Card>
  );
}

function Bars({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="space-y-2">
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-3">
          <div className="w-28 shrink-0 truncate text-xs text-muted" title={d.label}>{d.label}</div>
          <div className="h-3 flex-1 rounded-full bg-surface-2 overflow-hidden">
            <div className="h-full rounded-full bg-brand" style={{ width: `${(d.value / max) * 100}%` }} />
          </div>
          <div className="w-12 shrink-0 text-right text-xs tabular-nums text-fg">{d.value}</div>
        </div>
      ))}
    </div>
  );
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return <div className="text-xs text-muted">Not enough data yet.</div>;
  const max = Math.max(1, ...points);
  const w = 600, h = 80;
  const step = w / (points.length - 1);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${i * step},${h - (p / max) * h}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-20" preserveAspectRatio="none">
      <path d={path} fill="none" stroke="currentColor" strokeWidth={2} className="text-brand" />
    </svg>
  );
}

export default function AnalyticsDashboard() {
  const [data, setData] = useState<Analytics | null>(null);
  const [days, setDays] = useState(14);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.admin.analytics(days).then(setData).catch((e) => setErr(e.message));
  }, [days]);

  if (err) return <Card className="p-4 text-sm text-danger">{err}</Card>;
  if (!data) return <Card className="p-4 text-sm text-muted">Loading analytics…</Card>;

  const tierBars = Object.entries(data.tier_distribution).map(([k, v]) => ({ label: k, value: v }));
  const subBars = Object.entries(data.sub_distribution).map(([k, v]) => ({ label: k, value: v }));
  const modelBars = data.model_mix.map(([m, c]) => ({ label: m.split("/").pop() || m, value: c }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-fg">Analytics</h2>
        <div className="flex gap-2">
          {[7, 14, 30].map((d) => (
            <button key={d} onClick={() => setDays(d)}
              className={`rounded-lg px-3 py-1.5 text-xs ${days === d ? "bg-brand text-brand-fg" : "bg-surface-2 text-muted"}`}>
              {d}d
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Students" value={data.totals.students} />
        <Stat label="Active subscriptions" value={data.totals.active_subs} />
        <Stat label={`WAU (${data.window_days}d)`} value={data.totals.wau} />
        <Stat label="Provider cost (USD)" value={`$${data.totals.cost_usd.toFixed(2)}`} />
      </div>

      <Card className="p-4">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-sm font-medium text-fg">Daily active users</span>
          <Badge className="bg-brand/10 text-brand">admin view · raw</Badge>
        </div>
        <Sparkline points={data.daily.map((d) => d.active_users)} />
      </Card>

      <div className="grid md:grid-cols-2 gap-4">
        <Card className="p-4">
          <div className="mb-3 text-sm font-medium text-fg">Tier distribution</div>
          <Bars data={tierBars.length ? tierBars : [{ label: "normal", value: 0 }]} />
        </Card>
        <Card className="p-4">
          <div className="mb-3 text-sm font-medium text-fg">Subscription status</div>
          <Bars data={subBars.length ? subBars : [{ label: "inactive", value: 0 }]} />
        </Card>
      </div>

      <Card className="p-4">
        <div className="mb-3 text-sm font-medium text-fg">Model mix (requests)</div>
        <Bars data={modelBars.length ? modelBars : [{ label: "—", value: 0 }]} />
      </Card>
    </div>
  );
}
