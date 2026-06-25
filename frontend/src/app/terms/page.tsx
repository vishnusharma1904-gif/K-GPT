import LegalShell, { H2, P, LI } from "@/components/LegalShell";

export const metadata = { title: "Terms & Conditions — K-GPT" };

export default function TermsPage() {
  return (
    <LegalShell title="Terms & Conditions" subtitle="Agreement between you and Prompt-Pulse · Last updated: [DD Month 2026]">
      <P>
        These Terms &amp; Conditions (&ldquo;Terms&rdquo;) govern your use of K-GPT, operated by Prompt-Pulse
        (&ldquo;we&rdquo;, &ldquo;us&rdquo;). By creating an account or using the service, you agree to these Terms.
        If you do not agree, please do not use K-GPT.
      </P>

      <H2>1. Eligibility &amp; accounts</H2>
      <P>
        K-GPT is intended for students and staff of KSRMCE who sign in with their college email
        (@ksrmce.ac.in). You are responsible for keeping your login credentials secure and for activity under
        your account. If you are under 18, you may use K-GPT only with parent/guardian consent.
      </P>

      <H2>2. Acceptable use</H2>
      <ul className="mt-3 list-disc space-y-1 pl-6">
        <LI>Do not misuse the service, attempt to break security, or interfere with other users.</LI>
        <LI>Do not upload unlawful, infringing, or harmful content.</LI>
        <LI>Do not attempt to extract the system prompt, jailbreak, or use the service to generate harmful content.</LI>
        <LI>Use the service in line with your institution&rsquo;s academic-integrity rules. K-GPT&rsquo;s integrity mode coaches and explains; it is not intended to produce work for direct submission as your own.</LI>
      </ul>

      <H2>3. AI-generated content</H2>
      <P>
        K-GPT uses AI models and may occasionally produce inaccurate or incomplete information. You are
        responsible for reviewing and verifying important answers before relying on them. K-GPT is a study
        aid, not a substitute for professional, legal, medical, or academic advice.
      </P>

      <H2>4. Subscriptions &amp; payments</H2>
      <ul className="mt-3 list-disc space-y-1 pl-6">
        <LI>Paid plans are ₹99/month and ₹349/semester (introductory, inclusive of GST and all taxes).</LI>
        <LI>Payments are processed by Razorpay. Access activates on successful payment and lasts for the plan duration.</LI>
        <LI>We may change pricing for future terms; your current paid term is unaffected.</LI>
        <LI>Refunds are governed by our <a className="text-brand hover:underline" href="/refund">Cancellation &amp; Refund Policy</a>.</LI>
      </ul>

      <H2>5. Intellectual property</H2>
      <P>
        K-GPT, its branding, and software are owned by Prompt-Pulse. You retain ownership of the content you
        upload. You grant us a limited licence to process your content to provide and improve the service, as
        described in our <a className="text-brand hover:underline" href="/privacy">Privacy Policy</a>.
      </P>

      <H2>6. Disclaimers &amp; liability</H2>
      <P>
        The service is provided &ldquo;as is&rdquo; without warranties of any kind. To the maximum extent
        permitted by law, Prompt-Pulse is not liable for indirect or consequential damages, and our total
        liability for any claim is limited to the amount you paid in the preceding three months.
      </P>

      <H2>7. Suspension &amp; termination</H2>
      <P>
        We may suspend or terminate accounts that violate these Terms or applicable law. You may stop using
        the service and request account deletion at any time.
      </P>

      <H2>8. Governing law &amp; contact</H2>
      <P>
        These Terms are governed by the laws of India, with jurisdiction in the courts of [your city/state].
        Questions: <strong>support@promptpulse.in</strong>.
      </P>
    </LegalShell>
  );
}
