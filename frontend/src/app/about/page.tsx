import LegalShell, { H2, P, LI } from "@/components/LegalShell";

export const metadata = { title: "About Us — K-GPT" };

export default function AboutPage() {
  return (
    <LegalShell title="About Us" subtitle="Prompt-Pulse · the team behind K-GPT">
      <P>
        Prompt-Pulse is a student-founded technology venture building practical, affordable AI for
        Indian campuses. Our flagship product, <strong>K-GPT</strong>, is a campus-purpose AI study
        assistant built for KSRM College of Engineering (KSRMCE).
      </P>
      <P>
        K-GPT takes the same class of frontier AI models that power tools like ChatGPT and Gemini and
        wraps them in a layer designed for one institution: it answers from the college&rsquo;s own
        verified material with citations, works across English and 22 Indian languages, reads scanned
        and handwritten notes, protects academic integrity, and can run on infrastructure the
        institution controls.
      </P>

      <H2>Our mission</H2>
      <P>
        To give every student affordable, trustworthy, syllabus-grounded study help in their own
        language — and to keep their data private and under institutional control.
      </P>

      <H2>The team</H2>
      <ul className="mt-3 list-disc space-y-1 pl-6">
        <LI><strong>Vishnu Sharma</strong> — Chief Executive Officer; Lead Developer, K-GPT</LI>
        <LI><strong>Shristi</strong> — Chief Technology Officer; Lead Developer (QA &amp; Reliability)</LI>
        <LI><strong>Bandla Rahul</strong> — Chief Financial Officer</LI>
        <LI><strong>Kinkiri Rajeev</strong> — Full-Stack &amp; AI/ML Intern</LI>
      </ul>

      <H2>Contact</H2>
      <P>
        Prompt-Pulse — K-GPT &nbsp;|&nbsp; Email: <strong>support@promptpulse.in</strong>. For more,
        see our <a className="text-brand hover:underline" href="/contact">Contact</a> page.
      </P>
    </LegalShell>
  );
}
