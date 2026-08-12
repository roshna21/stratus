import type { Metadata } from "next";

/*
 * The page itself is a client component, and a client component cannot
 * export metadata — so the title lives here. Without it every screen in the
 * app shares the landing page's title, and a row of browser tabs says
 * nothing about which one is which.
 */
export const metadata: Metadata = {
  title: "Build",
  description: "Describe what you need in plain English and see exactly what would change before anything happens.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
