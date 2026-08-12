"use client";

import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import {
  Button,
  Card,
  Dot,
  Empty,
  ErrorNote,
  PageHeader,
  Spinner,
} from "@/components/ui";
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
      <PageHeader
        title="Changes made elsewhere"
        actions={
          <>
            <WorkspaceField value={workspace} onChange={setWorkspace} disabled={loading} />
            <Button variant="primary" onClick={check} disabled={loading}>
              {loading ? "Checking…" : "Check now"}
            </Button>
          </>
        }
      >
        Checks whether anything in your account has changed outside of Stratus — someone
        editing it in the Azure portal, or a script.
      </PageHeader>

      {!loading && !result && !error && (
        <Empty
          title="No check has been run yet."
          hint="This one compares your real account against the record, so it is only done when you ask. It takes about half a minute."
        />
      )}

      {loading && (
        <Card className="p-5">
          <Spinner label="Comparing your account against the record…" />
          <p className="mt-3 text-[13px] text-fg-faint">
            This reaches out to Azure, so it takes about half a minute.
          </p>
        </Card>
      )}

      {error && !loading && <ErrorNote>{error}</ErrorNote>}

      {result && !loading && (
        <Card tone={result.has_drift ? "warn" : "normal"} className="p-5">
          <div className="mb-4 flex items-center gap-2.5">
            <Dot tone={result.has_drift ? "warn" : "ok"} />
            <span
              className={`text-sm font-medium ${
                result.has_drift ? "text-warn" : "text-ok"
              }`}
            >
              {result.has_drift ? "Something has changed" : "Everything matches"}
            </span>
          </div>
          {/* The server's own wording, unaltered — the same sentences the
              command line prints for the same finding. */}
          <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-fg-muted">
            {result.description}
          </pre>
        </Card>
      )}
    </div>
  );
}
