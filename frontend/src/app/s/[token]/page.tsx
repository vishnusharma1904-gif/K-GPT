"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Logo } from "@/components/Logo";
import { Markdown } from "@/components/Markdown";
import { Sparkles, User } from "lucide-react";
import { api } from "@/lib/api";

export default function SharedChatPage() {
  const params = useParams();
  const token = params?.token as string;
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    api.share.public(token).then(setData).catch(() => setErr(true));
  }, [token]);

  if (err) return <div className="flex h-screen items-center justify-center text-muted">This shared chat is unavailable.</div>;
  if (!data) return <div className="flex h-screen items-center justify-center text-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center gap-3 border-b pb-4">
        <Logo size={24} /><div><h1 className="font-bold">{data.session?.title || "Shared chat"}</h1>
        <p className="text-xs text-muted">Read-only · shared from K-GPT</p></div>
      </div>
      {data.messages.map((m: any, i: number) => (
        <div key={i} className={`mb-5 flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
          <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${m.role === "user" ? "bg-surface-2" : "bg-brand/15 text-brand"}`}>
            {m.role === "user" ? <User size={16} /> : <Sparkles size={16} />}
          </div>
          <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${m.role === "user" ? "bg-brand text-brand-fg" : "glass"}`}>
            {m.role === "assistant" ? <Markdown content={m.content} /> : <p className="whitespace-pre-wrap text-sm">{m.content}</p>}
          </div>
        </div>
      ))}
      <p className="mt-8 text-center text-xs text-muted">Powered by K-GPT — KSRM College of Engineering</p>
    </div>
  );
}
