import LegalShell, { H2, P, LI } from "@/components/LegalShell";

export const metadata = { title: "Privacy Policy — K-GPT" };

export default function PrivacyPage() {
  return (
    <LegalShell title="Privacy Policy" subtitle="How Prompt-Pulse handles your data in K-GPT · Last updated: [DD Month 2026]">
      <P>
        This policy explains what personal data K-GPT collects, why, how we use it (including to improve
        and train our AI models), who we share it with, how we protect it, and the choices and rights you
        have. By creating an account and using K-GPT, you agree to this policy.
      </P>

      <H2>1. Data we collect</H2>
      <ul className="mt-3 list-disc space-y-1 pl-6">
        <LI><strong>Account data</strong> — name, college email, roll number, role, password (stored only as a secure hash), email-verification status.</LI>
        <LI><strong>Content you provide</strong> — your chat messages and the AI&rsquo;s replies, files and notes you upload, and (when enabled) voice audio you record.</LI>
        <LI><strong>Usage &amp; technical data</strong> — feature usage, token/usage counts, subscription status, timestamps, approximate IP/device info, and error logs.</LI>
        <LI><strong>Payment data</strong> — processed by Razorpay; we receive payment status and identifiers, not your full card/bank details.</LI>
      </ul>

      <H2>2. Data minimisation</H2>
      <P>
        We collect only what the service needs. We do not require sensitive personal data, and we exclude
        and discard data that is unnecessary for running, securing, or improving K-GPT. Where data is used
        beyond providing the service, we de-identify it first.
      </P>

      <H2>3. How we use your data</H2>
      <ul className="mt-3 list-disc space-y-1 pl-6">
        <LI>To provide K-GPT — answer your questions, ground replies in college documents, keep your history and notes memory.</LI>
        <LI>To operate accounts, verify your email (OTP), enforce quotas, and process subscriptions.</LI>
        <LI>To keep the service safe — detect abuse, prevent prompt-injection, review flagged safety events.</LI>
        <LI>To support you, fix problems, and understand aggregate usage to improve features.</LI>
      </ul>

      <H2>4. Using data to improve and train our models</H2>
      <P>
        We may use content and usage data to evaluate, improve, and train or fine-tune the AI models that
        power K-GPT, so the product becomes more accurate and useful for students. We do this responsibly:
      </P>
      <ul className="mt-3 list-disc space-y-1 pl-6">
        <LI><strong>De-identification first</strong> — identifiers (name, roll number, email) are removed before any data is used for training.</LI>
        <LI><strong>Only useful data</strong> — we exclude data that adds no value, anything you mark private, and (where required) data of users under 18.</LI>
        <LI><strong>Your choice</strong> — you can opt out of training use in your account settings at any time, without losing access.</LI>
        <LI><strong>No selling</strong> — we never sell your personal data or use it for third-party advertising.</LI>
      </ul>
      <P>
        By using K-GPT you consent to this processing. You may withdraw consent for training use at any
        time; withdrawal does not affect processing already carried out.
      </P>

      <H2>5. Who we share data with</H2>
      <P>
        We share data only with service providers who help us run K-GPT, under confidentiality terms: AI
        model providers (to generate answers), infrastructure/database hosting (optionally self-hosted on
        institution-controlled servers), Razorpay (payments), and email providers (verification/reset). We
        may share aggregate/administrative information with the institution (KSRMCE), and disclose data
        where required by law.
      </P>

      <H2>6. Security &amp; retention</H2>
      <P>
        We protect data with access controls, encryption in transit (HTTPS), hashed passwords, tenant
        isolation, prompt-injection and leak protections, and safety logging. We keep data while your
        account is active and as needed for legal and operational purposes. You can delete your chats and
        request account deletion, after which we remove or de-identify your personal data within a
        reasonable period.
      </P>

      <H2>7. Your rights</H2>
      <P>
        Subject to India&rsquo;s Digital Personal Data Protection (DPDP) Act, 2023, you may access, correct,
        or delete your data, withdraw consent (including for model training), and raise a grievance.
        Contact our Grievance Officer at <strong>grievance@promptpulse.in</strong>.
      </P>

      <H2>8. Students under 18</H2>
      <P>
        If you are under 18, you may use K-GPT only with the consent of a parent or guardian, as required by
        the DPDP Act. We do not knowingly use the identifiable personal data of users under 18 for model
        training, advertising, or behavioural tracking.
      </P>

      <H2>9. Changes &amp; contact</H2>
      <P>
        We may update this policy as the product evolves and will post the new version with an updated date.
        Questions? Email <strong>support@promptpulse.in</strong>.
      </P>
    </LegalShell>
  );
}
