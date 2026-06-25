import Link from "next/link";
import { Logo } from "@/components/Logo";

export const legalLinks = [
  { href: "/about", label: "About Us" },
  { href: "/contact", label: "Contact Us" },
  { href: "/pricing", label: "Pricing" },
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/terms", label: "Terms & Conditions" },
  { href: "/refund", label: "Cancellation & Refund" },
];

/** Section heading for legal/info pages. */
export function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-8 text-xl font-bold text-fg">{children}</h2>;
}
export function P({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 text-[15px] leading-relaxed text-fg/85">{children}</p>;
}
export function LI({ children }: { children: React.ReactNode }) {
  return <li className="text-[15px] leading-relaxed text-fg/85">{children}</li>;
}

export default function LegalShell({
  title, subtitle, children,
}: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto min-h-screen max-w-3xl px-6">
      <nav className="flex items-center justify-between py-6">
        <Link href="/"><Logo /></Link>
        <div className="flex items-center gap-4 text-sm text-muted">
          <Link href="/login" className="hover:text-fg">Log in</Link>
          <Link href="/signup" className="hover:text-fg">Sign up</Link>
        </div>
      </nav>

      <article className="py-4">
        <h1 className="text-3xl font-black tracking-tight text-fg sm:text-4xl">{title}</h1>
        {subtitle && <p className="mt-2 text-sm text-muted">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </article>

      <footer className="mt-16 border-t border-border py-8 text-sm text-muted">
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {legalLinks.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-fg">{l.label}</Link>
          ))}
        </div>
        <p className="mt-4">Prompt-Pulse · K-GPT for KSRMCE · © {new Date().getFullYear()}</p>
      </footer>
    </main>
  );
}
