"use client";
/* useTilt — pointer-reactive 3D tilt with a moving specular highlight.
   Returns a ref to attach to the card element. Respects reduced-motion. */
import { useRef, useEffect } from "react";

export function useTilt(max = 10, glare = true) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (window.matchMedia("(hover: none)").matches) return; // skip on touch

    let raf = 0;
    function onMove(e: PointerEvent) {
      const r = el!.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width;
      const py = (e.clientY - r.top) / r.height;
      const rx = (0.5 - py) * max * 2;
      const ry = (px - 0.5) * max * 2;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        el!.style.transform = `rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg) translateZ(0)`;
        if (glare) {
          el!.style.setProperty("--mx", `${(px * 100).toFixed(1)}%`);
          el!.style.setProperty("--my", `${(py * 100).toFixed(1)}%`);
        }
      });
    }
    function reset() {
      cancelAnimationFrame(raf);
      el!.style.transform = "rotateX(0deg) rotateY(0deg)";
    }
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", reset);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", reset);
      cancelAnimationFrame(raf);
    };
  }, [max, glare]);

  return ref;
}
