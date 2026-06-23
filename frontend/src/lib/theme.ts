"use client";

export type Theme = "light" | "dark" | "system";

export function getTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return (localStorage.getItem("kgpt_theme") as Theme) || "dark";
}

export function applyTheme(t: Theme) {
  if (typeof window === "undefined") return;
  const sysDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = t === "dark" || (t === "system" && sysDark);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

export function setTheme(t: Theme) {
  if (typeof window === "undefined") return;
  localStorage.setItem("kgpt_theme", t);
  applyTheme(t);
}
