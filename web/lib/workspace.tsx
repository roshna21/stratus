"use client";

import { useCallback, useSyncExternalStore } from "react";

const KEY = "stratus.workspace";
const DEFAULT = "default";

/**
 * A same-tab companion to the `storage` event.
 *
 * The browser fires `storage` in *other* tabs only — never in the one that
 * wrote the value. Without this, two components in the same page reading the
 * workspace would disagree the moment one of them changed it.
 */
const CHANGED = "stratus.workspace.changed";

function subscribe(notify: () => void) {
  window.addEventListener("storage", notify);
  window.addEventListener(CHANGED, notify);
  return () => {
    window.removeEventListener("storage", notify);
    window.removeEventListener(CHANGED, notify);
  };
}

function read(): string {
  return window.localStorage.getItem(KEY) ?? DEFAULT;
}

/**
 * What the server renders, before any browser storage exists.
 *
 * It must match the client's first render exactly or React reports a
 * hydration error, so this is the one answer that is always safe.
 */
function readOnServer(): string {
  return DEFAULT;
}

/**
 * Which set of infrastructure every page is looking at.
 *
 * Shared and remembered, because it was not: the build page had a selector
 * and the others were hardcoded to "default", so building in one workspace
 * and then opening History showed an empty list — which reads as "the build
 * was not recorded" rather than "you are looking somewhere else".
 *
 * Kept in localStorage rather than React state so it survives a reload. A
 * workspace is a thing you work in for a while, not for one page view.
 *
 * Subscribed to through useSyncExternalStore rather than copied into state
 * by an effect. localStorage *is* an external store, and the effect version
 * had to render the wrong value first and then correct it — a cascading
 * render that React now warns about, and a visible flicker if the stored
 * workspace was not the default one.
 */
export function useWorkspace(): [string, (next: string) => void] {
  const workspace = useSyncExternalStore(subscribe, read, readOnServer);

  const set = useCallback((next: string) => {
    // An empty box means the default, not a workspace with no name.
    const cleaned = next.trim() || DEFAULT;
    window.localStorage.setItem(KEY, cleaned);
    window.dispatchEvent(new Event(CHANGED));
  }, []);

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
    <span className="flex items-center gap-2 text-[12px] text-fg-faint">
      <label htmlFor="ws">Workspace</label>
      <input
        id="ws"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-32 rounded-md border border-hairline bg-surface px-2.5 py-1.5 font-mono text-[11px] text-fg outline-none transition-colors focus:border-accent disabled:opacity-50"
      />
    </span>
  );
}
