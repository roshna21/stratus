/**
 * The small pieces every page uses.
 *
 * Together in one file because they are each a handful of lines, and a
 * directory of ten-line files is harder to keep consistent than one you can
 * read top to bottom.
 */

import type { ReactNode } from "react";

/* -------------------------------------------------------------------------
 * Surfaces
 * ---------------------------------------------------------------------- */

export function Card({
  children,
  className = "",
  tone = "normal",
  interactive = false,
}: {
  children: ReactNode;
  className?: string;
  tone?: "normal" | "danger" | "warn" | "accent";
  interactive?: boolean;
}) {
  const border = {
    normal: "border-hairline",
    danger: "border-danger/40",
    warn: "border-warn/35",
    accent: "border-accent/40",
  }[tone];

  // A coloured card gets a wash of its own colour as well as a border.
  // Border alone is too thin a signal for "this one will destroy something".
  const wash = {
    normal: "",
    danger: "bg-danger/[0.035]",
    warn: "bg-warn/[0.03]",
    accent: "bg-accent/[0.035]",
  }[tone];

  return (
    <div
      className={`rounded-xl border ${border} bg-surface ${wash} ${
        interactive
          ? "transition-colors duration-200 hover:border-edge hover:bg-raised"
          : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function Label({ children }: { children: ReactNode }) {
  return (
    <div className="mb-3 font-mono text-[10.5px] font-medium uppercase tracking-[0.13em] text-fg-faint">
      {children}
    </div>
  );
}

/**
 * The top of an app page: what this is, and the controls that act on it.
 *
 * Shared rather than repeated three times, because the moment it is repeated
 * the three pages start disagreeing about heading size and spacing.
 */
export function PageHeader({
  title,
  children,
  actions,
}: {
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="max-w-xl">
        <h1 className="text-heading font-semibold">{title}</h1>
        {children && (
          <p className="mt-2 text-[14.5px] leading-relaxed text-fg-muted">{children}</p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-3">{actions}</div>
      )}
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  children,
}: {
  eyebrow?: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="max-w-2xl">
      {eyebrow && (
        <div className="mb-3 font-mono text-[11px] uppercase tracking-[0.15em] text-accent">
          {eyebrow}
        </div>
      )}
      <h2 className="text-title font-semibold text-balance">{title}</h2>
      {children && (
        <p className="mt-4 text-[15px] leading-relaxed text-fg-muted text-pretty">
          {children}
        </p>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------
 * Controls
 * ---------------------------------------------------------------------- */

/**
 * Shared so a Next `<Link>` can be dressed as a button without a second
 * implementation. Two sets of button styles is how a product ends up with
 * two slightly different buttons.
 */
export function buttonClass(
  variant: "primary" | "normal" | "ghost" | "danger" = "normal",
  size: "sm" | "md" | "lg" = "md",
) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg border font-medium " +
    "transition-all duration-200 disabled:pointer-events-none disabled:opacity-40";

  const sizing = {
    sm: "px-3 py-1.5 text-[13px]",
    md: "px-4 py-2 text-sm",
    lg: "px-5 py-2.5 text-[15px]",
  }[size];

  const look = {
    // The glow is what separates a primary action from a coloured rectangle.
    // The gradient stays inside the light half of the lilac ramp: running it
    // down into the deep violet would look richer but drops the dark label
    // below a readable contrast against the far end.
    primary:
      "border-transparent bg-gradient-to-br from-accent-bright to-accent text-canvas " +
      "shadow-[0_1px_0_0_rgba(255,255,255,0.25)_inset,0_8px_24px_-8px_var(--color-violet)] " +
      "hover:from-white hover:to-accent-bright hover:shadow-[0_1px_0_0_rgba(255,255,255,0.3)_inset,0_10px_30px_-8px_var(--color-accent)]",
    normal: "border-edge bg-raised text-fg hover:border-accent/50 hover:bg-overlay",
    ghost: "border-transparent text-fg-muted hover:bg-raised hover:text-fg",
    danger: "border-danger/50 text-danger hover:border-danger hover:bg-danger/10",
  }[variant];

  return `${base} ${sizing} ${look}`;
}

export function Button({
  children,
  onClick,
  variant = "normal",
  size = "md",
  disabled,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "normal" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${buttonClass(variant, size)} ${className}`}
    >
      {children}
    </button>
  );
}

/* -------------------------------------------------------------------------
 * Signals
 * ---------------------------------------------------------------------- */

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "danger" | "accent";
}) {
  const look = {
    neutral: "border-hairline bg-raised text-fg-muted",
    ok: "border-ok/30 bg-ok/10 text-ok",
    warn: "border-warn/30 bg-warn/10 text-warn",
    danger: "border-danger/30 bg-danger/10 text-danger",
    accent: "border-accent/30 bg-accent/10 text-accent",
  }[tone];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] tracking-wide ${look}`}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = "neutral" }: { tone?: "neutral" | "ok" | "warn" | "danger" }) {
  const colour = {
    neutral: "bg-fg-faint text-fg-faint",
    ok: "bg-ok text-ok",
    warn: "bg-warn text-warn",
    danger: "bg-danger text-danger",
  }[tone];
  // `halo` reads `currentColor`, so the text colour is doing real work here.
  return (
    <span className={`relative inline-block h-2 w-2 shrink-0 rounded-full ${colour}`}>
      {tone !== "neutral" && <span className="halo absolute inset-0" />}
    </span>
  );
}

/**
 * A single figure with a caption under it.
 *
 * Monospaced and large, because these are the numbers someone came to the
 * page for — how much, how many, how recently.
 */
export function Stat({
  value,
  caption,
  tone = "normal",
}: {
  value: ReactNode;
  caption: string;
  tone?: "normal" | "ok" | "warn" | "danger" | "accent";
}) {
  const colour = {
    normal: "text-fg",
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
    accent: "text-accent",
  }[tone];

  return (
    <div>
      <div className={`font-mono text-2xl leading-none ${colour}`}>{value}</div>
      <div className="mt-2 text-[13px] text-fg-muted">{caption}</div>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2.5 text-sm text-fg-muted">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-edge border-t-accent" />
      {label}
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function Empty({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-hairline px-6 py-16 text-center">
      <p className="text-sm text-fg">{title}</p>
      {hint && (
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-fg-muted">{hint}</p>
      )}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <Card tone="danger" className="p-5">
      <div className="flex gap-3">
        <span
          aria-hidden
          className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-danger/15 font-mono text-[11px] text-danger"
        >
          !
        </span>
        <pre className="min-w-0 whitespace-pre-wrap break-words font-sans text-sm leading-relaxed">
          {children}
        </pre>
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
    <div className="max-h-64 overflow-y-auto rounded-lg border border-hairline bg-canvas p-3.5">
      {lines.map((line, i) => (
        <div
          key={i}
          className="font-mono text-[11.5px] leading-[1.7] break-all text-fg-faint"
        >
          {line}
        </div>
      ))}
    </div>
  );
}
