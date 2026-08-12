"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/Nav";

/**
 * The landing page only.
 *
 * The app pages are tools, not documents — the Build page is sized to the
 * viewport and a footer under it would either be unreachable or would push
 * the message box off screen. Somewhere to look at the end of a page is a
 * property of pages you scroll to the bottom of.
 */
export function Footer() {
  const path = usePathname();
  if (path !== "/") return null;

  return (
    <footer className="border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-12">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-2.5">
              <Logo size={18} />
              <span className="text-sm font-semibold tracking-tight">Stratus</span>
            </div>
            <p className="mt-3 text-[13px] leading-relaxed text-fg-muted">
              Infrastructure from a sentence, with the change and the cost shown before
              anything happens.
            </p>
          </div>

          <div className="flex gap-12 sm:gap-16">
            <FooterColumn title="Product">
              <FooterLink href="/build">Build</FooterLink>
              <FooterLink href="/account">Account</FooterLink>
              <FooterLink href="/history">History</FooterLink>
              <FooterLink href="/drift">Changes</FooterLink>
            </FooterColumn>

            <FooterColumn title="Project">
              <FooterLink href="https://github.com/roshna21/stratus" external>
                Source
              </FooterLink>
              <FooterLink
                href="https://webr0bhza.z13.web.core.windows.net/"
                external
              >
                A page it built
              </FooterLink>
            </FooterColumn>
          </div>
        </div>

        <div className="rule my-8" />

        <div className="flex flex-col gap-2 text-[12px] text-fg-faint sm:flex-row sm:items-center sm:justify-between">
          <p>Built by Roshna Sai. MIT licensed.</p>
          <p>
            A demonstration. It has no authentication — do not expose it to the internet
            as it is.
          </p>
        </div>
      </div>
    </footer>
  );
}

function FooterColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.13em] text-fg-faint">
        {title}
      </div>
      <ul className="space-y-2.5">{children}</ul>
    </div>
  );
}

function FooterLink({
  href,
  children,
  external,
}: {
  href: string;
  children: React.ReactNode;
  external?: boolean;
}) {
  const className = "text-[13px] text-fg-muted transition-colors hover:text-fg";
  return (
    <li>
      {external ? (
        <a href={href} target="_blank" rel="noreferrer" className={className}>
          {children}
        </a>
      ) : (
        <Link href={href} className={className}>
          {children}
        </Link>
      )}
    </li>
  );
}
