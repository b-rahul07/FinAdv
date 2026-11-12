import { Link } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, CircleDashed, CircleDot, SkipForward } from "lucide-react";
import { EmptyState, InfoNote, NOT_ADVISER, Pill, Section } from "@/components/common";
import { api } from "@/lib/api";
import { date, inr, monthYear, months, pct } from "@/lib/format";
import type { GoalProgress, HomePlan, HomeResp, TimelineStep } from "@/lib/types";
import { cn } from "@/lib/utils";

const ACTION: Record<string, string> = {
  buy_health_cover: "Buy health cover",
  buy_term_cover: "Buy term life cover",
  clear_card_dues: "Clear card dues",
  repay_costly_loan: "Repay the costly loan",
  build_emergency_fund: "Build the emergency fund",
  no_new_emi: "No new EMIs",
  invest: "Invest",
};

const PLAN_Q = "Make me a money plan";

/** When a step happens, in words. The dates come from the API. */
function when(s: TimelineStep): string {
  if (s.kind === "one_off") return `in ${monthYear(s.starts_on)}`;
  if (s.kind === "ongoing") return `from ${monthYear(s.starts_on)}, ongoing`;
  return s.ends_on && s.ends_on !== s.starts_on ? `${monthYear(s.starts_on)} to ${monthYear(s.ends_on)}` : `in ${monthYear(s.starts_on)}`;
}

function useStepStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.patch(`/api/recommendations/${id}`, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["home"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

export function PlanBlock({ home }: { home: HomeResp }) {
  const plan = home.plan;
  if (!plan)
    return (
      <Section eyebrow="Your plan">
        <EmptyState
          title="No plan yet"
          body={home.profile_version
            ? "Your facts are in. Ask for a plan and it appears here: each step, what it costs a month, and the month it starts."
            : "Tell the advisor what you earn, spend, owe and want. It asks only what it needs, then lays out the steps in order."}
        >
          <Link to="/chat" search={{ q: PLAN_Q }} className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground">
            Make my plan <ArrowRight className="size-4" aria-hidden />
          </Link>
        </EmptyState>
        <GoalBars goals={home.goals} />
      </Section>
    );
  const next = plan.steps.find((s) => s.order === plan.next_order) ?? null;
  return (
    <Section
      eyebrow="Your plan"
      title={`${plan.done} of ${plan.total} steps done`}
      action={plan.chat_id ? <Link to="/chat/$chatId" params={{ chatId: plan.chat_id }} className="shrink-0 text-sm font-semibold text-brand">Open in advisor</Link> : undefined}
    >
      <div className="h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={plan.done} aria-valuemin={0} aria-valuemax={plan.total} aria-label="Plan steps done">
        <div className="h-full rounded-full bg-good" style={{ width: `${(plan.done / Math.max(1, plan.total)) * 100}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Made {date(plan.made_at)} from your facts{plan.profile_version ? ` (version ${plan.profile_version})` : ""}. It works with{" "}
        <span className="num font-semibold text-foreground">{inr(plan.monthly_surplus)}</span> left each month.
      </p>

      {plan.stale && (
        <div className="mt-4">
          <InfoNote tone="warn">
            Your facts changed after this plan was made, so its amounts may be out of date.{" "}
            <Link to="/chat" search={{ q: "Update my money plan for my latest facts" }} className="font-semibold underline underline-offset-2">Re-plan</Link>
          </InfoNote>
        </div>
      )}

      {next ? <NextStep step={next} total={plan.total} /> : (
        <p className="mt-4 rounded-2xl bg-gain-soft px-4 py-3 text-sm">
          Every step is done or skipped. Ask for a fresh plan when your income, loans or goals change.
        </p>
      )}

      <Timeline plan={plan} />

      {plan.notes.length > 0 && (
        <ul className="mt-4 space-y-1 text-xs text-muted-foreground">
          {plan.notes.map((n) => <li key={n}>• {n}</li>)}
        </ul>
      )}
      <GoalBars goals={home.goals} />
      <p className="mt-5 text-xs text-muted-foreground">{NOT_ADVISER}</p>
    </Section>
  );
}

function NextStep({ step, total }: { step: TimelineStep; total: number }) {
  const set = useStepStatus();
  const id = step.recommendation_id;
  return (
    <div className="mt-4 rounded-2xl border-2 border-brand/40 bg-info-soft p-4">
      <p className="eyebrow">Next step · {step.order} of {total}</p>
      <p className="mt-1.5 text-[15px] font-semibold leading-relaxed">{step.text}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {step.monthly > 0 && <Pill className="num bg-card">{inr(step.monthly)}/month</Pill>}
        {step.months > 0 && <Pill className="num bg-card">{months(step.months)}</Pill>}
        <Pill className="bg-card">{when(step)}</Pill>
      </div>
      {id && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button disabled={set.isPending} onClick={() => set.mutate({ id, status: "done" })}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60">
            <Check className="size-4" aria-hidden /> I've done this
          </button>
          <button disabled={set.isPending} onClick={() => set.mutate({ id, status: "skipped" })}
            className="inline-flex items-center gap-1.5 rounded-full border bg-card px-4 py-2 text-sm font-semibold hover:bg-surface-2 disabled:opacity-60">
            <SkipForward className="size-4" aria-hidden /> Skip
          </button>
        </div>
      )}
    </div>
  );
}

/** Steps as bars over months. Position and length come from the API; status is always said in words as well. */
function Timeline({ plan }: { plan: HomePlan }) {
  const set = useStepStatus();
  return (
    <div className="mt-6">
      <h3 className="text-sm font-bold">Timeline</h3>
      <div className="mt-2 hidden md:grid md:grid-cols-[minmax(0,17rem)_1fr] md:gap-4" aria-hidden>
        <span />
        <div className="relative h-5 text-[11px] text-muted-foreground">
          {plan.axis.map((a) => (
            <span key={a.month} className="num absolute top-0 whitespace-nowrap" style={{ left: `${a.offset * 100}%` }}>{monthYear(a.label_on)}</span>
          ))}
        </div>
      </div>
      <ol className="mt-1 space-y-3 md:space-y-2">
        {plan.steps.map((s) => {
          const isNext = s.order === plan.next_order;
          const closed = s.status === "done" || s.status === "skipped";
          const Icon = s.status === "done" ? Check : s.status === "skipped" ? SkipForward : isNext ? CircleDot : CircleDashed;
          return (
            <li key={s.order} className="md:grid md:grid-cols-[minmax(0,17rem)_1fr] md:items-center md:gap-4">
              <div className="flex items-start gap-2.5">
                <span className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full", s.status === "done" ? "bg-good text-background" : isNext ? "bg-brand text-background" : "bg-surface-2 text-muted-foreground")}>
                  <Icon className="size-3.5" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <p className={cn("text-sm font-semibold", closed && "text-muted-foreground", s.status === "skipped" && "line-through")}>
                    {s.order}. {ACTION[s.action] ?? s.action}{s.goal ? ` · ${s.goal}` : ""}
                    <span className="ml-2 text-xs font-bold">{s.status === "done" ? "Done" : s.status === "skipped" ? "Skipped" : isNext ? "Next" : ""}</span>
                  </p>
                  <p className="num whitespace-normal text-xs text-muted-foreground">
                    {s.monthly > 0 ? `${inr(s.monthly)}/month · ` : ""}{when(s)}
                  </p>
                </div>
                {s.recommendation_id && closed && (
                  <button onClick={() => set.mutate({ id: s.recommendation_id!, status: "suggested" })} className="shrink-0 rounded-full px-2 py-1 text-xs font-semibold text-muted-foreground underline underline-offset-2 hover:text-foreground">
                    Undo
                  </button>
                )}
              </div>
              <div className="relative mt-1.5 h-3 rounded-full bg-surface-2 md:mt-0" aria-hidden>
                <span
                  className={cn(
                    "absolute inset-y-0 min-w-3 rounded-full",
                    s.status === "done" ? "bg-good/50" : s.status === "skipped" ? "bg-muted-foreground/30" : isNext ? "bg-brand" : "bg-brand/45",
                    s.kind === "ongoing" && "rounded-r-none [mask-image:linear-gradient(to_right,black_70%,transparent)]",
                  )}
                  style={{ left: `${s.offset * 100}%`, width: `${s.width * 100}%` }}
                />
              </div>
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-xs text-muted-foreground">
        Investing starts in <span className="num font-semibold text-foreground">{monthYear(plan.invest_starts_on)}</span> at{" "}
        <span className="num font-semibold text-foreground">{inr(plan.investing_monthly)}/month</span>. Bars that fade have no end date.
      </p>
    </div>
  );
}

export function GoalBars({ goals }: { goals: GoalProgress[] }) {
  if (goals.length === 0) return null;
  return (
    <div className="mt-6">
      <h3 className="text-sm font-bold">Goals</h3>
      <ul className="mt-2 grid grid-cols-1 gap-x-8 gap-y-4 md:grid-cols-2">
        {goals.map((g) => (
          <li key={g.goal_id}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 truncate font-semibold">{g.name}</span>
              <span className="num shrink-0 text-xs text-muted-foreground">in {g.horizon_years} year{g.horizon_years === 1 ? "" : "s"}</span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={Math.round(g.funded * 100)} aria-valuemin={0} aria-valuemax={100} aria-label={`${g.name}: share saved so far`}>
              <div className="h-full rounded-full bg-series-3" style={{ width: `${g.funded * 100}%` }} />
            </div>
            <p className="num mt-1 whitespace-normal text-xs text-muted-foreground">
              {inr(g.saved_so_far)} of {inr(g.target_today)} saved ({pct(g.funded, 0)}), in today's rupees.
              {g.sip_needed != null && g.monthly_assigned != null && (
                <> Needs {inr(g.sip_needed)}/month; your plan gives <span className="font-semibold text-foreground">{inr(g.monthly_assigned)}</span>
                  {g.fundable === false && g.shortfall > 0 ? `, short by ${inr(g.shortfall)}` : ""}.</>
              )}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
