/**
 * The small pieces every page uses.
 *
 * Together in one file because they are each a handful of lines, and a
 * directory of ten-line files is harder to keep consistent than one you can
 * read top to bottom.
 */

import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
  tone = "normal",
}: {
  children: ReactNode;
  className?: string;
  tone?: "normal" | "danger" | "warn";
}) {
  const border =
    tone === "danger"
      ? "border-danger/45"
      : tone === "warn"
        ? "border-warn/40"
        : "border-line";
  return (
    <div className={`rounded-xl border ${border} bg-panel p-5 ${className}`}>{children}</div>
  );
}

export function Label({ children }: { children: ReactNode }) {
  return (
    <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-dim">
      {children}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "normal",
  disabled,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "normal" | "primary" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const styles = {
    normal: "border-line bg-panel-2 hover:bg-line",
    primary: "border-accent bg-accent text-ink font-medium hover:brightness-110",
    danger: "border-danger/60 text-danger hover:bg-danger/10",
  }[variant];

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg border px-4 py-2 text-sm transition-all disabled:cursor-default disabled:opacity-40 ${styles}`}
    >
      {children}
    </button>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-dim">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-dim border-t-transparent" />
      {label}
    </span>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line px-6 py-14 text-center">
      <p className="text-sm text-text">{title}</p>
      {hint && <p className="mt-1.5 text-sm text-dim">{hint}</p>}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <Card tone="danger">
      <div className="flex gap-3">
        <span className="mt-0.5 shrink-0 text-danger">!</span>
        <pre className="whitespace-pre-wrap break-words font-sans text-sm">{children}</pre>
      </div>
    </Card>
  );
}

/**
 * Terraform's own output, shown as it arrives.
 *
 * Monospace and scrolling, because it is a log and pretending otherwise
 * helps nobody. It is the one place in the product where the machinery is
 * allowed to show — during a build, seeing something move is worth more than
 * being shielded from the vocabulary.
 */
export function LogView({ lines }: { lines: string[] }) {
  if (!lines.length) return null;
  return (
    <div className="max-h-64 overflow-y-auto rounded-lg border border-line bg-ink p-3">
      {lines.map((line, i) => (
        <div key={i} className="font-mono text-[11.5px] leading-relaxed text-dim">
          {line}
        </div>
      ))}
    </div>
  );
}
