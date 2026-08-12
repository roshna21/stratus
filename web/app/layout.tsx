import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";

/*
 * Two faces, each with a job.
 *
 * Inter carries the product's own voice. JetBrains Mono carries the
 * machine's — logs, identifiers, costs, anything Stratus is quoting rather
 * than saying. Keeping that split consistent means a monospaced run of text
 * is a signal in itself, before it is read.
 *
 * Loaded through next/font so they are self-hosted and preloaded: no
 * request to a third party, and no flash of a fallback face on first paint.
 */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono-face",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Stratus — infrastructure from a sentence",
    template: "%s · Stratus",
  },
  description:
    "Describe the infrastructure you need in plain English. An agent designs it, shows you exactly what would change and what it would cost, and builds it on Azure once you agree.",
  openGraph: {
    title: "Stratus — infrastructure from a sentence",
    description:
      "Describe what you need in plain English. See the change and the cost before anything happens. Approve it, and it gets built.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <div className="flex min-h-screen flex-col">
          <Nav />
          <main className="flex-1">{children}</main>
          <Footer />
        </div>
      </body>
    </html>
  );
}
