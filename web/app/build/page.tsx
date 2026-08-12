"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, api, followJob, type PlanResponse } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  Dot,
  ErrorNote,
  Label,
  LogView,
  Spinner,
} from "@/components/ui";
import { WorkspaceField, useWorkspace } from "@/lib/workspace";

const SUGGESTIONS = [
  "a private place to keep some files",
  "somewhere to store photos for a small project",
  "a place to keep database backups",
];

type Body =
  | { kind: "you"; text: string }
  | { kind: "stratus"; text: string }
  | { kind: "error"; text: string }
  | { kind: "plan"; plan: PlanResponse; decided?: "built" | "cancelled" }
  | { kind: "building"; lines: string[]; done?: string };

// The body union is named separately because Omit<> over a union collapses
// to the keys they share, which is none of the interesting ones.
type Message = Body & { key: number };

/**
 * What is happening, and how long it is reasonable to wait for it.
 *
 * The second half is the point. Working out a plan takes thirty to ninety
 * seconds — it asks a model, reads the account, and runs a full plan against
 * Azure — and a bare spinner for that long reads as a hung page. Someone
 * watching one with no idea what it is waiting for concludes it is broken,
 * and they are being reasonable.
 */
type Busy = { label: string; hint: string };

/**
 * A counter rather than an array index.
 *
 * The build log is written from inside an await, and by then the array has
 * moved on. Addressing a message by the position it had when the request
 * started meant the log was appended to a message that did not exist — the
 * lines arrived from the server and were quietly dropped.
 */
let nextKey = 1;

export default function BuildPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  // Shared across pages, so History and Changes show the same workspace you
  // just built in.
  const [workspace, setWorkspace] = useWorkspace();
  const [busy, setBusy] = useState<Busy | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  const push = (m: Body) => {
    const keyed = { ...m, key: nextKey++ } as Message;
    setMessages((prev) => [...prev, keyed]);
    return keyed.key;
  };

  const update = (key: number, change: (m: Message) => Message) =>
    setMessages((prev) => prev.map((m) => (m.key === key ? change(m) : m)));

  async function ask(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    push({ kind: "you", text });
    setBusy({
      label: "Working out what to build",
      hint: "Reading your account, designing it, then checking exactly what would change. Usually under a minute.",
    });

    try {
      const plan = await api.plan(text, workspace);
      if (plan.nothing_to_do) {
        push({ kind: "stratus", text: plan.summary });
      } else {
        push({ kind: "plan", plan });
      }
    } catch (err) {
      push({ kind: "error", text: err instanceof ApiError ? err.message : String(err) });
    } finally {
      setBusy(null);
    }
  }

  async function decide(key: number, plan: PlanResponse, answer: string | null) {
    // Mark the plan as settled so its buttons cannot be pressed twice — the
    // approval is single-use on the server, and a second press would only
    // produce a confusing "no longer available".
    update(key, (m) =>
      m.kind === "plan" ? { ...m, decided: answer ? "built" : "cancelled" } : m,
    );

    // No message of its own. The card settles into "Cancelled. Nothing was
    // changed." in place, and adding a reply saying the same thing printed
    // the sentence twice in a row.
    if (!answer) return;

    setBusy({
      label: "Building",
      hint: "Progress appears below as it happens. This takes a couple of minutes.",
    });
    const buildKey = push({ kind: "building", lines: [] });

    try {
      const started = await api.apply(plan.id!, answer);
      if (!started.job) {
        push({ kind: "stratus", text: started.message ?? "Cancelled." });
        return;
      }

      const finished = await followJob(started.job, (lines) => {
        update(buildKey, (m) =>
          m.kind === "building" ? { ...m, lines: [...m.lines, ...lines] } : m,
        );
      });

      if (finished.status === "failed") {
        push({ kind: "error", text: finished.error ?? "The build failed." });
      } else {
        update(buildKey, (m) =>
          m.kind === "building"
            ? { ...m, done: finished.result?.summary ?? "Done." }
            : m,
        );
      }
    } catch (err) {
      push({ kind: "error", text: err instanceof ApiError ? err.message : String(err) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-3.5rem)] max-w-3xl flex-col px-5">
      <div className="flex-1 overflow-y-auto py-8">
        {messages.length === 0 && <Welcome onPick={ask} busy={!!busy} />}

        <div className="space-y-5">
          {messages.map((m) => (
            <div key={m.key} className="rise">
              {m.kind === "you" && <You text={m.text} />}
              {m.kind === "stratus" && <Says>{m.text}</Says>}
              {m.kind === "error" && <ErrorNote>{m.text}</ErrorNote>}
              {m.kind === "plan" && (
                <PlanCard
                  plan={m.plan}
                  decided={m.decided}
                  onDecide={(answer) => decide(m.key, m.plan, answer)}
                />
              )}
              {m.kind === "building" && <Building lines={m.lines} done={m.done} />}
            </div>
          ))}
        </div>

        {busy && (
          <div className="mt-5 rise">
            <Spinner label={`${busy.label}…`} />
            <p className="mt-2 max-w-md text-[12.5px] leading-relaxed text-fg-faint">
              {busy.hint}
            </p>
          </div>
        )}
        <div ref={bottom} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="border-t border-hairline py-4"
      >
        <div className="flex gap-2.5">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!!busy}
            placeholder="What do you need?"
            aria-label="Describe what you need"
            className="flex-1 rounded-lg border border-hairline bg-surface px-4 py-3 text-sm outline-none transition-colors placeholder:text-fg-faint focus:border-accent disabled:opacity-50"
          />
          <Button type="submit" variant="primary" disabled={!!busy || !input.trim()}>
            Send
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-[12px] text-fg-faint">
          <span>
            Nothing is created until you approve it. Real resources, in your real Azure
            subscription.
          </span>
          <span className="ml-auto">
            <WorkspaceField value={workspace} onChange={setWorkspace} disabled={!!busy} />
          </span>
        </div>
      </form>
    </div>
  );
}

function Welcome({ onPick, busy }: { onPick: (t: string) => void; busy: boolean }) {
  return (
    <div className="mb-10">
      <h1 className="text-heading font-semibold">What would you like to build?</h1>
      <p className="mt-2.5 max-w-lg text-[14.5px] leading-relaxed text-fg-muted">
        Describe it in ordinary words. You will see exactly what would change and what it
        would cost before anything happens.
      </p>
      <div className="mt-6">
        <Label>Try one of these</Label>
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              disabled={busy}
              onClick={() => onPick(s)}
              className="rounded-full border border-hairline bg-surface px-3.5 py-1.5 text-[13px] text-fg-muted transition-colors hover:border-accent/50 hover:bg-raised hover:text-fg disabled:opacity-40"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function You({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-xl rounded-br-sm border border-accent/25 bg-accent/10 px-4 py-2.5 text-sm">
        {text}
      </div>
    </div>
  );
}

function Says({ children }: { children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <div className="whitespace-pre-wrap text-sm leading-relaxed">{children}</div>
    </Card>
  );
}

/**
 * What a fixed monthly charge is, said honestly.
 *
 * Zero is a real answer here and means "nothing bills by the hour", but on
 * its own it reads as "this is free" — and most of what Stratus builds still
 * bills on usage. So zero is never rendered as a price. An absent figure is
 * unknown, and says so; a cost that cannot be worked out is never quietly
 * shown as nothing.
 */
function CostBadge({ monthly }: { monthly?: number }) {
  if (monthly === undefined || monthly === null) {
    return <Badge tone="warn">cost unknown</Badge>;
  }
  if (monthly === 0) {
    return <Badge tone="ok">no fixed monthly charge</Badge>;
  }
  return (
    <Badge tone="warn">
      ${monthly.toFixed(2)}/month, every month
    </Badge>
  );
}

function PlanCard({
  plan,
  decided,
  onDecide,
}: {
  plan: PlanResponse;
  decided?: "built" | "cancelled";
  onDecide: (answer: string | null) => void;
}) {
  const [typed, setTyped] = useState("");
  const destructive = !!plan.destructive;

  return (
    <Card tone={destructive ? "danger" : "normal"} className="p-5 sm:p-6">
      {destructive && (
        <div className="mb-5 flex flex-wrap items-center gap-2 rounded-lg bg-danger/10 px-3.5 py-2.5 text-[13.5px] text-danger">
          <strong className="font-semibold">This will destroy things.</strong>
          <span className="text-danger/85">Read it carefully.</span>
        </div>
      )}

      <div className="text-sm leading-relaxed">{plan.summary}</div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <CostBadge monthly={plan.monthly_cost} />
        {destructive && <Badge tone="danger">destroys existing things</Badge>}
        {/* How many times a generated configuration was rejected by the
            safety rules and sent back to be rewritten. Worth showing: it is
            the difference between a tool that refuses and one that warns. */}
        {!!plan.repairs && (
          <Badge tone="accent">
            {plan.repairs} unsafe {plan.repairs === 1 ? "version" : "versions"} rejected
          </Badge>
        )}
      </div>

      {!!plan.assumptions?.length && (
        <div className="mt-6">
          <Label>I assumed</Label>
          <ul className="space-y-2">
            {plan.assumptions.map((a, i) => (
              <li key={i} className="flex gap-2.5 text-[13.5px] text-fg-muted">
                <span className="text-fg-faint">—</span>
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6">
        <Label>What would change</Label>
        {/* The server's own wording, unaltered. The command line and the
            browser must never describe the same plan differently — two
            descriptions of one change is one of them being wrong. */}
        <pre className="whitespace-pre-wrap break-words rounded-lg border border-hairline bg-canvas p-4 font-sans text-[13px] leading-[1.75] text-fg-muted">
          {plan.question}
        </pre>
      </div>

      {decided ? (
        <p className="mt-5 flex items-center gap-2 text-sm text-fg-muted">
          <Dot tone={decided === "built" ? "ok" : "neutral"} />
          {decided === "built" ? "Approved." : "Cancelled. Nothing was changed."}
        </p>
      ) : (
        <div className="mt-6">
          {destructive ? (
            <div className="space-y-3">
              <p className="text-[13.5px] text-fg-muted">
                To go ahead, type{" "}
                <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[13px] text-danger">
                  DELETE
                </code>{" "}
                exactly.
              </p>
              <div className="flex flex-wrap gap-2.5">
                <input
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  placeholder="DELETE"
                  aria-label="Type DELETE to confirm"
                  className="w-36 rounded-lg border border-hairline bg-canvas px-3 py-2 font-mono text-sm outline-none transition-colors placeholder:text-fg-faint focus:border-danger"
                />
                <Button
                  variant="danger"
                  disabled={typed !== "DELETE"}
                  onClick={() => onDecide("DELETE")}
                >
                  Destroy and build
                </Button>
                <Button variant="ghost" onClick={() => onDecide(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2.5">
              <Button variant="primary" onClick={() => onDecide("yes")}>
                Build it
              </Button>
              <Button variant="ghost" onClick={() => onDecide(null)}>
                Cancel
              </Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function Building({ lines, done }: { lines: string[]; done?: string }) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center gap-2.5">
        {done ? (
          <>
            <Dot tone="ok" />
            <span className="text-sm text-ok">Done</span>
          </>
        ) : (
          <Spinner label="Building — this takes a couple of minutes" />
        )}
      </div>
      <LogView lines={lines} />
      {done && <p className="mt-4 text-sm leading-relaxed">{done}</p>}
    </Card>
  );
}
