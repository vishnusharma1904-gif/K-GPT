"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Script from "next/script";
import { motion } from "framer-motion";
import { Logo } from "@/components/Logo";
import { Button, Card, Badge } from "@/components/ui/primitives";
import { UsageRing } from "@/components/UsageRing";
import { api, getToken } from "@/lib/api";
import SereneBackdrop from "@/components/SereneBackdrop";
import { ArrowLeft, Check, Zap, Gift, Clock } from "lucide-react";

declare global { interface Window { Razorpay: any } }

function countdown(secs: number) {
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60);
  return `${h}h ${m}m`;
}

export default function AccountPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  const [cfg, setCfg] = useState<any>(null);
  const [plans, setPlans] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function loadUsage() { try { setUsage(await api.usage()); } catch {} }
  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api.me().then(setMe).catch(() => router.push("/login"));
    loadUsage();
    api.billing.config().then(setCfg).catch(() => {});
    api.billing.plans().then(setPlans).catch(() => {});
  }, [router]);

  async function claimBonus() {
    setBusy(true); setMsg("");
    try { setUsage(await api.claimBonus()); setMsg("🎁 Weekly bonus added to today's limit."); }
    catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  }

  async function pay(planCode: string, planName: string) {
    setBusy(true); setMsg("");
    try {
      if (!cfg?.online_enabled) {
        setMsg("Online payment isn't enabled yet. Pay the fee to the department and ask admin to activate your account.");
        return;
      }
      const order = await api.billing.order(planCode);
      const rzp = new window.Razorpay({
        key: order.key_id, amount: order.amount, currency: "INR",
        name: "K-GPT · KSRMCE", description: planName,
        order_id: order.order_id,
        handler: async (resp: any) => {
          await api.billing.verify({
            razorpay_order_id: resp.razorpay_order_id,
            razorpay_payment_id: resp.razorpay_payment_id,
            razorpay_signature: resp.razorpay_signature,
          });
          setMsg("✅ Access activated! Redirecting…");
          setTimeout(() => router.push("/chat"), 1200);
        },
        prefill: { name: me?.full_name, email: me?.email },
        theme: { color: "#7c6cf6" },
      });
      rzp.open();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  }

  function tierLine(tier: string) {
    return tier === "heavy" ? "1,000,000 tokens/day" : tier === "monthly" ? "150,000 tokens/day" : "500,000 tokens/day";
  }

  const active = usage?.sub_status === "active" || me?.role === "admin";

  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <SereneBackdrop />
      <Script src="https://checkout.razorpay.com/v1/checkout.js" />
      <div className="mb-8 flex items-center justify-between">
        <Logo />
        <Button variant="ghost" size="sm" onClick={() => router.push("/chat")}><ArrowLeft size={16} /> Back to chat</Button>
      </div>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold">{me?.full_name}</h1>
              <p className="text-sm text-muted">{me?.email}{me?.roll_no ? ` · ${me.roll_no}` : ""}</p>
            </div>
            <div className="flex gap-2">
              {usage?.tier === "heavy" && <Badge className="bg-brand/15 text-brand"><Zap size={12} /> Heavy</Badge>}
              <Badge className={active ? "bg-accent/15 text-accent" : "bg-danger/15 text-danger"}>
                {active ? <><Check size={12} /> Active</> : "Inactive"}
              </Badge>
            </div>
          </div>
        </Card>

        {!active && (
          <Card className="p-6">
            <h2 className="text-lg font-semibold">Choose a plan</h2>
            <p className="mt-1 text-sm text-muted">Pick the access that fits you. All plans include private memory, multi-model chat, study modes and a weekly bonus.</p>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {(plans.length ? plans : (cfg?.plans || [])).map((pl: any) => {
                const rupees = Math.round((pl.price_inr || 0) / 100);
                const featured = pl.code === "monthly";
                return (
                  <div key={pl.code} className={`flex flex-col rounded-xl border p-4 ${featured ? "border-brand bg-brand/5 shadow-glow" : "border-border"}`}>
                    <div className="flex items-center justify-between">
                      <span className="font-semibold">{pl.name}</span>
                      {featured && <Badge className="bg-brand/15 text-brand">New</Badge>}
                    </div>
                    <div className="mt-2 flex items-baseline gap-1">
                      <span className="text-3xl font-extrabold">₹{rupees}</span>
                      <span className="text-xs text-muted">/ {pl.duration_days}d</span>
                    </div>
                    <div className="mt-1 text-xs text-muted">{tierLine(pl.tier)}</div>
                    {pl.tier === "heavy" && <div className="mt-1 text-[11px] text-brand">+ pin any model</div>}
                    <Button onClick={() => pay(pl.code, pl.name)} disabled={busy} size="sm" className="mt-4 w-full" variant={featured ? "primary" : "outline"}>
                      {busy ? "…" : cfg?.online_enabled ? `Get ₹${rupees}` : "How to activate"}
                    </Button>
                  </div>
                );
              })}
            </div>
            {!cfg?.online_enabled && <p className="mt-3 text-xs text-muted">Online payment isn't enabled yet — pay the department and ask an admin to activate your account.</p>}
          </Card>
        )}

        {active && usage && (
          <Card className="p-6">
            <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:justify-between">
              <UsageRing percent={usage.percent_used ?? 0} state={usage.state ?? "comfortable"} />
              <div className="flex-1 sm:pl-6">
                <h2 className="font-semibold">Today's usage</h2>
                <p className="mt-1 flex items-center gap-1.5 text-sm text-muted">
                  <Clock size={14} /> Resets in {countdown(usage.resets_in_seconds ?? 0)}
                </p>
                <div className="mt-4 rounded-xl border border-border bg-surface-2/40 p-4">
                  <div className="flex items-center gap-2 font-medium"><Gift size={16} className="text-accent" /> Weekly bonus</div>
                  <p className="mt-1 text-sm text-muted">
                    {usage.weekly_bonus_available
                      ? "Available — add a one-time boost to today's limit."
                      : "Already used this week. Refreshes weekly."}
                  </p>
                  <Button onClick={claimBonus} disabled={!usage.weekly_bonus_available || busy}
                    variant={usage.weekly_bonus_available ? "primary" : "outline"} size="sm" className="mt-3">
                    {usage.weekly_bonus_available ? "Use weekly bonus" : "Used this week"}
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        )}

        {msg && <p className="rounded-lg bg-surface-2 px-4 py-3 text-sm">{msg}</p>}
      </motion.div>
    </main>
  );
}
