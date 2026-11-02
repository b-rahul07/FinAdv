import { Check, ChevronDown, Copy, Loader2, RefreshCw, ThumbsDown, ThumbsUp } from "lucide-react";
import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api } from "@/lib/api";
import type { Card, FollowupsCard, Stage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { GoalView, HealthCheckView, NotYetView, PlanView } from "./cards/AdviceCards";
import { EvidenceView } from "./cards/EvidenceView";
import { ChatProfileCard, ChatQuestionnaireCard } from "./cards/ProfileCards";
import { WhatIfView } from "./cards/WhatIfView";
import type { LiveMessage } from "./useChat";
import { WhyPanel } from "./WhyPanel";

const STAGE_LABEL: Record<string, string> = {
  extraction: "Reading your message",
  capacity: "Scoring capacity for loss",
  planner: "Choosing products from what you're allowed",
  audit: "Auditing the plan against twin profiles",
  gate: "Checking suitability",
  retrieval: "Reading FinAdvisor's documents",
};

const ROUTE_LABEL: Record<string, string> = { learn: "Learn", plan: "Plan", check: "Check" };

export function CardView({ card, onAsk }: { card: Card; onAsk: (text: string) => void }) {
  switch (card.type) {
    case "health_check":
      return <HealthCheckView card={card} />;
    case "plan":
      return <PlanView card={card} />;
    case "goal":
      return <GoalView card={card} />;
    case "not_yet":
    case "check_ok":
      return <NotYetView card={card} />;
    case "what_if":
      return "sliders" in card ? <WhatIfView card={card} /> : null;
    case "evidence":
      return <EvidenceView card={card} />;
    case "profile":
      return <ChatProfileCard card={card} onConfirmed={() => onAsk("Build my plan with my confirmed profile")} />;
    case "questionnaire":
      return <ChatQuestionnaireCard onDone={() => onAsk("Build my plan with my confirmed profile")} />;
  }
}

function Stages({ stages }: { stages: Stage[] }) {
  if (!stages.length) return null;
  return (
    <ol className="mb-3 space-y-1 text-sm text-muted-foreground" aria-live="polite">
      {stages.map((s) => (
        <li key={s.stage} className="flex items-center gap-2">
          {s.status === "done" ? <Check className="size-4 text-good" aria-hidden /> : <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />}
          <span>
            {STAGE_LABEL[s.stage] ?? s.stage}
            {s.detail && s.status !== "done" ? ` · ${s.detail}` : ""}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Memoised: a finished message only re-renders if its own data changes, not while another streams. */
export const MessageView = memo(function MessageView({ m, isLast, onRegenerate, onAsk }: { m: LiveMessage; isLast: boolean; onRegenerate: () => void; onAsk: (t: string) => void }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-surface-2 px-4 py-2.5">{m.content}</div>
      </div>
    );
  }
  const streaming = m.status === "streaming";
  // Saved answers from before the question-first layout have no `show`; they keep every card in the reply.
  const main = m.cards.filter((c) => c.show !== "details" && c.type !== "followups");
  const details = m.cards.filter((c) => c.show === "details");
  const followups = m.cards.find((c) => c.type === "followups") as FollowupsCard | undefined;
  const advice = m.cards.some((c) => c.type === "plan" || c.type === "not_yet" || c.type === "check_ok");
  return (
    <article className="group" aria-busy={streaming}>
      {m.route && ROUTE_LABEL[m.route] && <p className="eyebrow mb-2">{ROUTE_LABEL[m.route]}</p>}
      {streaming && <Stages stages={m.stages ?? []} />}
      {m.content && (
        <div className="prose-chat">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
          {streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-foreground/60 align-middle motion-reduce:animate-none" aria-hidden />}
        </div>
      )}
      {!m.content && streaming && !(m.stages ?? []).length && <div className="skeleton h-4 w-40" />}
      {m.sources.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
          {m.sources.map((s) => (
            <span key={s.n} className="rounded-full border px-2.5 py-1 text-muted-foreground" title={s.source}>
              [{s.n}] {s.title}
            </span>
          ))}
        </div>
      )}
      {main.length > 0 && (
        <div className="mt-4 grid gap-3">
          {main.map((c, i) => (
            <CardView key={i} card={c} onAsk={onAsk} />
          ))}
        </div>
      )}
      {followups && isLast && !streaming && (
        <div className="mt-4 flex flex-wrap gap-2" aria-label="Suggested next questions">
          {followups.items.map((q) => (
            <button key={q} onClick={() => onAsk(q)} className="rounded-full border px-3.5 py-1.5 text-sm transition-colors hover:bg-surface-2">
              {q}
            </button>
          ))}
        </div>
      )}
      {(details.length > 0 || (advice && !streaming)) && (
        <Details cards={details} onAsk={onAsk} why={advice && !streaming ? <WhyPanel runId={m.advice_run_id} live={m.why} /> : null} />
      )}
      {advice && <p className="mt-2 text-xs text-muted-foreground">Education and planning only. FinAdvisor is not a SEBI-registered investment adviser.</p>}
      {m.status === "stopped" && <p className="mt-2 text-xs font-semibold text-muted-foreground">Stopped</p>}
      {m.status === "error" && <p className="mt-2 text-sm text-loss">This answer could not be completed. Try regenerating it.</p>}
      {!streaming && !m.id.startsWith("live") && <Actions m={m} isLast={isLast} onRegenerate={onRegenerate} />}
    </article>
  );
});

const DETAIL_LABEL: Record<string, string> = { plan: "full plan", goal: "goals", health_check: "health check", what_if: "what-if" };

/** The supporting cards, closed by default so the reply itself stays short. */
function Details({ cards, onAsk, why }: { cards: Card[]; onAsk: (t: string) => void; why: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const names = [...new Set(cards.map((c) => DETAIL_LABEL[c.type]).filter(Boolean))];
  const label = names.length ? `See the ${names.join(", ")}${why ? " and why" : ""}` : "Why this answer";
  return (
    <div className="mt-3">
      <button className="flex items-center gap-1.5 text-sm font-semibold text-primary underline-offset-4 hover:underline" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
        {open ? "Hide details" : label}
      </button>
      {open && (
        <div className="mt-3 grid gap-3">
          {cards.map((c, i) => (
            <CardView key={i} card={c} onAsk={onAsk} />
          ))}
          {why}
        </div>
      )}
    </div>
  );
}

function Actions({ m, isLast, onRegenerate }: { m: LiveMessage; isLast: boolean; onRegenerate: () => void }) {
  const [rating, setRating] = useState<number>(m.feedback?.rating ?? 0);
  const [comment, setComment] = useState(m.feedback?.comment ?? "");
  const [open, setOpen] = useState(false);
  const send = (r: number, c = comment) => api.post(`/api/messages/${m.id}/feedback`, { rating: r, comment: c }).catch(() => toast.error("Could not save feedback"));
  const btn = "rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground";
  return (
    <div className="mt-2 flex items-center gap-0.5 opacity-100 md:opacity-0 md:transition-opacity md:group-focus-within:opacity-100 md:group-hover:opacity-100">
      <button
        className={btn}
        aria-label="Copy answer"
        onClick={() => {
          navigator.clipboard.writeText(m.content).then(() => toast.success("Copied"));
        }}
      >
        <Copy className="size-4" />
      </button>
      {isLast && (
        <button className={btn} aria-label="Regenerate answer" onClick={onRegenerate}>
          <RefreshCw className="size-4" />
        </button>
      )}
      <button
        className={cn(btn, rating === 1 && "text-good")}
        aria-label="Good answer"
        aria-pressed={rating === 1}
        onClick={() => {
          const r = rating === 1 ? 0 : 1;
          setRating(r);
          send(r);
        }}
      >
        <ThumbsUp className="size-4" />
      </button>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            className={cn(btn, rating === -1 && "text-loss")}
            aria-label="Bad answer"
            aria-pressed={rating === -1}
            onClick={() => {
              if (rating !== -1) {
                setRating(-1);
                send(-1);
              }
            }}
          >
            <ThumbsDown className="size-4" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-80">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(-1, comment).then(() => toast.success("Thanks, noted"));
              setOpen(false);
            }}
          >
            <label htmlFor={`fb-${m.id}`} className="text-sm font-semibold">
              What went wrong? (optional)
            </label>
            <textarea id={`fb-${m.id}`} className="mt-2 h-20 w-full rounded-lg border bg-card p-2 text-sm" value={comment} onChange={(e) => setComment(e.target.value)} />
            <button className="mt-2 rounded-full bg-primary px-4 py-1.5 text-sm font-semibold text-primary-foreground">Send</button>
          </form>
        </PopoverContent>
      </Popover>
    </div>
  );
}
