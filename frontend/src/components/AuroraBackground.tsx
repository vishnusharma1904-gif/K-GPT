"use client";
/* Decorative animated hero background: drifting aurora blobs + floating glass
   orbs + a faded moving grid + a slow conic glow + a holographic sweep +
   vignette. Pure CSS/SVG + framer-motion — no image/video assets, GPU-cheap
   (only transform/opacity animate). Respects prefers-reduced-motion. */
import { motion } from "framer-motion";

const BLOBS = [
  { className: "left-[-10%] top-[-12%] h-[44rem] w-[44rem] bg-brand/30",
    anim: { x: [0, 60, -30, 0], y: [0, 40, 70, 0], scale: [1, 1.14, 0.96, 1] }, dur: 22 },
  { className: "right-[-12%] top-[-6%] h-[40rem] w-[40rem] bg-accent/25",
    anim: { x: [0, -50, 30, 0], y: [0, 50, 20, 0], scale: [1, 0.94, 1.12, 1] }, dur: 26 },
  { className: "left-[18%] bottom-[-28%] h-[42rem] w-[42rem] bg-brand-2/22",
    anim: { x: [0, 40, -40, 0], y: [0, -30, 20, 0], scale: [1, 1.1, 0.98, 1] }, dur: 30 },
  { className: "right-[14%] bottom-[-18%] h-[30rem] w-[30rem] bg-accent-2/18",
    anim: { x: [0, -30, 30, 0], y: [0, 24, -16, 0], scale: [1, 1.06, 0.94, 1] }, dur: 34 },
];

const ORBS = [
  { left: "12%", top: "30%", size: 90, delay: 0 },
  { left: "82%", top: "26%", size: 64, delay: 1.2 },
  { left: "70%", top: "62%", size: 120, delay: 0.6 },
  { left: "26%", top: "68%", size: 50, delay: 1.8 },
];

export default function AuroraBackground() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* deep base wash */}
      <div className="absolute inset-0 bg-[radial-gradient(1300px_760px_at_50%_-10%,hsl(var(--brand)/0.20),transparent_60%)]" />

      {/* drifting aurora blobs */}
      {BLOBS.map((b, i) => (
        <motion.div
          key={i}
          className={`absolute rounded-full blur-[120px] ${b.className}`}
          animate={b.anim}
          transition={{ duration: b.dur, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}

      {/* slow conic glow ring behind the headline */}
      <div className="absolute left-1/2 top-[34%] h-[48rem] w-[48rem] -translate-x-1/2 -translate-y-1/2 opacity-40">
        <div className="animate-spin-slow h-full w-full rounded-full bg-[conic-gradient(from_0deg,transparent,hsl(var(--brand)/0.35),transparent_30%,hsl(var(--accent)/0.32),transparent_60%,hsl(var(--brand-2)/0.3),transparent_90%)] blur-2xl" />
      </div>

      {/* holographic diagonal sweep */}
      <motion.div
        className="absolute inset-0 opacity-30 bg-[linear-gradient(115deg,transparent_30%,hsl(var(--accent)/0.12)_46%,hsl(var(--brand)/0.16)_52%,transparent_68%)] bg-[length:300%_100%]"
        animate={{ backgroundPosition: ["0% 0%", "300% 0%"] }}
        transition={{ duration: 12, repeat: Infinity, ease: "linear" }}
      />

      {/* floating glass orbs */}
      {ORBS.map((o, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full border border-white/10 bg-white/5 backdrop-blur-md"
          style={{ left: o.left, top: o.top, width: o.size, height: o.size }}
          animate={{ y: [0, -18, 0], opacity: [0.5, 0.85, 0.5] }}
          transition={{ duration: 6 + i, repeat: Infinity, ease: "easeInOut", delay: o.delay }}
        />
      ))}

      {/* faded moving grid */}
      <div className="hero-grid absolute inset-0 opacity-[0.18]" />

      {/* vignette for depth */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,hsl(var(--shadow-color)/0.55))]" />
    </div>
  );
}
