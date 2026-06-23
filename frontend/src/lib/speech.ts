"use client";
/* Lightweight speech helpers.
   - Voice input uses the browser SpeechRecognition API (Chrome/Edge/Safari).
     No backend round-trip; fully on-device where the browser supports it.
   - Read-aloud uses window.speechSynthesis. */
import { useEffect, useRef, useState } from "react";

type Rec = any;

export function speechSupported(): boolean {
  if (typeof window === "undefined") return false;
  return !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
}

export function useVoiceInput(onText: (t: string) => void) {
  const [listening, setListening] = useState(false);
  const recRef = useRef<Rec>(null);

  function start() {
    const Ctor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Ctor) return;
    const rec: Rec = new Ctor();
    rec.lang = navigator.language || "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    let final = "";
    rec.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) final += r[0].transcript;
        else interim += r[0].transcript;
      }
      onText((final + interim).trim());
    };
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    try { rec.start(); } catch { setListening(false); }
  }
  function stop() {
    try { recRef.current?.stop(); } catch {}
    setListening(false);
  }
  function toggle() { listening ? stop() : start(); }

  useEffect(() => () => { try { recRef.current?.abort?.(); } catch {} }, []);
  return { listening, start, stop, toggle, supported: speechSupported() };
}

/* Read-aloud: strips markdown noise so the TTS voice reads cleanly. */
export function cleanForSpeech(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, " (code block) ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[#>*_~|]/g, "")
    .replace(/\n{2,}/g, ". ")
    .replace(/\s+/g, " ")
    .trim();
}

export function useReadAloud() {
  const [speakingId, setSpeakingId] = useState<number | null>(null);
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;

  function speak(id: number, text: string) {
    if (!supported) return;
    window.speechSynthesis.cancel();
    if (speakingId === id) { setSpeakingId(null); return; }
    const u = new SpeechSynthesisUtterance(cleanForSpeech(text).slice(0, 4000));
    u.rate = 1.02; u.pitch = 1;
    u.onend = () => setSpeakingId(null);
    u.onerror = () => setSpeakingId(null);
    setSpeakingId(id);
    window.speechSynthesis.speak(u);
  }
  function stop() { if (supported) window.speechSynthesis.cancel(); setSpeakingId(null); }
  useEffect(() => () => { if (supported) window.speechSynthesis.cancel(); }, [supported]);
  return { speak, stop, speakingId, supported };
}
