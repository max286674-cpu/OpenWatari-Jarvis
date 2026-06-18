"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV: { head: string; links: [string, string][] }[] = [
  {
    head: "Start",
    links: [
      ["Overview", "/"],
      ["Quick start", "/quickstart"],
      ["Setup & keys", "/setup"],
      ["Personalize", "/personalize"],
    ],
  },
  {
    head: "Capabilities",
    links: [
      ["Features", "/features"],
      ["Integrations & tools", "/integrations"],
      ["Obsidian vault & memory", "/vault"],
    ],
  },
  {
    head: "Concepts",
    links: [
      ["Architecture", "/architecture"],
      ["Networking (Tailnet)", "/networking"],
      ["Devices", "/devices"],
      ["Phones (iPhone/Android)", "/phones"],
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

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <Link href="/" className="brandrow" style={{ color: "inherit" }}>
        <img src="/logo.png" alt="OpenWatari" />
        <span className="wm">
          Open<span>Watari</span>
        </span>
      </Link>
      <div className="tag">Build your own Watari.</div>

      {NAV.map((group) => (
        <div key={group.head}>
          <div className="navhead">{group.head}</div>
          <nav>
            {group.links.map(([label, href]) => {
              const active = href === "/" ? path === "/" : path.startsWith(href);
              return (
                <Link key={href + label} href={href} className={active ? "active" : ""}>
                  {label}
                </Link>
              );
            })}
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
  );
}
