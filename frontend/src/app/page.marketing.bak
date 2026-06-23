"use client";
import Link from "next/link";
import { motion } from "framer-motion";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/primitives";
import AuroraBackground from "@/components/AuroraBackground";
import ThemeToggle from "@/components/ThemeToggle";
import { useTilt } from "@/lib/useTilt";
import {
  Brain, Lock, Sparkles, Zap, ShieldCheck, BookOpen, Code, GraduationCap,
  Search, Mic, FileText, ArrowRight,
} from "lucide-react";

const features = [
  { icon: Brain, title: "Remembers what matters", desc: "Private memory of your notes and files — answers grounded in your own material." },
  { icon: Zap, title: "Fast, multi-model", desc: "Routes across 100+ models with automatic fallback. Never stuck on one provider." },
  { icon: Lock, title: "Yours, isolated", desc: "Every student's chats and memory are fully private — no one else can see them." },
  { icon: Sparkles, title: "Modes for anything", desc: "General assistant plus tutor, code mentor, exam-prep and research lenses." },
];

const modes = [
  { icon: BookOpen, name: "Tutor" },
  { icon: Code, name: "Code Mentor" },
  { icon: GraduationCap, name: "Exam Prep" },
  { icon: Search, name: "Researcher" },
];

const stats = [
  { v: "100+", k: "models routed" },
  { v: "384-d", k: "private memory" },
  { v: "<1s", k: "first token" },
  { v: "100%", k: "tenant-isolated" },
];

/** Glassy card with pointer-reactive 3D tilt + moving specular highlight. */
function TiltCard({ children, className = "", max = 9 }: { children: React.ReactNode; className?: string; max?: number }) {
  const ref = useTilt(max);
  return (
    <div className="scene h-full">
      <div
        ref={ref}
        className={`tilt glass group relative h-full overflow-hidden rounded-2xl ${className}`}
      >
        {/* moving glare */}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{ background: "radial-gradient(420px circle at var(--mx,50%) var(--my,50%), hsl(0 0% 100% / 0.10), transparent 45%)" }}
        />
        {children}
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <>
      <AuroraBackground />
      <main className="mx-auto flex min-h-screen max-w-6xl flex-col px-6">
        <nav className="flex items-center justify-between py-6">
          <Logo />
          <div className="flex items-center gap-2">
            <ThemeToggle compact />
            <Link href="/login"><Button variant="ghost" size="sm">Log in</Button></Link>
            <Link href="/signup"><Button size="sm" className="btn-shine">Get started</Button></Link>
          </div>
        </nav>

        <section className="flex flex-1 flex-col items-center justify-center py-16 text-center">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
            <span className="glass inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-medium text-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft" />
              KSRM College of Engineering · Campus AI
            </span>
            <h1 className="mt-6 text-5xl font-black leading-[1.03] tracking-tight sm:text-7xl">
              Your private<br /><span className="aurora-text text-glow">AI assistant</span>
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-lg text-muted">
              K-GPT is a campus-only AI that remembers your courses, helps you code and
              prep for exams, and keeps every conversation private to you.
            </p>
            <div className="mt-9 flex items-center justify-center gap-3">
              <Link href="/signup"><Button size="lg" className="btn-shine">Get started free <ArrowRight size={18} /></Button></Link>
              <Link href="/login"><Button variant="outline" size="lg">I have an account</Button></Link>
            </div>
            <p className="mt-4 inline-flex items-center gap-1.5 text-xs text-muted">
              <ShieldCheck size={13} className="text-success" /> Private by default · @ksrmce.ac.in only
            </p>

            {/* mode chips */}
            <div className="mt-7 flex flex-wrap items-center justify-center gap-2">
              {modes.map((m) => (
                <span key={m.name} className="chip text-muted">
                  <m.icon size={12} className="text-brand" /> {m.name}
                </span>
              ))}
            </div>
          </motion.div>

          {/* Floating glassmorphic app preview with 3D tilt */}
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="mt-16 w-full max-w-2xl"
          >
            <div className="scene">
              <PreviewCard />
            </div>
          </motion.div>

          {/* stats strip */}
          <div className="mt-16 grid w-full max-w-3xl grid-cols-2 gap-3 sm:grid-cols-4">
            {stats.map((s, i) => (
              <motion.div key={s.k}
                initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 + i * 0.06 }}
                className="glass rounded-xl px-4 py-4 text-center">
                <div className="text-2xl font-black tabular text-gradient">{s.v}</div>
                <div className="mt-1 text-xs text-muted">{s.k}</div>
              </motion.div>
            ))}
          </div>

          {/* feature cards (3D tilt) */}
          <div className="mt-16 grid w-full grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((f, i) => (
              <motion.div key={f.title}
                initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.08, duration: 0.45 }}>
                <TiltCard className="p-5 text-left">
                  <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-brand/15 text-brand shadow-glow">
                    <f.icon size={20} />
                  </div>
                  <h3 className="font-semibold">{f.title}</h3>
                  <p className="mt-1 text-sm text-muted">{f.desc}</p>
                </TiltCard>
              </motion.div>
            ))}
          </div>

          {/* secondary capability row */}
          <div className="mt-6 grid w-full grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              { icon: Mic, title: "Talk to it", desc: "Push-to-talk voice input and read-aloud answers." },
              { icon: FileText, title: "Bring your files", desc: "PDF, DOCX, PPTX, XLSX — grounded, cited answers." },
              { icon: Code, title: "Live canvas", desc: "Render HTML/SVG artifacts side-by-side, instantly." },
            ].map((f) => (
              <TiltCard key={f.title} className="p-5 text-left" max={7}>
                <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 text-accent">
                  <f.icon size={18} />
                </div>
                <h3 className="font-semibold">{f.title}</h3>
                <p className="mt-1 text-sm text-muted">{f.desc}</p>
              </TiltCard>
            ))}
          </div>

          {/* CTA */}
          <motion.div
            initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }} transition={{ duration: 0.5 }}
            className="mt-20 w-full">
            <div className="glass-strong holo relative overflow-hidden rounded-2xl px-8 py-12 text-center">
              <div className="hero-grid absolute inset-0 opacity-[0.12]" />
              <h2 className="relative text-3xl font-black tracking-tight sm:text-4xl">
                Ready when you are.
              </h2>
              <p className="relative mx-auto mt-3 max-w-md text-muted">
                Sign in with your campus email and start a private conversation in seconds.
              </p>
              <div className="relative mt-7 flex items-center justify-center gap-3">
                <Link href="/signup"><Button size="lg" className="btn-shine">Create your account <ArrowRight size={18} /></Button></Link>
              </div>
            </div>
          </motion.div>
        </section>

        <footer className="py-8 text-center text-sm text-muted">
          Built by Vishnu Sharma · K-GPT for KSRMCE · {new Date().getFullYear()}
        </footer>
      </main>
    </>
  );
}

function PreviewCard() {
  const ref = useTilt(6);
  return (
    <div ref={ref} className="tilt glass-strong animate-float-y overflow-hidden rounded-2xl text-left">
      <div className="flex items-center gap-2 border-b border-border/70 px-4 py-3">
        <span className="h-3 w-3 rounded-full bg-danger/70" />
        <span className="h-3 w-3 rounded-full bg-warning/70" />
        <span className="h-3 w-3 rounded-full bg-success/70" />
        <span className="ml-3 text-xs text-muted">K-GPT · new chat</span>
      </div>
      <div className="space-y-3 p-5">
        <div className="ml-auto w-fit max-w-[80%] rounded-2xl bg-brand px-4 py-2 text-sm text-brand-fg shadow-glow">
          Explain Ohm&apos;s law with a quick example?
        </div>
        <div className="flex gap-2.5">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand/15 text-brand">
            <Sparkles size={14} />
          </div>
          <div className="glass max-w-[85%] rounded-2xl px-4 py-2.5 text-sm text-fg/90">
            Ohm&apos;s law is <span className="text-gradient font-semibold">V = I × R</span>. If a 9V battery
            drives 3Ω, current is I = V/R = 3A. Want a worked circuit next?
            <div className="mt-2 flex gap-1.5">
              <span className="rounded-md bg-surface-2 px-2 py-0.5 text-[11px] text-muted">groq · llama-3.3</span>
              <span className="rounded-md bg-brand/10 px-2 py-0.5 text-[11px] text-brand">12% used today</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
