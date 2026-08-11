"use client";

import { useEffect, useState } from "react";

const KEY = "stratus.workspace";

/**
 * Which set of infrastructure every page is looking at.
 *
 * Shared and remembered, because it was not: the build page had a selector
 * and the others were hardcoded to "default", so building in one workspace
 * and then opening History showed an empty list — which reads as "the build
 * was not recorded" rather than "you are looking somewhere else".
 *
 * Kept in localStorage rather than a React context so it survives a reload.
 * A workspace is a thing you work in for a while, not for one page view.
 */
export function useWorkspace(): [string, (next: string) => void] {
  // Starts at the default and is corrected after mount. Reading localStorage
  // during render would make the server-rendered markup disagree with the
  // first client render, which React reports as a hydration error.
  const [workspace, setLocal] = useState("default");

  useEffect(() => {
    const stored = window.localStorage.getItem(KEY);
    if (stored) setLocal(stored);

    // Two tabs open on different workspaces, each thinking it knows the
    // answer, is worse than either being wrong.
    const sync = (e: StorageEvent) => {
      if (e.key === KEY && e.newValue) setLocal(e.newValue);
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const set = (next: string) => {
    const cleaned = next.trim() || "default";
    setLocal(cleaned);
    window.localStorage.setItem(KEY, cleaned);
  };

  return [workspace, set];
}

export function WorkspaceField({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <span className="flex items-center gap-2 text-xs text-dim">
      <label htmlFor="ws">Workspace</label>
      <input
        id="ws"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-32 rounded-md border border-line bg-panel px-2 py-1 font-mono text-[11px] text-text outline-none focus:border-accent disabled:opacity-50"
      />
    </span>
  );
}
