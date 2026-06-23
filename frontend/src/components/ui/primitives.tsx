"use client";
import { cn } from "@/lib/utils";
import { forwardRef } from "react";

export const Button = forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "outline" | "danger"; size?: "sm" | "md" | "lg" }>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => {
    const variants = {
      primary: "bg-gradient-to-br from-brand to-brand-2 text-brand-fg hover:brightness-110 shadow-glow",
      ghost: "hover:bg-surface-2 text-fg",
      outline: "border border-border bg-surface-2/40 hover:bg-surface-2 hover:border-brand/40 text-fg",
      danger: "bg-danger/10 text-danger hover:bg-danger/20 border border-danger/30",
    };
    const sizes = { sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-sm", lg: "h-12 px-6 text-base" };
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-150 disabled:opacity-50 disabled:pointer-events-none active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50",
          variants[variant], sizes[size], className,
        )}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-11 w-full rounded-lg border border-border bg-surface/60 px-3.5 text-sm text-fg placeholder:text-muted transition-colors focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass rounded-xl shadow-soft", className)} {...props} />;
}

export function Badge({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", className)}>
      {children}
    </span>
  );
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-sm font-medium text-fg", className)} {...props} />;
}
