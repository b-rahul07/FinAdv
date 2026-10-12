/**
 * Landing Page Route (Home Screen)
 * ================================
 * This is the first screen the user sees when opening the web application.
 * It introduces the AI Financial Advisor ("Ledgerly"), explains how the 3-step
 * suitability process works (Questions -> Profile Review -> Auditable Recommendation),
 * and lets the user start a new session or resume an existing one.
 */

import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowRight, FileSearch, ListChecks, ShieldCheck, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { advisorApi } from "@/lib/advisor/api";
import { sessionStore } from "@/lib/advisor/store";
import type { SessionSummary } from "@/lib/advisor/types";

// TanStack Router definition for the root path "/"
export const Route = createFileRoute("/")({
  // SEO metadata tags for search engines and browser tab titles
  head: () => ({
    meta: [
      { title: "Ledgerly — Auditable AI Financial Guidance" },
      {
        name: "description",
        content:
          "An educational suitability tool that traces every piece of guidance back to the documents, sentiment signals and rules behind it.",
      },
      { property: "og:title", content: "Ledgerly — Auditable AI Financial Guidance" },
      {
        property: "og:description",
        content:
          "Answer seven questions, review what we understood, and get guidance with a visible evidence trail.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Landing,
});

/**
 * Main Landing Component:
 * Displays the hero headline, call-to-action buttons, 3-step guide, and SEBI compliance disclaimer.
 */
function Landing() {
  const navigate = useNavigate();

  // Local state to store past user sessions from browser storage
  const [sessions, setSessions] = useState<SessionSummary[]>([]);

  // Loading state to disable the button while communicating with the backend
  const [starting, setStarting] = useState(false);

  // Load any previously saved sessions when the page mounts
  useEffect(() => {
    setSessions(sessionStore.list());
  }, []);

  /**
   * Starts a brand new advising session:
   * 1. Calls the backend API to generate a new unique session UUID.
   * 2. Initializes the session state in localStorage.
   * 3. Navigates the browser to the chat room for that session.
   */
  const start = async () => {
    setStarting(true);
    try {
      const { session_id } = await advisorApi.createSession();
      sessionStore.upsert(session_id, [], "elicitation");
      void navigate({ to: "/chat/$sessionId", params: { sessionId: session_id } });
    } finally {
      setStarting(false);
    }
  };

  // Find the most recent session (if any exists) so the user can quickly resume
  const latest = sessions[0];

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-20">
      {/* Brand Icon Badge */}
      <span className="flex size-11 items-center justify-center rounded-xl bg-primary/15">
        <ShieldCheck className="size-5 text-primary" />
      </span>

      {/* Hero Headline & Description */}
      <h1 className="mt-8 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
        Financial guidance you can <span className="text-primary">trace</span>.
      </h1>
      <p className="mt-4 max-w-xl text-lg leading-relaxed text-muted-foreground">
        Answer structured profiling questions and get suitability guidance where every claim links back to
        the document, sentiment signal, or rule behind it.
      </p>

      {/* Action Buttons: "Start New Session" or "Resume Previous" */}
      <div className="mt-8 flex flex-wrap items-center gap-3">
        <Button size="lg" className="gap-2" disabled={starting} onClick={() => void start()}>
          Start a new session
          <ArrowRight className="size-4" />
        </Button>
        {latest ? (
          <Button
            size="lg"
            variant="outline"
            onClick={() =>
              void navigate({
                to: "/chat/$sessionId",
                params: { sessionId: latest.session_id },
              })
            }
          >
            Resume previous conversation
          </Button>
        ) : null}
      </div>

      {/* 3-Step Feature Cards explaining how the AI works */}
      <div className="mt-14 grid gap-4 sm:grid-cols-3">
        <Step
          icon={<ListChecks className="size-4 text-primary" />}
          title="Profiling questions"
          body="A short conversation about your goal, horizon, income and existing commitments."
        />
        <Step
          icon={<ShieldCheck className="size-4 text-primary" />}
          title="You correct us"
          body="Review the profile we inferred and edit anything that's wrong before we continue."
        />
        <Step
          icon={<FileSearch className="size-4 text-accent" />}
          title="Evidence beside it"
          body="Sources, sentiment scores and the rule that fired, shown next to the guidance."
        />
      </div>

      {/* Mandatory SEBI / Educational Disclaimer Notice */}
      <div className="mt-10 flex gap-3 rounded-xl border border-warning/40 bg-warning/10 p-4">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" />
        <p className="text-sm leading-relaxed text-foreground/90">
          This is an educational and suitability tool. It is <strong>not investment advice</strong>,
          it does not forecast markets, and no returns are guaranteed. Nothing here should be
          treated as a recommendation to buy or sell any specific security.
        </p>
      </div>
    </main>
  );
}

/**
 * Reusable Step Card Component:
 * Displays an icon, bold title, and short descriptive text for the landing page.
 */
function Step({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <div className="mb-3">{icon}</div>
      <p className="text-sm font-semibold">{title}</p>
      <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{body}</p>
    </div>
  );
}
