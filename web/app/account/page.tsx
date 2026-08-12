"use client";

import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import {
  Button,
  Card,
  ErrorNote,
  Label,
  PageHeader,
  Skeleton,
  Stat,
} from "@/components/ui";

type Account = { summary: string; count: number };

export default function AccountPage() {
  const [data, setData] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  /**
   * Bumped by Refresh to run the effect again.
   *
   * The fetch lives in an effect and nothing is set synchronously inside it:
   * `loading` already starts true for the first load, and Refresh sets it
   * from its own click handler. Setting state in the body of an effect
   * schedules a second render before the first has painted, which React
   * flags as a cascading render.
   */
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // A reply that arrives after the component has gone, or after a newer
    // request was started, must not overwrite what is on screen.
    let cancelled = false;

    api
      .account()
      .then((r) => {
        if (cancelled) return;
        setData(r);
        setError(null);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const refresh = () => {
    setLoading(true);
    setError(null);
    setAttempt((n) => n + 1);
  };

  return (
    <div className="mx-auto max-w-3xl px-5 py-10">
      <PageHeader
        title="Your account"
        actions={
          <Button onClick={refresh} disabled={loading}>
            Refresh
          </Button>
        }
      >
        Everything in your Azure subscription, in plain words. Read live, every time —
        this is what Stratus looks at before it plans anything.
      </PageHeader>

      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-52 w-full" />
        </div>
      )}

      {error && !loading && <ErrorNote>{error}</ErrorNote>}

      {data && !loading && !error && (
        <div className="space-y-4">
          <Card className="p-5">
            <Stat
              value={data.count}
              caption={
                data.count === 1
                  ? "thing in your subscription"
                  : "things in your subscription"
              }
              tone="accent"
            />
          </Card>

          <Card className="p-5">
            <Label>What you have</Label>
            <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-fg-muted">
              {data.summary}
            </pre>
          </Card>
        </div>
      )}
    </div>
  );
}
