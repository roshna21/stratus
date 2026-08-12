"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Dot, buttonClass } from "@/components/ui";

const APP_LINKS = [
  { href: "/build", label: "Build" },
  { href: "/account", label: "Account" },
  { href: "/history", label: "History" },
  { href: "/drift", label: "Changes" },
];

export function Nav() {
  const path = usePathname();
  const onLanding = path === "/";

  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-canvas/80 backdrop-blur-xl">
      <div
        className={`mx-auto flex h-14 items-center gap-6 px-5 ${
          onLanding ? "max-w-6xl" : "max-w-5xl"
        }`}
      >
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5"
          aria-label="Stratus home"
        >
          <Logo />
          <span className="text-[15px] font-semibold tracking-tight">Stratus</span>
        </Link>

        {onLanding ? <LandingLinks /> : <AppLinks path={path} />}
      </div>
    </header>
  );
}

function LandingLinks() {
  return (
    <>
      <nav className="ml-2 hidden items-center gap-1 md:flex">
        {[
          { href: "#how", label: "How it works" },
          { href: "#capabilities", label: "What it does" },
          { href: "#stack", label: "Stack" },
        ].map((l) => (
          <a
            key={l.href}
            href={l.href}
            className="rounded-lg px-3 py-1.5 text-sm text-fg-muted transition-colors hover:bg-raised hover:text-fg"
          >
            {l.label}
          </a>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <a
          href="https://github.com/roshna21/stratus"
          target="_blank"
          rel="noreferrer"
          className={buttonClass("ghost", "sm")}
        >
          <GitHubMark />
          <span className="hidden sm:inline">GitHub</span>
        </a>
        <Link href="/build" className={buttonClass("primary", "sm")}>
          Open the app
        </Link>
      </div>
    </>
  );
}

function AppLinks({ path }: { path: string }) {
  return (
    <>
      <nav className="flex items-center gap-0.5 overflow-x-auto">
        {APP_LINKS.map((link) => {
          const active = path === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={`shrink-0 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                active
                  ? "bg-raised text-fg"
                  : "text-fg-muted hover:bg-surface hover:text-fg"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>

      <div className="ml-auto shrink-0">
        <ServerStatus />
      </div>
    </>
  );
}

/**
 * Whether the API is answering.
 *
 * Checked once on load and then every half minute. Without it, a stopped
 * server looks like a broken page — every action fails and nothing says why.
 *
 * Only rendered inside the app. The landing page is static and must look
 * right to someone who has never started a server; telling that visitor the
 * server is offline would report a fault that does not exist.
 */
function ServerStatus() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
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
    <span className="flex items-center gap-2 rounded-full border border-hairline bg-surface px-2.5 py-1 font-mono text-[11px] text-fg-muted">
      <Dot tone={online === null ? "neutral" : online ? "ok" : "danger"} />
      <span className="hidden sm:inline">
        {online === null ? "checking" : online ? "connected" : "server offline"}
      </span>
    </span>
  );
}

/**
 * Layered bars: strata, which is what the name means, and also what the
 * product builds. A literal cloud outline is the icon every cloud tool
 * already uses.
 */
export function Logo({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="4" y="5" width="16" height="3.4" rx="1.7" fill="var(--color-accent)" />
      <rect
        x="2.5"
        y="10.3"
        width="19"
        height="3.4"
        rx="1.7"
        fill="var(--color-accent)"
        opacity="0.62"
      />
      <rect
        x="6.5"
        y="15.6"
        width="11"
        height="3.4"
        rx="1.7"
        fill="var(--color-accent)"
        opacity="0.32"
      />
    </svg>
  );
}

function GitHubMark() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.4 7.4 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}
