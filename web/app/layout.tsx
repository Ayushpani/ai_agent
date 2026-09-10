import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Portfolio Intelligence Agent",
  description: "Natural-language analytics over the loan portfolio MIS.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // The document itself scrolls — no h-full lock, no inner scroll
  // container. A nested scroller only responds to the wheel while the
  // cursor is inside it, which is exactly the behaviour every real chat
  // app avoids.
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable} scroll-smooth`}>
      <body className="min-h-dvh font-sans antialiased">{children}</body>
    </html>
  );
}
