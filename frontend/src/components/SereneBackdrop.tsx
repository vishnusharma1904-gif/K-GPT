/* =============================================================================
 *  K-GPT · SereneBackdrop
 *  A lightweight, GPU-cheap "nature serene" background for data-heavy pages
 *  (chat, account, settings, admin). No WebGL — just layered token-tinted
 *  gradients with a couple of slowly drifting light blooms and a faint sun.
 *  Fixed behind everything (-z-10); inherits the theme via CSS variables.
 * ========================================================================== */

export default function SereneBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* base wash: soft sky → horizon → forest floor */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(1200px 720px at 18% -8%, hsl(var(--brand) / 0.16), transparent 56%)," +
            "radial-gradient(1000px 560px at 92% -6%, hsl(var(--accent) / 0.18), transparent 52%)," +
            "radial-gradient(1200px 840px at 50% 120%, hsl(var(--accent-2) / 0.16), transparent 62%)",
        }}
      />
      {/* warm sun bloom, upper-right */}
      <div
        className="absolute -top-40 right-[-12%] h-[44rem] w-[44rem] rounded-full blur-3xl animate-pulse-soft"
        style={{ background: "radial-gradient(circle, hsl(var(--accent) / 0.20), transparent 60%)" }}
      />
      {/* emerald mist, lower-left, gently floating */}
      <div
        className="absolute bottom-[-22%] left-[-12%] h-[42rem] w-[42rem] rounded-full blur-3xl animate-float-y"
        style={{ background: "radial-gradient(circle, hsl(var(--brand) / 0.18), transparent 60%)" }}
      />
      {/* teal haze drifting through the middle */}
      <div
        className="absolute left-1/2 top-1/3 h-[38rem] w-[38rem] -translate-x-1/2 rounded-full blur-3xl animate-spin-slow"
        style={{ background: "radial-gradient(circle, hsl(var(--brand-2) / 0.12), transparent 62%)" }}
      />
      {/* subtle vignette for depth + legibility */}
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(120% 120% at 50% 30%, transparent 55%, hsl(var(--shadow-color) / 0.22))" }}
      />
    </div>
  );
}
