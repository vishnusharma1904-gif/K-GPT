import "./globals.css";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github-dark.css";
import type { Metadata, Viewport } from "next";
import CookieNotice from "@/components/CookieNotice";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://kgpt.promptpulse.in";
const description =
  "K-GPT is KSRMCE's own campus AI study assistant — answers grounded in your college's verified syllabi and notes, across 22 Indian languages, with private per-student memory. From ₹99/month.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "K-GPT · KSRM Campus AI",
    template: "%s · K-GPT",
  },
  description,
  applicationName: "K-GPT",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "K-GPT", statusBarStyle: "black-translucent" },
  keywords: [
    "K-GPT", "KSRMCE", "campus AI", "study assistant", "AI tutor India",
    "syllabus AI", "RAG", "Prompt-Pulse", "student AI", "exam prep AI",
  ],
  authors: [{ name: "Prompt-Pulse" }],
  creator: "Prompt-Pulse",
  publisher: "Prompt-Pulse",
  alternates: { canonical: "/" },
  // og:image / twitter:image are injected automatically from the
  // app/opengraph-image.png and app/twitter-image.png file conventions.
  openGraph: {
    type: "website",
    url: siteUrl,
    siteName: "K-GPT",
    title: "K-GPT · KSRM Campus AI",
    description,
  },
  twitter: {
    card: "summary_large_image",
    title: "K-GPT · KSRM Campus AI",
    description,
  },
  robots: { index: true, follow: true },
  // Set NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION / NEXT_PUBLIC_BING_SITE_VERIFICATION
  // in the environment to verify ownership in Search Console / Bing Webmaster Tools.
  verification: {
    google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION,
    other: process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION
      ? { "msvalidate.01": process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION }
      : {},
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0a12" },
    { media: "(prefers-color-scheme: light)", color: "#f4f6fb" },
  ],
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
};

// Applied before paint to prevent a flash of the wrong theme.
const themeInit = `
(function(){
  try {
    var t = localStorage.getItem('kgpt_theme') || 'dark';
    var sysDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var dark = t === 'dark' || (t === 'system' && sysDark);
    document.documentElement.classList.toggle('dark', dark);
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
  } catch(e){ document.documentElement.classList.add('dark'); }
})();
`;

// Root layout — global <head>, theme bootstrap, and viewport (mobile-first).
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>
        {children}
        <CookieNotice />
      </body>
    </html>
  );
}
