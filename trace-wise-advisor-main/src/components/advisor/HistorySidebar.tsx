/**
 * History Sidebar Component
 * =========================
 * Displays the navigation sidebar on the left side of the screen.
 * It contains:
 *   - The Ledgerly brand title and logo.
 *   - The "+ New session" button to quickly start a new conversation.
 *   - A scrollable list of all saved prior chat sessions (loaded from browser storage).
 *   - Quick-delete buttons to purge specific sessions.
 */

import { Link } from "@tanstack/react-router";
import { MessageSquare, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { SessionSummary } from "@/lib/advisor/types";
import { cn } from "@/lib/utils";

// Properties passed into the HistorySidebar
type Props = {
  sessions: SessionSummary[];          // List of available sessions
  activeId?: string;                   // The currently active session UUID
  onNew: () => void;                   // Action callback to start a new chat
  onDelete: (id: string) => void;      // Action callback to delete a session
};

export function HistorySidebar({ sessions, activeId, onNew, onDelete }: Props) {
  return (
    <div className="flex h-full w-full flex-col bg-sidebar text-sidebar-foreground">
      {/* Brand Header */}
      <div className="px-5 py-5">
        <Link to="/" className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/15">
            <ShieldCheck className="size-4 text-primary" />
          </span>
          <span className="text-base font-semibold tracking-tight">Ledgerly</span>
        </Link>
      </div>

      {/* "New Session" Call-to-Action Button */}
      <div className="px-4">
        <Button className="w-full justify-start gap-2" onClick={onNew}>
          <Plus className="size-4" />
          New session
        </Button>
      </div>

      {/* Past Sessions List Title */}
      <p className="px-5 pb-2 pt-6 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Past sessions
      </p>

      {/* Scrollable list of past conversations */}
      <ScrollArea className="flex-1">
        <nav className="space-y-1 px-3 pb-4">
          {sessions.length === 0 ? (
            <p className="px-2 text-sm text-muted-foreground">No sessions yet.</p>
          ) : (
            sessions.map((s) => (
              <div
                key={s.session_id}
                className={cn(
                  "group flex items-center gap-2 rounded-lg px-2 transition-colors",
                  s.session_id === activeId
                    ? "bg-sidebar-accent"
                    : "hover:bg-sidebar-accent/60",
                )}
              >
                {/* Clicking a session link switches the URL and loads that session */}
                <Link
                  to="/chat/$sessionId"
                  params={{ sessionId: s.session_id }}
                  className="flex min-w-0 flex-1 items-center gap-2 py-2 text-sm"
                >
                  <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                  <span className="truncate">{s.label}</span>
                </Link>

                {/* Delete button: Visible on hover */}
                <button
                  type="button"
                  aria-label="Delete session"
                  onClick={() => onDelete(s.session_id)}
                  className="opacity-0 transition-opacity group-hover:opacity-100"
                >
                  <Trash2 className="size-3.5 text-muted-foreground hover:text-destructive" />
                </button>
              </div>
            ))
          )}
        </nav>
      </ScrollArea>

      {/* Educational Footer Disclaimer */}
      <p className="border-t border-sidebar-border px-5 py-4 text-xs leading-relaxed text-muted-foreground">
        Educational suitability tool. Not investment advice.
      </p>
    </div>
  );
}
