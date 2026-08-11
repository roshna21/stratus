"use client";

import { useEffect, useState } from "react";
import { ApiError, api, type HistoryEntry } from "@/lib/api";
import { Button, Card, Empty, ErrorNote, Spinner } from "@/components/ui";

export default function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [workspace] = useState("default");
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .history(workspace)
      .then((r) => setEntries(r.entries))
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="mx-auto max-w-3xl px-5 py-10">
      <div className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">History</h1>
          <p className="mt-1 text-sm text-dim">
            Every change that reached your account, newest first.
          </p>
        </div>
        <Button onClick={load} disabled={loading}>
          Refresh
        </Button>
      </div>

      {loading && <Spinner label="Loading…" />}
      {error && !loading && <ErrorNote>{error}</ErrorNote>}
      {entries && !loading && !error && entries.length === 0 && (
        <Empty
          title="Nothing has been built yet."
          hint="Anything you build will be recorded here, and you can go back to it."
        />
      )}

      <div className="space-y-3">
        {entries?.map((e) => (
          <Card key={e.id}>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-sm">{e.request}</p>
                <p className="mt-1.5 text-sm text-dim">{e.summary}</p>
              </div>
              <code className="shrink-0 rounded bg-panel-2 px-2 py-1 font-mono text-[11px] text-dim">
                {e.id}
              </code>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-dim">
              <time>{new Date(e.at).toLocaleString()}</time>
              {e.created > 0 && <span className="text-ok">+{e.created} created</span>}
              {e.changed > 0 && <span className="text-warn">~{e.changed} changed</span>}
              {e.destroyed > 0 && (
                <span className="text-danger">-{e.destroyed} removed</span>
              )}
            </div>
          </Card>
        ))}
      </div>

      {!!entries?.length && (
        <p className="mt-5 text-xs text-dim">
          To return to one of these, run{" "}
          <code className="rounded bg-panel-2 px-1.5 py-0.5 font-mono">
            stratus rollback &lt;id&gt;
          </code>
          . Rolling back from the browser is not built yet — it can destroy things, and
          the command line asks properly.
        </p>
      )}
    </div>
  );
}
