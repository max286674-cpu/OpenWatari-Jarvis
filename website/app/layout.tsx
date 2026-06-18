import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "./_nav";

export const metadata: Metadata = {
  title: "OpenWatari — build your own voice-first AI companion",
  description:
    "OpenWatari is an open-source framework for building your own 24/7, voice-first, multi-device AI companion (Watari). Local-first, self-hosted, no GPU required.",
  icons: { icon: "/logo.png" },
  openGraph: {
    title: "OpenWatari",
    description:
      "Build your own 24/7, voice-first, multi-device AI companion. Local-first, self-hosted.",
    images: ["/banner.png"],
    type: "website",
  },
  twitter: { card: "summary_large_image", images: ["/banner.png"] },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="layout">
          <Sidebar />
          <main className="content">
            <div className="inner">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
