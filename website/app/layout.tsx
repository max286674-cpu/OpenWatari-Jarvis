import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "OpenWatari — build your own voice-first AI companion",
  description:
    "OpenWatari is an open-source framework for building your own 24/7, voice-first, multi-device AI companion (Watari). Local-first, self-hosted.",
};

const NAV: { head: string; links: [string, string][] }[] = [
  {
    head: "Start",
    links: [
      ["Overview", "/"],
      ["Quick start", "/quickstart"],
      ["Setup & keys", "/setup"],
    ],
  },
  {
    head: "Concepts",
    links: [
      ["Architecture", "/architecture"],
      ["Networking (Tailnet)", "/networking"],
      ["Devices", "/devices"],
      ["Memory", "/architecture#memory"],
    ],
  },
  {
    head: "Operate",
    links: [
      ["Configuration", "/configuration"],
      ["Production readiness", "/production"],
      ["Security", "/security"],
      ["License", "/license"],
    ],
  },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="layout">
          <aside className="sidebar">
            <div className="brand">
              Open<span>Watari</span>
            </div>
            <div className="tag">Build your own Watari.</div>
            {NAV.map((group) => (
              <div key={group.head}>
                <div className="navhead">{group.head}</div>
                <nav>
                  {group.links.map(([label, href]) => (
                    <Link key={href + label} href={href}>
                      {label}
                    </Link>
                  ))}
                </nav>
              </div>
            ))}
            <div className="navhead">Links</div>
            <nav>
              <a href="https://github.com/iamvazghen/OpenWatari" target="_blank" rel="noreferrer">
                GitHub ↗
              </a>
              <a href="https://tailscale.com/" target="_blank" rel="noreferrer">
                Tailscale ↗
              </a>
            </nav>
          </aside>
          <main className="content">
            <div className="inner">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
