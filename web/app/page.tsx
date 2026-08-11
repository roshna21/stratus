"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, api, followJob, type PlanResponse } from "@/lib/api";
import { Button, Card, ErrorNote, Label, LogView, Spinner } from "@/components/ui";

const SUGGESTIONS = [
  "a private place to keep some files",
  "somewhere to store photos for a small project",
  "a place to keep database backups",
];

type Message =
  | { kind: "you"; text: string }
  | { kind: "stratus"; text: string }
  | { kind: "error"; text: string }
  | { kind: "plan"; plan: PlanResponse; decided?: "built" | "cancelled" }
  | { kind: "building"; lines: string[]; done?: string };

export default function BuildPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  // One workspace holds one set of infrastructure, so asking for something
  // new in a workspace that already has something replaces it. Without a way
  // to choose, every request from here would target "default" and quietly
  // propose destroying whatever was built before.
  const [workspace, setWorkspace] = useState("default");
  const [busy, setBusy] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  const push = (m: Message) => setMessages((prev) => [...prev, m]);

  async function ask(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    push({ kind: "you", text });
    setBusy("Working out what to build");

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

  async function decide(index: number, plan: PlanResponse, answer: string | null) {
    // Mark the plan as settled so its buttons cannot be pressed twice — the
    // approval is single-use on the server, and a second press would only
    // produce a confusing "no longer available".
    setMessages((prev) =>
      prev.map((m, i) =>
        i === index && m.kind === "plan"
          ? { ...m, decided: answer ? "built" : "cancelled" }
          : m,
      ),
    );

    if (!answer) {
      push({ kind: "stratus", text: "Cancelled. Nothing was changed." });
      return;
    }

    setBusy("Building");
    const buildIndex = messages.length + 1;
    push({ kind: "building", lines: [] });

    try {
      const started = await api.apply(plan.id!, answer);
      if (!started.job) {
        push({ kind: "stratus", text: started.message ?? "Cancelled." });
        return;
      }

      const finished = await followJob(started.job, (lines) => {
        setMessages((prev) =>
          prev.map((m, i) =>
            i === buildIndex && m.kind === "building"
              ? { ...m, lines: [...m.lines, ...lines] }
              : m,
          ),
        );
      });

      if (finished.status === "failed") {
        push({ kind: "error", text: finished.error ?? "The build failed." });
      } else {
        setMessages((prev) =>
          prev.map((m, i) =>
            i === buildIndex && m.kind === "building"
              ? { ...m, done: finished.result?.summary ?? "Done." }
              : m,
          ),
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
          {messages.map((m, i) => (
            <div key={i} className="rise">
              {m.kind === "you" && <You text={m.text} />}
              {m.kind === "stratus" && <Says>{m.text}</Says>}
              {m.kind === "error" && <ErrorNote>{m.text}</ErrorNote>}
              {m.kind === "plan" && (
                <PlanCard
                  plan={m.plan}
                  decided={m.decided}
                  onDecide={(answer) => decide(i, m.plan, answer)}
                />
              )}
              {m.kind === "building" && <Building lines={m.lines} done={m.done} />}
            </div>
          ))}
        </div>

        {busy && (
          <div className="mt-5">
            <Spinner label={`${busy}…`} />
          </div>
        )}
        <div ref={bottom} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="border-t border-line py-4"
      >
        <div className="flex gap-2.5">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!!busy}
            placeholder="What do you need?"
            className="flex-1 rounded-lg border border-line bg-panel px-4 py-3 text-sm outline-none transition-colors placeholder:text-dim focus:border-accent disabled:opacity-50"
          />
          <Button type="submit" variant="primary" disabled={!!busy || !input.trim()}>
            Send
          </Button>
        </div>
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-dim">
          <span>
            Nothing is created until you approve it. Real resources, in your real Azure
            subscription.
          </span>
          <span className="ml-auto flex items-center gap-2">
            <label htmlFor="ws">Workspace</label>
            <input
              id="ws"
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value.trim() || "default")}
              disabled={!!busy}
              className="w-32 rounded-md border border-line bg-panel px-2 py-1 font-mono text-[11px] text-text outline-none focus:border-accent disabled:opacity-50"
            />
          </span>
        </div>
      </form>
    </div>
  );
}

function Welcome({ onPick, busy }: { onPick: (t: string) => void; busy: boolean }) {
  return (
    <div className="mb-8">
      <h1 className="text-2xl font-semibold tracking-tight">
        What would you like to build?
      </h1>
      <p className="mt-2 max-w-lg text-sm leading-relaxed text-dim">
        Describe it in ordinary words. You will see exactly what would change and what it
        would cost before anything happens.
      </p>
      <div className="mt-5 flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            disabled={busy}
            onClick={() => onPick(s)}
            className="rounded-full border border-line bg-panel px-3.5 py-1.5 text-[13px] text-dim transition-colors hover:border-accent/50 hover:text-text disabled:opacity-40"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function You({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-xl rounded-br-sm bg-accent-dim/30 px-4 py-2.5 text-sm">
        {text}
      </div>
    </div>
  );
}

function Says({ children }: { children: React.ReactNode }) {
  return (
    <Card>
      <div className="whitespace-pre-wrap text-sm leading-relaxed">{children}</div>
    </Card>
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
    <Card tone={destructive ? "danger" : "normal"}>
      {destructive && (
        <div className="mb-4 flex items-center gap-2 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
          <strong>This will destroy things.</strong> Read it carefully.
        </div>
      )}

      <div className="text-sm leading-relaxed">{plan.summary}</div>

      {!!plan.assumptions?.length && (
        <div className="mt-4">
          <Label>I assumed</Label>
          <ul className="space-y-1">
            {plan.assumptions.map((a, i) => (
              <li key={i} className="text-sm text-dim">
                • {a}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4">
        <Label>What would change</Label>
        {/* The server's own wording, unaltered. The command line and the
            browser must never describe the same plan differently — two
            descriptions of one change is one of them being wrong. */}
        <pre className="whitespace-pre-wrap break-words rounded-lg border border-line bg-ink p-4 font-sans text-[13px] leading-relaxed">
          {plan.question}
        </pre>
      </div>

      {decided ? (
        <p className="mt-4 text-sm text-dim">
          {decided === "built" ? "Approved." : "Cancelled. Nothing was changed."}
        </p>
      ) : (
        <div className="mt-5">
          {destructive ? (
            <div className="space-y-3">
              <p className="text-sm text-dim">
                To go ahead, type <code className="text-danger">DELETE</code> exactly.
              </p>
              <div className="flex gap-2.5">
                <input
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  placeholder="DELETE"
                  className="w-40 rounded-lg border border-line bg-ink px-3 py-2 font-mono text-sm outline-none focus:border-danger"
                />
                <Button
                  variant="danger"
                  disabled={typed !== "DELETE"}
                  onClick={() => onDecide("DELETE")}
                >
                  Destroy and build
                </Button>
                <Button onClick={() => onDecide(null)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2.5">
              <Button variant="primary" onClick={() => onDecide("yes")}>
                Build it
              </Button>
              <Button onClick={() => onDecide(null)}>Cancel</Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function Building({ lines, done }: { lines: string[]; done?: string }) {
  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        {done ? (
          <span className="text-sm text-ok">Done</span>
        ) : (
          <Spinner label="Building — this takes a couple of minutes" />
        )}
      </div>
      <LogView lines={lines} />
      {done && <p className="mt-4 text-sm leading-relaxed">{done}</p>}
    </Card>
  );
}
