/**
 * Main Chat & Advising Screen Route
 * ==================================
 * File: src/routes/chat.$sessionId.tsx
 * 
 * This is the primary interactive hub of the Ledgerly application.
 * It manages the complete end-to-end user lifecycle across 3 distinct phases:
 * 
 *   Phase 1: Elicitation ("elicitation")
 *     - The assistant asks 7 structured financial profiling questions.
 *     - Provides click-to-answer option chips or text input.
 *     - Shows a progress bar (Question X of 7).
 * 
 *   Phase 2: Human Confirmation ("confirm")
 *     - Once all 7 questions are answered, renders an interactive `ProfileCard`.
 *     - Allows the user to inspect and edit any inferred profile values.
 * 
 *   Phase 3: Recommendation & Evidence ("recommendation")
 *     - Runs the multi-agent RAG pipeline via `/recommend`.
 *     - Shows an animated 4-stage progress checklist (`StagedProgress`).
 *     - Renders the final recommendation with clickable citations (`RecommendationCard`).
 *     - Dynamically drives the live `EvidencePanel` showing source chunks, FinBERT sentiment, and SEBI rules.
 */

import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, PanelLeft, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { DemoSettings } from "@/components/advisor/DemoSettings";
import { EvidencePanel } from "@/components/advisor/EvidencePanel";
import { HistorySidebar } from "@/components/advisor/HistorySidebar";
import { ProfileCard } from "@/components/advisor/ProfileCard";
import { RecommendationCard } from "@/components/advisor/RecommendationCard";
import { StagedProgress } from "@/components/advisor/StagedProgress";
import { advisorApi } from "@/lib/advisor/api";
import { sessionStore } from "@/lib/advisor/store";
import type {
  RecommendationResponse,
  SessionSummary,
  ThreadItem,
  UserProfile,
} from "@/lib/advisor/types";

// TanStack Router route definition with SEO tags
export const Route = createFileRoute("/chat/$sessionId")({
  head: () => ({
    meta: [
      { title: "Session — Ledgerly" },
      {
        name: "description",
        content:
          "Answer the elicitation questions, confirm your profile, and read guidance alongside its evidence trail.",
      },
      { property: "og:title", content: "Session — Ledgerly" },
      {
        property: "og:description",
        content: "Auditable suitability guidance with a live evidence trail.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: ChatSession,
});

// Helper utilities to generate short unique IDs and ISO timestamps
const uid = () => Math.random().toString(36).slice(2, 10);
const now = () => new Date().toISOString();

function ChatSession() {
  // Extract sessionId parameter from the URL path (e.g. /chat/abc-123)
  const { sessionId } = Route.useParams();
  const navigate = useNavigate();

  // --- STATE MANAGEMENT ---
  // List of conversation items (questions, user answers, profile card, recommendation)
  const [thread, setThread] = useState<ThreadItem[]>([]);
  // Current stage of the advisor process
  const [stage, setStage] = useState<"elicitation" | "confirm" | "recommendation">(
    "elicitation",
  );
  // Text input box value
  const [input, setInput] = useState("");
  // Busy flags for async API operations
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [loadingFirstQuestion, setLoadingFirstQuestion] = useState(false);
  const [startingNew, setStartingNew] = useState(false);
  // List of all saved sessions for the sidebar
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  // Active recommendation data currently displayed in the right evidence panel
  const [activeEvidence, setActiveEvidence] = useState<RecommendationResponse | null>(null);
  // Active chunk ID highlighted when clicking a footnote [n] in the text
  const [activeChunk, setActiveChunk] = useState<string | null>(null);

  // DOM and synchronization refs
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const activeSessionRef = useRef(sessionId);
  // Ref to prevent duplicate API calls if the user double-clicks "Confirm Profile"
  const confirmingRef = useRef(false);

  // Keep activeSessionRef synced with current route parameter
  useEffect(() => {
    activeSessionRef.current = sessionId;
  }, [sessionId]);

  // Synchronizes the session list from localStorage
  const refreshSessions = useCallback(() => setSessions(sessionStore.list()), []);

  /**
   * SESSION INITIALIZATION EFFECT:
   * Runs whenever the sessionId changes.
   * Restores cached messages from localStorage if available;
   * Otherwise, calls the backend /chat/{sessionId}/start endpoint to fetch the first question.
   */
  useEffect(() => {
    // Reset state to avoid showing messages from the previous session
    setThread([]);
    setStage("elicitation");
    setBusy(false);
    setGenerating(false);
    setActiveEvidence(null);
    setActiveChunk(null);

    const cached = sessionStore.get(sessionId);
    if (cached && cached.thread.length > 0) {
      // Restore from local cache
      setThread(cached.thread);
      setStage(cached.stage);
      const lastRec = [...cached.thread]
        .reverse()
        .find((t) => t.kind === "recommendation");
      if (lastRec && lastRec.kind === "recommendation") setActiveEvidence(lastRec.data);
    } else {
      // New session: Request the first question from the backend
      setLoadingFirstQuestion(true);
      void advisorApi.start(sessionId).then((res) => {
        setLoadingFirstQuestion(false);
        if (res.type !== "question") return;
        setThread([
          {
            id: uid(),
            kind: "question",
            role: "assistant",
            content: res.question,
            options: res.options,
            index: res.index,
            total: res.total,
            timestamp: now(),
          },
        ]);
      }).catch(() => setLoadingFirstQuestion(false));
    }
    refreshSessions();
  }, [sessionId, refreshSessions]);

  /**
   * PERSISTENCE & AUTO-SCROLL EFFECT:
   * Whenever thread updates, automatically saves to localStorage and scrolls to bottom.
   */
  useEffect(() => {
    if (thread.length > 0) {
      sessionStore.upsert(sessionId, thread, stage);
      refreshSessions();
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread, stage, sessionId, refreshSessions]);

  /**
   * AUTO-FOCUS EFFECT:
   * Re-focuses the chat input field once generation completes.
   */
  useEffect(() => {
    if (!busy && !generating && !loadingFirstQuestion) inputRef.current?.focus();
  }, [busy, generating, loadingFirstQuestion, thread.length]);

  // Calculate progress percentage through the 7 questions
  const lastQuestion = [...thread].reverse().find((t) => t.kind === "question");
  const progress =
    lastQuestion && lastQuestion.kind === "question" && lastQuestion.total
      ? ((lastQuestion.index ?? 1) / lastQuestion.total) * 100
      : 0;

  /**
   * SUBMIT ANSWER HANDLER:
   * Handles user sending an answer (either typing text or clicking a quick option pill).
   */
  const submit = async (answer: string) => {
    if (!answer.trim() || busy || loadingFirstQuestion) return;
    setBusy(true);
    setInput("");

    // Append user's answer bubble immediately
    setThread((t) => [
      ...t,
      { id: uid(), kind: "text", role: "user", content: answer, timestamp: now() },
    ]);

    // Send answer to the backend elicitation agent
    const res = await advisorApi.sendMessage(sessionId, answer);
    if (res.type === "question") {
      // Case A: Next elicitation question returned
      setThread((t) => [
        ...t,
        {
          id: uid(),
          kind: "question",
          role: "assistant",
          content: res.question,
          options: res.options,
          index: res.index,
          total: res.total,
          timestamp: now(),
        },
      ]);
    } else {
      // Case B: All 7 questions complete! Render the ProfileCard review screen
      setStage("confirm");
      setThread((t) => [
        ...t,
        {
          id: uid(),
          kind: "profile",
          role: "assistant",
          profile: res.profile,
          confirmed: false,
          timestamp: now(),
        },
      ]);
    }
    setBusy(false);
  };

  /**
   * CONFIRM PROFILE HANDLER:
   * Triggered when the user clicks "Confirm and get my recommendation" on the ProfileCard.
   * Sends the confirmed profile to the backend, then triggers the multi-agent recommendation pipeline.
   */
  const confirmProfile = async (profile: UserProfile) => {
    // Debounce guard against rapid repeated clicks
    if (confirmingRef.current) return;
    confirmingRef.current = true;
    setConfirming(true);

    // Optimistically update the UI to show the profile as confirmed
    setThread((t) =>
      t.map((item) => (item.kind === "profile" ? { ...item, profile, confirmed: true } : item)),
    );
    setStage("recommendation");

    const sessionAtCallTime = sessionId;
    try {
      // 1. Send the confirmed profile to backend
      await advisorApi.confirm(sessionId, profile);

      if (activeSessionRef.current !== sessionAtCallTime) return;
      setGenerating(true);

      // 2. Trigger the full recommendation pipeline (RAG + FinBERT + Rules + Ollama)
      const rec = await advisorApi.recommend(sessionId);

      if (activeSessionRef.current !== sessionAtCallTime) return;

      // 3. Display recommendation card and populate evidence panel
      setGenerating(false);
      setActiveEvidence(rec);
      setThread((t) => [
        ...t,
        { id: uid(), kind: "recommendation", role: "assistant", data: rec, timestamp: now() },
      ]);
    } catch (err) {
      if (activeSessionRef.current !== sessionAtCallTime) return;
      setGenerating(false);
      const msg = err instanceof Error ? err.message : "An unknown error occurred.";
      setThread((t) => [
        ...t,
        { id: uid(), kind: "error", role: "assistant", content: msg, timestamp: now() },
      ]);
    } finally {
      confirmingRef.current = false;
      setConfirming(false);
    }
  };

  /**
   * NEW SESSION HANDLER:
   * Requests a new session UUID from the backend and navigates to it.
   */
  const newSession = async () => {
    if (startingNew) return;
    setStartingNew(true);
    try {
      const { session_id } = await advisorApi.createSession();
      void navigate({ to: "/chat/$sessionId", params: { sessionId: session_id } });
    } finally {
      setStartingNew(false);
    }
  };

  /**
   * DELETE SESSION HANDLER:
   * Purges a session from local storage and redirects home if it was active.
   */
  const deleteSession = (id: string) => {
    sessionStore.remove(id);
    refreshSessions();
    if (id === sessionId) void navigate({ to: "/" });
  };

  // Highlights a citation chunk in the EvidencePanel
  const cite = (chunkId: string) => setActiveChunk(`${chunkId}`);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* DESKTOP SIDEBAR: History navigation */}
      <div className="hidden w-[270px] shrink-0 border-r border-sidebar-border lg:block">
        <HistorySidebar
          sessions={sessions}
          activeId={sessionId}
          onNew={() => void newSession()}
          onDelete={deleteSession}
        />
      </div>

      {/* CENTER COLUMN: Main chat view */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Header */}
        <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
          <div className="flex items-center gap-2">
            {/* Mobile Sidebar Sheet Trigger */}
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="lg:hidden">
                  <PanelLeft className="size-4" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-[270px] p-0">
                <SheetTitle className="sr-only">Sessions</SheetTitle>
                <HistorySidebar
                  sessions={sessions}
                  activeId={sessionId}
                  onNew={() => void newSession()}
                  onDelete={deleteSession}
                />
              </SheetContent>
            </Sheet>
            <span className="text-sm font-medium">Suitability session</span>
          </div>

          <div className="flex items-center gap-2">
            {/* Mobile Evidence Panel Sheet Trigger */}
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2 xl:hidden">
                  <ShieldCheck className="size-4 text-evidence" />
                  Evidence
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-full p-0 sm:max-w-md">
                <SheetTitle className="sr-only">Evidence trail</SheetTitle>
                <EvidencePanel data={activeEvidence} activeChunkId={activeChunk} />
              </SheetContent>
            </Sheet>
            {/* Demo Settings Ablation Popover */}
            <DemoSettings />
          </div>
        </header>

        {/* Elicitation Progress Bar (Question X of 7) */}
        {stage === "elicitation" && lastQuestion?.kind === "question" && lastQuestion.total ? (
          <div className="border-b border-border px-5 py-3">
            <div className="mb-2 flex justify-between text-xs text-muted-foreground">
              <span>
                Question {lastQuestion.index} of {lastQuestion.total}
              </span>
              <span>Preference elicitation</span>
            </div>
            <Progress value={progress} className="h-1" />
          </div>
        ) : null}

        {/* Chat Stream (Scrollable messages) */}
        <ScrollArea className="flex-1">
          <div className="mx-auto max-w-2xl space-y-6 px-5 py-8">
            {thread.map((item) => {
              // Message Bubble: Text answer or question
              if (item.kind === "text" || item.kind === "question") {
                const isUser = item.role === "user";
                return (
                  <div
                    key={item.id}
                    className={isUser ? "flex justify-end" : "flex justify-start"}
                  >
                    <div className="max-w-[85%] space-y-3">
                      <div
                        className={
                          isUser
                            ? "rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-[0.95rem] leading-relaxed text-primary-foreground"
                            : "rounded-2xl rounded-bl-sm bg-surface px-4 py-2.5 text-[0.95rem] leading-relaxed"
                        }
                      >
                        {item.content}
                      </div>
                      {/* Clickable Quick Option Pills for the latest question */}
                      {item.kind === "question" &&
                      item.options &&
                      item.id === lastQuestion?.id &&
                      stage === "elicitation" ? (
                        <div className="flex flex-wrap gap-2">
                          {item.options.map((o) => (
                            <button
                              key={o}
                              type="button"
                              disabled={busy}
                              onClick={() => void submit(o)}
                              className="rounded-full border border-border bg-surface-2 px-4 py-1.5 text-sm transition-colors hover:border-primary hover:text-primary disabled:opacity-50"
                            >
                              {o}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              }

              // Profile Card: Inferred preferences review & edit
              if (item.kind === "profile") {
                return (
                  <ProfileCard
                    key={item.id}
                    profile={item.profile}
                    confirmed={item.confirmed}
                    loading={confirming || generating}
                    onConfirm={(p) => void confirmProfile(p)}
                  />
                );
              }

              // Error notification
              if (item.kind === "error") {
                return (
                  <div key={item.id} className="flex justify-start">
                    <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                      <strong>Error:</strong> {item.content}
                    </div>
                  </div>
                );
              }

              // Recommendation Card: Final advice with interactive citations
              return (
                <div key={item.id} className="space-y-2">
                  <RecommendationCard
                    data={item.data}
                    onCite={(id) => {
                      setActiveEvidence(item.data);
                      cite(id);
                    }}
                  />
                </div>
              );
            })}

            {/* Staged progress checklist shown while LLM is generating */}
            {generating ? <StagedProgress /> : null}

            {/* Loading dots for initial question load */}
            {loadingFirstQuestion ? (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm bg-surface px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <span className="size-2 animate-bounce rounded-full bg-muted-foreground/50 [animation-delay:-0.3s]" />
                    <span className="size-2 animate-bounce rounded-full bg-muted-foreground/50 [animation-delay:-0.15s]" />
                    <span className="size-2 animate-bounce rounded-full bg-muted-foreground/50" />
                  </div>
                </div>
              </div>
            ) : null}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        {/* Bottom Message Input Bar (active only during elicitation) */}
        {stage === "elicitation" ? (
          <div className="border-t border-border px-5 py-4">
            <form
              className="mx-auto flex max-w-2xl items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void submit(input);
              }}
            >
              <Input
                ref={inputRef}
                value={input}
                disabled={busy || loadingFirstQuestion}
                placeholder={loadingFirstQuestion ? "Loading first question…" : "Type your answer…"}
                onChange={(e) => setInput(e.target.value)}
                className="h-11"
              />
              <Button type="submit" size="icon" className="size-11 shrink-0" disabled={busy || loadingFirstQuestion}>
                <ArrowUp className="size-4" />
              </Button>
            </form>
            <p className="mx-auto mt-2 max-w-2xl text-center text-xs text-muted-foreground">
              Educational suitability tool — not investment advice.
            </p>
          </div>
        ) : null}
      </div>

      {/* DESKTOP RIGHT COLUMN: Live Evidence Panel */}
      <div className="hidden w-[380px] shrink-0 xl:block">
        <EvidencePanel data={activeEvidence} activeChunkId={activeChunk} />
      </div>
    </div>
  );
}
