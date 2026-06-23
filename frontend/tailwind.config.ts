import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "hsl(var(--bg))",
        "bg-2": "hsl(var(--bg-2))",
        surface: "hsl(var(--surface))",
        "surface-2": "hsl(var(--surface-2))",
        border: "hsl(var(--border))",
        fg: "hsl(var(--fg))",
        muted: "hsl(var(--muted))",
        brand: {
          DEFAULT: "hsl(var(--brand))",
          2: "hsl(var(--brand-2))",
          fg: "hsl(var(--brand-fg))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          2: "hsl(var(--accent-2))",
        },
        danger: "hsl(var(--danger))",
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
      },
      borderRadius: {
        "2xl": "calc(var(--radius) + 8px)",
        xl: "calc(var(--radius) + 4px)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
        serif: ["Fraunces", "Georgia", "Cambria", "serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px hsl(var(--brand) / 0.3), 0 8px 40px -8px hsl(var(--brand) / 0.45)",
        "glow-lg": "0 0 0 1px hsl(var(--brand) / 0.35), 0 16px 70px -10px hsl(var(--halo) / 0.6)",
        soft: "0 1px 2px hsl(var(--shadow-color) / 0.4), 0 8px 30px -12px hsl(var(--shadow-color) / 0.5)",
        depth: "0 30px 90px -34px hsl(var(--shadow-color) / 0.85)",
        "inner-top": "0 1px 0 hsl(0 0% 100% / 0.06) inset",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "pulse-dot": { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.3" } },
        rise: {
          from: { opacity: "0", transform: "translateY(14px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.96)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s cubic-bezier(0.22,1,0.36,1) both",
        "pulse-dot": "pulse-dot 1.2s ease-in-out infinite",
        rise: "rise 0.5s cubic-bezier(0.22,1,0.36,1) both",
        "scale-in": "scale-in 0.25s cubic-bezier(0.22,1,0.36,1) both",
      },
    },
  },
  plugins: [],
};
export default config;
