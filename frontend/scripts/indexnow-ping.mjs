#!/usr/bin/env node
/**
 * IndexNow submitter for K-GPT.
 *
 * Instantly tells IndexNow-enabled search engines (Bing, Yandex, Naver, Seznam,
 * and — via the shared protocol — Google's crawl hints) that URLs were added or
 * updated. Run after a deploy or when content changes.
 *
 * Setup (once):
 *   1. A key file already exists at public/<KEY>.txt (the filename IS the key).
 *   2. Export the same key so this script can find it:
 *        export INDEXNOW_KEY=<the key>            # same value as the filename
 *        export SITE_URL=https://kgpt.promptpulse.in
 *
 * Usage:
 *   node scripts/indexnow-ping.mjs                 # submits the default route list
 *   node scripts/indexnow-ping.mjs /pricing /about # submits specific paths
 */

const KEY = process.env.INDEXNOW_KEY;
const HOST = (process.env.SITE_URL || "https://kgpt.promptpulse.in").replace(/\/$/, "");

const DEFAULT_PATHS = [
  "/", "/pricing", "/about", "/contact",
  "/privacy", "/terms", "/refund", "/status",
];

async function main() {
  if (!KEY) {
    console.error("✗ INDEXNOW_KEY is not set. Set it to the filename (without .txt) in public/.");
    process.exit(1);
  }
  const host = new URL(HOST).host;
  const paths = process.argv.slice(2).length ? process.argv.slice(2) : DEFAULT_PATHS;
  const urlList = paths.map((p) => (p.startsWith("http") ? p : `${HOST}${p}`));

  const body = {
    host,
    key: KEY,
    keyLocation: `${HOST}/${KEY}.txt`,
    urlList,
  };

  const res = await fetch("https://api.indexnow.org/indexnow", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  });

  if (res.ok || res.status === 202) {
    console.log(`✓ Submitted ${urlList.length} URL(s) to IndexNow (HTTP ${res.status}).`);
  } else {
    console.error(`✗ IndexNow returned HTTP ${res.status}: ${await res.text()}`);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error("✗ IndexNow ping failed:", e.message);
  process.exit(1);
});
