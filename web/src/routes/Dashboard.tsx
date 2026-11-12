import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, CheckCircle2, XCircle } from "lucide-react";
import { useState } from "react";
import { Delta, ErrorState, InfoNote, Section, Skeleton } from "@/components/common";
import { useMe } from "@/components/layout/AppShell";
import { PlanBlock } from "@/features/home/PlanBlock";
import { api } from "@/lib/api";
import { date, inr, inrParts, longDay, signedInr } from "@/lib/format";
import type { CashFlow, DashboardResp, HomeResp } from "@/lib/types";

function greeting() {
  const h = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }).format(new Date()));
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** Home answers three things in order: where you stand, what to do next, and anything else you want to ask. */
export function Dashboard() {
  const me = useMe();
  const dash = useQuery({ queryKey: ["dashboard", "1Y"], queryFn: () => api.get<DashboardResp>("/api/dashboard?range=1Y") });
  const home = useQuery({ queryKey: ["home"], queryFn: () => api.get<HomeResp>("/api/home") });
  const first = me.data?.name?.split(" ")[0];
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-8 md:py-10">
      <p className="text-sm text-muted-foreground">{longDay()}</p>
      <h1 className="mt-1 text-[28px] font-extrabold tracking-tight md:text-[34px]">{greeting()}{first ? `, ${first}` : ""}.</h1>
      {(dash.isError || home.isError) && (
        <div className="mt-6"><ErrorState message="Could not load your home page." onRetry={() => { dash.refetch(); home.refetch(); }} /></div>
      )}

      <h2 className="sr-only">Where you stand</h2>
      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[1.6fr_1fr]">
        <section className="card p-6 md:p-7" aria-label="Net worth and monthly cash flow">
          {dash.data ? <NetWorth d={dash.data} /> : <Skeleton className="h-28" />}
          <div className="my-5 border-t" />
          {home.data ? <CashFlowStrip c={home.data.cash_flow} version={home.data.profile_version} /> : <Skeleton className="h-24" />}
        </section>
        {home.data ? <Health h={home.data} /> : <Skeleton className="h-72" />}
      </div>

      <div className="mt-4">{home.data ? <PlanBlock home={home.data} /> : <Skeleton className="h-64" />}</div>

      <Ask />
    </div>
  );
}

function NetWorth({ d }: { d: DashboardResp }) {
  if (d.holdings_count === 0)
    return (
      <>
        <p className="eyebrow">Net worth</p>
        <h3 className="mt-3 text-2xl font-extrabold tracking-tight">Your story is just starting.</h3>
        <p className="mt-2 max-w-lg text-muted-foreground">Add what you own and owe to see your net worth here. Until then we show nothing rather than a guess.</p>
        <Link to="/money" search={{ tab: "Stocks" }} className="mt-4 inline-flex rounded-full border px-5 py-2.5 text-sm font-semibold hover:bg-surface-2">Add what you own</Link>
      </>
    );
  const parts = inrParts(d.net_worth.value);
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="eyebrow">Net worth</p>
        {d.latest_price_date && (
          <span className="rounded-full bg-surface-2 px-2.5 py-1 text-xs font-semibold text-muted-foreground">as of {date(d.latest_price_date)} close</span>
        )}
      </div>
      <p className="mt-3 text-5xl font-extrabold tracking-tight md:text-6xl">
        {parts.whole}<span className="text-3xl text-muted-foreground md:text-4xl">{parts.fraction}</span>
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <Delta value={d.day_change} text={signedInr(d.day_change)} />
        <span className="text-muted-foreground">today</span>
      </div>
      <p className="num mt-2 whitespace-normal text-sm text-muted-foreground">
        Assets {inr(d.net_worth.assets)} − loans {inr(d.net_worth.liabilities)}.{" "}
        <Link to="/money" className="font-semibold text-brand">See it all</Link>
      </p>
    </>
  );
}

const FLOW = [
  { key: "emis", label: "EMIs", dot: "bg-series-2" },
  { key: "expenses", label: "Expenses", dot: "bg-series-1" },
  { key: "left_over", label: "Left over", dot: "bg-series-3" },
] as const;

/** Take-home to what is left. "Left over" is the amount the plan works with, so the two never disagree. */
function CashFlowStrip({ c, version }: { c: CashFlow | null; version: number | null }) {
  if (!c || !c.widths)
    return (
      <>
        <p className="eyebrow">Each month</p>
        <p className="mt-2 text-sm text-muted-foreground">Add your take-home pay, expenses and EMIs to see what is left each month. That is the amount every plan is built on.</p>
        <Link to="/money" search={{ tab: "Facts" }} className="mt-3 inline-flex rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2">Add my monthly facts</Link>
      </>
    );
  return (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="eyebrow">Each month</p>
        <p className="text-sm text-muted-foreground">Take-home <span className="num font-bold text-foreground">{inr(c.take_home)}</span></p>
      </div>
      <div className="mt-3 flex h-3 gap-0.5 overflow-hidden rounded-full" aria-hidden>
        {FLOW.map((f) => c.widths![f.key] > 0 && <span key={f.key} className={f.dot} style={{ width: `${c.widths![f.key] * 100}%` }} />)}
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
        {FLOW.map((f) => (
          <div key={f.key}>
            <dt className="flex items-center gap-1.5 text-muted-foreground"><span className={`size-2 rounded-full ${f.dot}`} aria-hidden />{f.label}</dt>
            <dd className={f.key === "left_over" ? "num text-xl font-extrabold" : "num text-lg font-bold"}>{inr(c[f.key])}</dd>
          </div>
        ))}
      </dl>
      {c.short_by > 0 && (
        <div className="mt-3"><InfoNote tone="warn">Expenses and EMIs are <strong className="num">{inr(c.short_by)}</strong> more than take-home, so nothing is left to plan with.</InfoNote></div>
      )}
      {!!c.sips && (
        <p className="num mt-3 whitespace-normal text-sm">
          <strong>{inr(c.sips)}</strong> of the left-over already goes into {c.sips_count === 1 ? "a SIP" : `${c.sips_count} SIPs`} each month.{" "}
          <Link to="/money" search={{ tab: "Funds" }} className="font-semibold text-brand">See them</Link>
        </p>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        From your facts{version ? ` (version ${version})` : ""}. Your plan works with the left-over amount.{" "}
        <Link to="/money" search={{ tab: "Facts" }} className="font-semibold text-brand">Edit facts</Link>
      </p>
    </>
  );
}

function Health({ h }: { h: HomeResp }) {
  const card = h.health;
  if (!card)
    return (
      <Section eyebrow="Money health" title="Not checked yet">
        <p className="text-sm text-muted-foreground">Confirm your facts and FinAdvisor runs a 7-point check based on SEBI's thresholds.</p>
        <Link to="/money" search={{ tab: "Facts" }} className="mt-4 inline-flex rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2">Set up my facts</Link>
      </Section>
    );
  const fails = card.checks.filter((c) => c.status === "fail");
  const hist = h.health_history;
  return (
    <Section eyebrow="Money health" action={<Link to="/chat" search={{ q: "Explain my money health check" }} className="text-sm font-semibold text-brand">Ask why</Link>}>
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-4xl font-extrabold">{card.score}<span className="text-xl text-muted-foreground">/{card.out_of}</span></p>
          <p className="text-sm text-muted-foreground">checks pass</p>
        </div>
        {hist.length > 1 && <Trend points={hist} />}
      </div>
      {hist.length > 1 && (
        <p className="num mt-1 whitespace-normal text-xs text-muted-foreground">
          {hist.every((x) => x.score === hist[0].score)
            ? `Unchanged across ${hist.length} versions of your facts, since ${date(hist[0].at)}.`
            : `Was ${hist[0].score} of ${hist[0].out_of} on ${date(hist[0].at)}; ${hist.map((x) => x.score).join(" → ")} over ${hist.length} versions of your facts.`}
        </p>
      )}
      <ul className="mt-4 space-y-1.5 text-sm">
        {fails.map((c) => (
          <li key={c.key} className="flex items-start gap-2">
            <XCircle className="mt-0.5 size-4 shrink-0 text-loss" aria-label="Needs attention" />
            <span className="font-semibold">{c.title}</span>
          </li>
        ))}
        {fails.length < card.checks.length && (
          <li className="flex items-start gap-2 text-muted-foreground">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-good" aria-label="Pass" />
            <span>{card.checks.length - fails.length} other check{card.checks.length - fails.length === 1 ? "" : "s"} pass</span>
          </li>
        )}
      </ul>
      <p className="mt-3 text-xs text-muted-foreground">Thresholds from SEBI's investor-portal Financial Health Check.</p>
    </Section>
  );
}

/** A small line of the score across versions of the facts. Decorative: the same numbers are written out beside it. */
function Trend({ points }: { points: HomeResp["health_history"] }) {
  const W = 96, H = 36, pad = 4;
  const xy = points.map((p, i) => [pad + (i * (W - 2 * pad)) / (points.length - 1), H - pad - (p.score / p.out_of) * (H - 2 * pad)] as const);
  const [lx, ly] = xy[xy.length - 1];
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden className="shrink-0 text-brand">
      <polyline points={xy.map((p) => p.join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lx} cy={ly} r="3" fill="currentColor" />
    </svg>
  );
}

const IDEAS = ["Am I on track?", "How much tax will I pay this year?", "Should I buy a phone on a no-cost EMI?"];

function Ask() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const go = (q: string) => {
    const v = q.trim();
    if (v) navigate({ to: "/chat", search: { q: v } });
  };
  return (
    <section className="card mt-4 p-5 md:p-6" aria-labelledby="ask-h">
      <p className="eyebrow">Ask</p>
      <h2 id="ask-h" className="mt-1 text-lg font-bold tracking-tight">Anything else about your money?</h2>
      <form className="mt-3 flex items-center gap-2 rounded-2xl border bg-background p-2 focus-within:ring-2 focus-within:ring-ring" onSubmit={(e) => { e.preventDefault(); go(text); }}>
        <label htmlFor="home-ask" className="sr-only">Ask the advisor</label>
        <input id="home-ask" value={text} onChange={(e) => setText(e.target.value)} placeholder="Can I afford a car loan of ₹12,000 a month?" className="min-w-0 flex-1 bg-transparent px-2 py-2 outline-none" />
        <button type="submit" disabled={!text.trim()} aria-label="Ask" className="grid size-10 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground disabled:opacity-40">
          <ArrowUp className="size-5" />
        </button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        {IDEAS.map((q) => (
          <button key={q} onClick={() => go(q)} className="rounded-full border px-3 py-1.5 text-sm text-muted-foreground hover:bg-surface-2 hover:text-foreground">{q}</button>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted-foreground">Education and planning only, not investment advice. FinAdvisor is not SEBI-registered and never recommends individual securities.</p>
    </section>
  );
}
