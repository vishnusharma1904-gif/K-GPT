import LegalShell, { H2, P } from "@/components/LegalShell";

export const metadata = { title: "Contact Us — K-GPT" };

export default function ContactPage() {
  return (
    <LegalShell title="Contact Us" subtitle="We&rsquo;d love to hear from you">
      <P>
        For any questions, support, billing queries, or feedback about K-GPT, please reach out using
        the details below. We aim to respond within 1–2 business days.
      </P>

      <H2>Reach us</H2>
      <div className="mt-3 space-y-2 text-[15px] text-fg/85">
        <p><strong>Business name:</strong> Prompt-Pulse</p>
        <p><strong>Product:</strong> K-GPT — Campus AI for KSRMCE</p>
        <p><strong>Email (support &amp; billing):</strong> support@promptpulse.in</p>
        <p><strong>Grievance Officer:</strong> grievance@promptpulse.in</p>
        <p><strong>Operating hours:</strong> Mon–Sat, 10:00 AM – 6:00 PM IST</p>
        <p className="text-muted">Email is the fastest way to reach us — we reply within 1–2 business days.</p>
      </div>

      <H2>Grievance / data requests</H2>
      <P>
        For privacy or data-related requests (access, correction, deletion, or to withdraw consent for
        model training), contact our Grievance Officer at <strong>grievance@promptpulse.in</strong>. See
        our <a className="text-brand hover:underline" href="/privacy">Privacy Policy</a> for details.
      </P>
    </LegalShell>
  );
}
