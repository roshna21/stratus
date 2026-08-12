"use client";

import { useEffect, useState } from "react";
import { ApiError, api, type HistoryEntry } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorNote,
  PageHeader,
  Skeleton,
  Stat,
} from "@/components/ui";
import { WorkspaceField, useWorkspace } from "@/lib/workspace";

/** What was asked for, and what came back. */
type Result = {
  /** Which request this answers. Empty before the first one returns. */
  token: string;
  entries?: HistoryEntry[];
  error?: string;
};

export default function HistoryPage() {
  const [workspace, setWorkspace] = useWorkspace();
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result>({ token: "" });

  /**
   * Loading is derived, not stored.
   *
   * Changing the workspace has to show a loading state immediately, and the
   * obvious way — setting a flag in the effect that reacts to the change —
   * is a synchronous setState inside an effect, which cascades a second
   * render. Comparing what is on screen against what is currently being
   * asked for gives the same answer during render, with no extra state and
   * no way for the two to disagree.
   */
  const token = `${workspace}#${attempt}`;
  const loading = result.token !== token;
  const { entries, error } = loading ? ({} as Result) : result;

  useEffect(() => {
    let cancelled = false;

    api
      .history(workspace)
      .then((r) => {
        if (!cancelled) setResult({ token, entries: r.entries });
      })
      .catch((e) => {
        if (!cancelled) {
          setResult({ token, error: e instanceof ApiError ? e.message : String(e) });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [workspace, token]);

  const totals = (entries ?? []).reduce(
    (acc, e) => ({
      created: acc.created + e.created,
      changed: acc.changed + e.changed,
      destroyed: acc.destroyed + e.destroyed,
    }),
    { created: 0, changed: 0, destroyed: 0 },
  );

  return (
    <div className="mx-auto max-w-3xl px-5 py-10">
      <PageHeader
        title="History"
        actions={
          <>
            <WorkspaceField value={workspace} onChange={setWorkspace} disabled={loading} />
            <Button onClick={() => setAttempt((n) => n + 1)} disabled={loading}>
              Refresh
            </Button>
          </>
        }
      >
        Every change that reached your account, newest first. Each one is stored with the
        configuration that produced it.
      </PageHeader>

      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      )}

      {error && <ErrorNote>{error}</ErrorNote>}

      {entries?.length === 0 && (
        <Empty
          title="Nothing has been built yet."
          hint={`Anything built in the “${workspace}” workspace is recorded here, and you can go back to it.`}
        />
      )}

      {!!entries?.length && (
        <>
          <Card className="mb-6 grid grid-cols-3 gap-4 p-5">
            <Stat
              value={totals.created}
              caption="created"
              tone={totals.created ? "ok" : "normal"}
            />
            <Stat
              value={totals.changed}
              caption="changed"
              tone={totals.changed ? "warn" : "normal"}
            />
            <Stat
              value={totals.destroyed}
              caption="removed"
              tone={totals.destroyed ? "danger" : "normal"}
            />
          </Card>

          {/* A timeline rather than a stack of cards: these are events in an
              order, and the order is the point — what was built on top of
              what. The rule is drawn behind the markers so it reads as one
              continuous line. */}
          <ol className="relative space-y-3 border-l border-hairline pl-6">
            {entries.map((e) => (
              <li key={e.id} className="relative">
                <span
                  aria-hidden
                  className="absolute -left-[1.6875rem] top-5 h-2.5 w-2.5 rounded-full border-2 border-canvas bg-edge"
                />
                <Card interactive className="p-5">
                  <div className="flex items-start justify-between gap-4">
                    <p className="min-w-0 text-sm leading-relaxed">{e.request}</p>
                    <code
                      title="Change id — pass this to stratus rollback"
                      className="shrink-0 rounded bg-raised px-2 py-1 font-mono text-[11px] text-fg-faint"
                    >
                      {e.id}
                    </code>
                  </div>

                  <p className="mt-2 text-[13.5px] leading-relaxed text-fg-muted">
                    {e.summary}
                  </p>

                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <time
                      dateTime={e.at}
                      title={new Date(e.at).toLocaleString()}
                      className="font-mono text-[11px] text-fg-faint"
                    >
                      {ago(e.at)}
                    </time>
                    {e.created > 0 && <Badge tone="ok">+{e.created} created</Badge>}
                    {e.changed > 0 && <Badge tone="warn">~{e.changed} changed</Badge>}
                    {e.destroyed > 0 && (
                      <Badge tone="danger">−{e.destroyed} removed</Badge>
                    )}
                  </div>
                </Card>
              </li>
            ))}
          </ol>

          <p className="mt-6 text-[12.5px] leading-relaxed text-fg-faint">
            To return to one of these, run{" "}
            <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[12px] text-fg-muted">
              stratus rollback &lt;id&gt;
            </code>
            . Rolling back from the browser is not built yet — it can destroy things, and
            the command line asks properly.
          </p>
        </>
      )}
    </div>
  );
}

/**
 * How long ago, in words.
 *
 * Only ever rendered on the client — this page fetches after mount — so
 * there is no server and client disagreeing about what "now" is.
 */
function ago(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;

  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return "just now";

  // Past a month, the date itself is more use than a count of weeks.
  if (seconds > 2_592_000) return new Date(iso).toLocaleDateString();

  // Largest unit that yields a whole number, so a two-hour-old change reads
  // as "2 hours ago" rather than "120 minutes ago".
  const units: [number, string][] = [
    [604800, "week"],
    [86400, "day"],
    [3600, "hour"],
    [60, "minute"],
  ];

  for (const [size, name] of units) {
    const value = Math.floor(seconds / size);
    if (value >= 1) return `${value} ${name}${value === 1 ? "" : "s"} ago`;
  }

  return "just now";
}
