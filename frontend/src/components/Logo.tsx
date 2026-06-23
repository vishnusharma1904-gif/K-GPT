export function Logo({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <div className={`flex items-center gap-2.5 select-none ${className}`}>
      <svg width={size} height={size} viewBox="0 0 40 40" fill="none">
        <rect x="2" y="2" width="36" height="36" rx="10" fill="url(#g)" />
        <path d="M12 14h16M20 14v13" stroke="white" strokeWidth="3" strokeLinecap="round" />
        <defs>
          <linearGradient id="g" x1="2" y1="2" x2="38" y2="38">
            <stop stopColor="hsl(160 64% 50%)" />
            <stop offset="1" stopColor="hsl(188 72% 52%)" />
          </linearGradient>
        </defs>
      </svg>
      <span className="text-lg font-extrabold tracking-tight">
        K<span className="text-gradient">-GPT</span>
      </span>
    </div>
  );
}
