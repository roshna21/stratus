/**
 * Everything the page knows about the server.
 *
 * Kept in one file so the shapes the API returns are written down once. The
 * base URL is configurable because the front end runs on its own port in
 * development and is served by the same process in production.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type PlanResponse = {
  id?: string;
  summary: string;
  assumptions?: string[];
  question?: string;
  destructive?: boolean;
  monthly_cost?: number;
  repairs?: number;
  nothing_to_do?: boolean;
};

export type JobSnapshot = {
  id: string;
  kind: string;
  status: "running" | "done" | "failed";
  log: string[];
  log_length: number;
  result: { applied: boolean; summary?: string; change_id?: string } | null;
  error: string | null;
};

export type HistoryEntry = {
  id: string;
  at: string;
  request: string;
  summary: string;
  created: number;
  changed: number;
  destroyed: number;
};

export class ApiError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // A failed fetch says "Failed to fetch" and nothing else, which sends
    // people hunting through their own code. The server being down is by far
    // the likeliest cause, so say that.
    throw new ApiError(
      `Can't reach the Stratus server at ${BASE}. Is it running?\n\n` +
        `    uvicorn stratus.web:app --port 8000`,
    );
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(body?.detail ?? `The server returned ${response.status}.`);
  }
  return body as T;
}

export const api = {
  health: () => call<{ status: string }>("/api/health"),

  account: () => call<{ summary: string; count: number }>("/api/account"),

  plan: (request: string, workspace = "default") =>
    call<PlanResponse>("/api/plan", {
      method: "POST",
      body: JSON.stringify({ request, workspace }),
    }),

  apply: (id: string, answer: string) =>
    call<{ applied: boolean | null; job?: string; message?: string }>("/api/apply", {
      method: "POST",
      body: JSON.stringify({ id, answer }),
    }),

  job: (id: string, since = 0) => call<JobSnapshot>(`/api/jobs/${id}?since=${since}`),

  history: (workspace = "default") =>
    call<{ entries: HistoryEntry[] }>(`/api/history?workspace=${workspace}`),

  drift: (workspace = "default") =>
    call<{ has_drift: boolean; description: string }>(`/api/drift?workspace=${workspace}`),
};

/**
 * Watch a job to completion, reporting each new batch of output.
 *
 * Only lines not already seen are requested, so a build producing hundreds
 * of them does not resend the whole log every second.
 */
export async function followJob(
  id: string,
  onLines: (lines: string[]) => void,
  intervalMs = 1200,
): Promise<JobSnapshot> {
  let seen = 0;

  for (;;) {
    const snapshot = await api.job(id, seen);
    if (snapshot.log.length) {
      onLines(snapshot.log);
      seen = snapshot.log_length;
    }
    if (snapshot.status !== "running") return snapshot;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
