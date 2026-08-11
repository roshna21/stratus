"use client";

import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { Button, Card, ErrorNote, Spinner } from "@/components/ui";
import { WorkspaceField, useWorkspace } from "@/lib/workspace";

export default function DriftPage() {
  const [result, setResult] = useState<{ has_drift: boolean; description: string } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [workspace, setWorkspace] = useWorkspace();
  const [loading, setLoading] = useState(false);

  // Not run on load, unlike the other pages: a drift check plans against the
  // real cloud and takes tens of seconds. Doing that because someone clicked
  // a tab would be rude.
  const check = () => {
    setLoading(true);
    setError(null);
    setResult(null);
    api
      .drift(workspace)
      .then(setResult)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  return (
    <div className="mx-auto max-w-3xl px-5 py-10">
      <h1 className="text-xl font-semibold tracking-tight">Changes made elsewhere</h1>
      <p className="mt-1 max-w-xl text-sm leading-relaxed text-dim">
        Checks whether anything in your account has changed outside of Stratus — someone
        editing it in the Azure portal, or a script.
      </p>

      <div className="mt-5 flex items-center gap-4">
        <WorkspaceField value={workspace} onChange={setWorkspace} disabled={loading} />
        <Button variant="primary" onClick={check} disabled={loading}>
          {loading ? "Checking…" : "Check now"}
        </Button>
        {!loading && !result && !error && (
          <span className="ml-3 text-xs text-dim">Takes about half a minute.</span>
        )}
      </div>

      <div className="mt-6">
        {loading && <Spinner label="Comparing your account against the record…" />}
        {error && <ErrorNote>{error}</ErrorNote>}
        {result && (
          <Card tone={result.has_drift ? "warn" : "normal"}>
            <div className="mb-3 flex items-center gap-2 text-sm">
              <span
                className={`h-2 w-2 rounded-full ${result.has_drift ? "bg-warn" : "bg-ok"}`}
              />
              {result.has_drift ? "Something has changed" : "Everything matches"}
            </div>
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
              {result.description}
            </pre>
          </Card>
        )}
      </div>
    </div>
  );
}
