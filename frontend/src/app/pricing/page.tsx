import LegalShell, { H2, P, LI } from "@/components/LegalShell";

export const metadata = { title: "Pricing — K-GPT" };

function PlanCard({ name, price, per, note, best }: { name: string; price: string; per: string; note: string; best?: boolean }) {
  return (
    <div className={`rounded-2xl border p-6 ${best ? "border-brand bg-brand/5" : "border-border bg-surface-2"}`}>
      {best && <span className="mb-2 inline-block rounded-full bg-brand/15 px-3 py-0.5 text-xs font-semibold text-brand">Best value</span>}
      <h3 className="text-lg font-bold text-fg">{name}</h3>
      <div className="mt-2 text-3xl font-black text-fg">{price}<span className="text-base font-medium text-muted"> / {per}</span></div>
      <p className="mt-2 text-sm text-muted">{note}</p>
    </div>
  );
}

export default function PricingPage() {
  return (
    <LegalShell title="Pricing" subtitle="Simple, rupee-priced campus plans — all taxes included">
      <P>
        K-GPT is available to KSRMCE students and staff on the introductory plans below. All prices are
        in Indian Rupees and are <strong>inclusive of GST and all applicable taxes</strong>. Payments are
        processed securely through Razorpay (UPI, cards, net banking).
      </P>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <PlanCard name="Monthly Access" price="₹99" per="month" note="Flexible month-to-month access. Great for exam months." />
        <PlanCard name="Semester Access" price="₹349" per="semester" note="≈ ₹58/month — best value for the full term." best />
      </div>

      <H2>What every plan includes</H2>
      <ul className="mt-3 list-disc space-y-1 pl-6">
        <LI>Answers grounded in the college&rsquo;s verified material, with citations</LI>
        <LI>Support for English and 22 Indian languages</LI>
        <LI>Document &amp; handwritten-note reading (OCR), figures, charts and LaTeX maths</LI>
        <LI>Private chat history and personal notes memory</LI>
        <LI>Strict (exam-accurate) mode and academic-integrity coaching</LI>
        <LI>Fair-use daily limits to keep the service fast and affordable for everyone</LI>
      </ul>

      <H2>Billing</H2>
      <P>
        Access activates immediately after successful payment and remains valid for the plan duration
        (30 days for Monthly; one semester for Semester). Introductory pricing may change for future
        terms; your current term is unaffected. See our{" "}
        <a className="text-brand hover:underline" href="/refund">Cancellation &amp; Refund Policy</a> and{" "}
        <a className="text-brand hover:underline" href="/terms">Terms &amp; Conditions</a>.
      </P>
    </LegalShell>
  );
}
