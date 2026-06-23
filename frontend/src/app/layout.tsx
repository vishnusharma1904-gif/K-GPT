import "./globals.css";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github-dark.css";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "K-GPT · KSRM Campus AI",
  description: "Your private, general-purpose AI assistant for the KSRMCE community.",
  manifest: "/manifest.webmanifest",
  applicationName: "K-GPT",
  appleWebApp: { capable: true, title: "K-GPT", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0a12" },
    { media: "(prefers-color-scheme: light)", color: "#f4f6fb" },
  ],
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
