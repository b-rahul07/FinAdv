/**
 * Client-Side Session Cache (localStorage)
 * ===========================================
 * Provides fast, instant-load local caching of chat threads in the browser's
 * localStorage so the UI loads immediately without waiting for network roundtrips.
 * 
 * Features:
 *   - list(): Lists all cached sessions sorted by last updated timestamp.
 *   - get(id): Fetches a specific cached session by ID.
 *   - upsert(id, thread, stage): Automatically saves thread messages and extracts
 *     a human-readable label from the user's first question.
 *   - remove(id): Purges a deleted session from local cache.
 */

import type { CachedSession, SessionSummary, ThreadItem } from "./types";

// Local storage key for version 1 of the session store
const KEY = "advisor.sessions.v1";

/**
 * Reads all cached sessions from window.localStorage.
 */
function readAll(): Record<string, CachedSession> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.localStorage.getItem(KEY) ?? "{}") as Record<string, CachedSession>;
  } catch {
    return {};
  }
}

/**
 * Writes the entire session map into window.localStorage.
 */
function writeAll(data: Record<string, CachedSession>) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(data));
}

/**
 * Session storage API for client-side state management.
 */
export const sessionStore = {
  // Returns summary metadata for all cached sessions
  list(): SessionSummary[] {
    return Object.values(readAll())
      .map((s) => ({ session_id: s.session_id, label: s.label, updated_at: s.updated_at }))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  },

  // Retrieves a single session by its UUID
  get(id: string): CachedSession | undefined {
    return readAll()[id];
  },

  // Saves a complete CachedSession object directly
  save(session: CachedSession) {
    const all = readAll();
    all[session.session_id] = session;
    writeAll(all);
  },

  // Updates or inserts a session with latest thread items and progression stage
  upsert(id: string, thread: ThreadItem[], stage: CachedSession["stage"]) {
    const all = readAll();
    const firstUser = thread.find((t) => t.kind === "text" && t.role === "user");
    const label =
      firstUser && firstUser.kind === "text"
        ? firstUser.content.slice(0, 48)
        : (all[id]?.label ?? "New session");
    all[id] = {
      session_id: id,
      label,
      updated_at: new Date().toISOString(),
      thread,
      stage,
    };
    writeAll(all);
  },

  // Removes a session from the local cache
  remove(id: string) {
    const all = readAll();
    delete all[id];
    writeAll(all);
  },
};

