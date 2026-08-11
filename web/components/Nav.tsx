"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Build" },
  { href: "/account", label: "Account" },
  { href: "/history", label: "History" },
  { href: "/drift", label: "Changes" },
];

export function Nav() {
  const path = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    // Checked once on load and then every half minute. Without it, a stopped
    // server looks like a broken page — every action fails and nothing says
    // why.
    const check = () =>
      api
        .health()
        .then(() => setOnline(true))
        .catch(() => setOnline(false));
    check();
    const timer = setInterval(check, 30_000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-ink/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-5">
        <Link href="/" className="flex items-center gap-2.5 shrink-0">
          <Cloud />
          <span className="text-[15px] font-semibold tracking-tight">Stratus</span>
        </Link>

        <nav className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active = path === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
                  active
                    ? "bg-panel-2 text-text"
                    : "text-dim hover:bg-panel hover:text-text"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2 text-xs text-dim">
          <span
            className={`h-2 w-2 rounded-full ${
              online === null
                ? "bg-dim pulse-soft"
                : online
                  ? "bg-ok"
                  : "bg-danger"
            }`}
          />
          {online === null ? "checking" : online ? "connected" : "server offline"}
        </div>
      </div>
    </header>
  );
}

function Cloud() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6.5 18.5A4.5 4.5 0 0 1 6 9.56a6 6 0 0 1 11.6-1.2A4.25 4.25 0 0 1 17.5 18.5h-11Z"
        stroke="var(--color-accent)"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}
