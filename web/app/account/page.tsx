"use client";

import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { Button, Card, ErrorNote, Label, Spinner } from "@/components/ui";

export default function AccountPage() {
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .account()
      .then((r) => setSummary(r.summary))
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="mx-auto max-w-3xl px-5 py-10">
      <div className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Your account</h1>
          <p className="mt-1 text-sm text-dim">
            Everything in your Azure subscription, in plain words.
          </p>
        </div>
        <Button onClick={load} disabled={loading}>
          Refresh
        </Button>
      </div>

      {loading && <Spinner label="Reading your account…" />}
      {error && !loading && <ErrorNote>{error}</ErrorNote>}
      {summary && !loading && !error && (
        <Card>
          <Label>What you have</Label>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
            {summary}
          </pre>
        </Card>
      )}
    </div>
  );
}
