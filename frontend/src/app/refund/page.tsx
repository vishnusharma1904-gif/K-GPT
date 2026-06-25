import LegalShell, { H2, P, LI } from "@/components/LegalShell";

export const metadata = { title: "Cancellation & Refund Policy — K-GPT" };

export default function RefundPage() {
  return (
    <LegalShell title="Cancellation & Refund Policy" subtitle="For K-GPT subscriptions · Last updated: [DD Month 2026]">
      <P>
        K-GPT is a digital subscription service. This policy explains how cancellations and refunds work.
        By subscribing, you agree to the terms below.
      </P>

      <H2>1. Cancellation</H2>
      <P>
        You can cancel your subscription at any time from your account. Cancellation stops future renewals;
        your access continues until the end of the current paid period (30 days for Monthly, one semester for
        Semester). Plans do not auto-renew unless explicitly stated at checkout.
      </P>

      <H2>2. Refunds</H2>
      <P>
        Because access to the service is granted immediately on payment, fees are generally{" "}
        <strong>non-refundable</strong> once the subscription is active. However, we will provide a full or
        partial refund in these cases:
      </P>
      <ul className="mt-3 list-disc space-y-1 pl-6">
        <LI><strong>Duplicate or accidental payment</strong> — you were charged more than once for the same plan.</LI>
        <LI><strong>Failed activation</strong> — payment succeeded but access was not granted and we cannot resolve it.</LI>
        <LI><strong>Service unavailable</strong> — a prolonged technical failure on our side prevents you from using the service for a significant part of your paid period.</LI>
      </ul>

      <H2>3. How to request a refund</H2>
      <P>
        Email <strong>support@promptpulse.in</strong> from your registered college email within{" "}
        <strong>7 days</strong> of the charge, with your name, registered email, and the payment reference.
        We review eligible requests and, where approved, process refunds to the original payment method,
        typically within <strong>5–7 business days</strong> (timing may vary by bank/Razorpay).
      </P>

      <H2>4. Contact</H2>
      <P>
        For any billing or refund question, contact <strong>support@promptpulse.in</strong>. See also our{" "}
        <a className="text-brand hover:underline" href="/terms">Terms &amp; Conditions</a> and{" "}
        <a className="text-brand hover:underline" href="/pricing">Pricing</a>.
      </P>
    </LegalShell>
  );
}
