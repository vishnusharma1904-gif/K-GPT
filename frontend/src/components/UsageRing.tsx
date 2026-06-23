"use client";
import { motion } from "framer-motion";

const STATE_LABEL: Record<string, string> = {
  comfortable: "Comfortable",
  getting_close: "Getting close",
  almost: "Almost at today's limit",
  reached: "Daily limit reached",
};
const STATE_COLOR: Record<string, string> = {
  comfortable: "hsl(var(--accent))",
  getting_close: "hsl(45 90% 55%)",
  almost: "hsl(28 90% 55%)",
  reached: "hsl(var(--danger))",
};

/** Percentage-only usage ring. NEVER shows a token count — by design. */
export function UsageRing({ percent, state, size = 132 }: { percent: number; state: string; size?: number }) {
  const r = (size - 16) / 2;
  const c = 2 * Math.PI * r;
  const color = STATE_COLOR[state] || STATE_COLOR.comfortable;
  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--surface-2))" strokeWidth={10} />
          <motion.circle
            cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={10} strokeLinecap="round"
            strokeDasharray={c}
            initial={{ strokeDashoffset: c }}
            animate={{ strokeDashoffset: c - (percent / 100) * c }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-extrabold tabular-nums">{percent}%</span>
          <span className="text-[11px] text-muted">used today</span>
        </div>
      </div>
      <span className="mt-3 text-sm font-medium" style={{ color }}>{STATE_LABEL[state] || ""}</span>
    </div>
  );
}
