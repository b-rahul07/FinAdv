import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, MessageCircle, Plus, Upload, XCircle } from "lucide-react";
import { useState } from "react";
import { Delta, EmptyState, ErrorState, InfoNote, Section, Skeleton } from "@/components/common";
import { useMe } from "@/components/layout/AppShell";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AllocationDonut, Segmented, ValueChart } from "@/features/charts/Charts";
import { api } from "@/lib/api";
import { date, inr, inrParts, longDay, pct, signedInr } from "@/lib/format";
import type { DashboardResp, HealthCheck } from "@/lib/types";
import { cn } from "@/lib/utils";

const RANGES = ["1M", "6M", "1Y", "3Y", "ALL"] as const;

function greeting() {
  const h = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }).format(new Date()));
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function Explain({ children, tip }: { children: React.ReactNode; tip: string }) {
  return (
    <Tooltip>
      <TooltipTrigger className="text-left underline decoration-dotted decoration-muted-foreground/50 underline-offset-4">{children}</TooltipTrigger>
      <TooltipContent className="max-w-xs">{tip}</TooltipContent>
    </Tooltip>
  );
}

export function Dashboard() {
  const me = useMe();
  const [range, setRange] = useState<(typeof RANGES)[number]>("1Y");
  const q = useQuery({ queryKey: ["dashboard", range], queryFn: () => api.get<DashboardResp>(`/api/dashboard?range=${range}`), placeholderData: (p) => p });
  const first = me.data?.name?.split(" ")[0];
  const d = q.data;
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-8 md:py-10">
      <p className="text-sm text-muted-foreground">{longDay()}</p>
      <h1 className="mt-1 text-[28px] font-extrabold tracking-tight md:text-[34px]">{greeting()}{first ? `, ${first}` : ""}.</h1>
      {q.isError && <div className="mt-6"><ErrorState message="Could not load your dashboard." onRetry={() => q.refetch()} /></div>}
      {!d && q.isLoading && <Skeleton className="mt-6 h-72" />}
      {d && (d.holdings_count === 0 ? <FirstDay d={d} /> : <Full d={d} range={range} setRange={setRange} />)}
    </div>
  );
}

function Actions() {
  return (
    <div className="mt-6 flex flex-wrap gap-2">
      <Link to="/chat" className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground"><MessageCircle className="size-4" aria-hidden /> Ask advisor</Link>
      <Link to="/holdings" className="inline-flex items-center gap-2 rounded-full border px-5 py-2.5 text-sm font-semibold hover:bg-surface-2"><Plus className="size-4" aria-hidden /> Add holding</Link>
      <Link to="/holdings" className="inline-flex items-center gap-2 rounded-full border px-5 py-2.5 text-sm font-semibold hover:bg-surface-2"><Upload className="size-4" aria-hidden /> Import CAS</Link>
    </div>
  );
}

function FirstDay({ d }: { d: DashboardResp }) {
  return (
    <>
      <div className="mt-6 grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <section className="card p-6 md:p-7">
          <p className="eyebrow">Net worth</p>
          <h2 className="mt-3 text-2xl font-extrabold tracking-tight">Your story is just starting.</h2>
          <p className="mt-2 max-w-lg text-muted-foreground">Add what you own to see your net worth, daily trend and allocation. Until then we show nothing rather than a guess.</p>
          <Actions />
        </section>
        <HealthScore h={d.health} version={d.profile_version} />
      </div>
      <div className="mt-4"><AdviceList d={d} /></div>
    </>
  );
}

function Full({ d, range, setRange }: { d: DashboardResp; range: (typeof RANGES)[number]; setRange: (r: (typeof RANGES)[number]) => void }) {
  const parts = inrParts(d.net_worth.value);
  const r = d.returns;
  return (
    <>
      <div className="mt-6 grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <section className="card p-6 md:p-7" aria-labelledby="nw-label">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p id="nw-label" className="eyebrow">Net worth</p>
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
            {d.range_change != null && (
              <>
                <Delta value={d.range_change} text={signedInr(d.range_change)} />
                <Explain tip="Change in value over the selected range, excluding money you added or withdrew.">market change over {range}</Explain>
              </>
            )}
          </div>
          <p className="num mt-2 whitespace-normal text-xs text-muted-foreground">
            Assets {inr(d.net_worth.assets)} − loans {inr(d.net_worth.liabilities)}.
            {d.net_worth.self_reported > 0 ? ` Includes ${inr(d.net_worth.self_reported)} you estimated yourself.` : ""}
            {d.unpriced ? ` ${d.unpriced} holding(s) have no price yet and are left out.` : ""}
            {d.net_worth.unvalued.length ? ` Not valued: ${d.net_worth.unvalued.join(", ")}.` : ""}
          </p>
          <Actions />
        </section>
        <HealthScore h={d.health} version={d.profile_version} />
      </div>

      <Section className="mt-4" eyebrow="Value over time" title="Portfolio" action={<Segmented label="Range" value={range} options={RANGES} onChange={setRange} />}>
        {d.series.points.length < 2 ? (
          <InfoNote>Not enough daily prices yet to draw a trend. History loads in the background after you add a holding.</InfoNote>
        ) : (
          <ValueChart points={d.series.points} benchmarkLabel={d.series.benchmark_label} />
        )}
      </Section>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Section eyebrow="Allocation" title="By asset class">
          <AllocationDonut data={d.allocation} />
        </Section>
        <Section eyebrow="Overall returns" title={signedInr(r.gain)}>
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div><dt className="text-muted-foreground"><Explain tip="Cost of the units you still hold, including charges.">Invested</Explain></dt><dd className="num text-lg font-bold">{inr(r.invested)}</dd></div>
            <div><dt className="text-muted-foreground"><Explain tip="Units × latest published close or NAV.">Current value</Explain></dt><dd className="num text-lg font-bold">{inr(r.value)}</dd></div>
            <div><dt className="text-muted-foreground"><Explain tip="Current value minus invested, for holdings with a price.">Absolute gain</Explain></dt><dd className="flex items-center gap-2"><span className="num text-lg font-bold">{signedInr(r.gain)}</span>{r.simple != null && <Delta value={r.gain} text={pct(r.simple, 1, true)} />}</dd></div>
            <div>
              <dt className="text-muted-foreground"><Explain tip="Annualised return that accounts for when each rupee went in (cash-flow timed). Shown only after a year of investing.">XIRR</Explain></dt>
              <dd className="num text-lg font-bold">{r.xirr != null ? pct(r.xirr, 1) : "—"}</dd>
              {r.note && <dd className="text-xs text-muted-foreground">{r.note}</dd>}
            </div>
          </dl>
          {d.movers.length > 0 && (
            <>
              <h3 className="mb-2 mt-6 text-sm font-bold">Top movers today</h3>
              <ul className="divide-y">
                {d.movers.map((m) => (
                  <li key={m.instrument.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <Link to="/holdings/$instrumentId" params={{ instrumentId: m.instrument.id }} className="min-w-0 truncate font-medium hover:underline">
                      {m.instrument.kind === "mf" ? m.instrument.name : m.instrument.symbol}
                    </Link>
                    <span className="flex items-center gap-2"><span className="num text-xs text-muted-foreground">{signedInr(m.day_change)}</span><Delta value={m.day_change_pct} text={pct(m.day_change_pct, 2, true)} /></span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      </div>
      <div className="mt-4"><AdviceList d={d} /></div>
    </>
  );
}

function HealthScore({ h, version }: { h: HealthCheck | null; version: number | null }) {
  if (!h)
    return (
      <Section eyebrow="Money health" title="Not checked yet">
        <p className="text-sm text-muted-foreground">Confirm your profile and FinAdvisor runs a 7-point check based on SEBI's thresholds.</p>
        <Link to="/profile" className="mt-4 inline-flex rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2">Set up profile</Link>
      </Section>
    );
  return (
    <Section eyebrow="Money health" action={<Link to="/chat" className="text-sm font-semibold text-brand">Ask why</Link>}>
      <p className="text-4xl font-extrabold">{h.score}<span className="text-xl text-muted-foreground">/{h.out_of}</span></p>
      <p className="text-sm text-muted-foreground">checks pass · profile version {version}</p>
      <ul className="mt-4 space-y-1.5 text-sm">
        {h.checks.map((c) => (
          <li key={c.key} className="flex items-center gap-2">
            {c.status === "pass" ? <CheckCircle2 className="size-4 text-good" aria-label="Pass" /> : <XCircle className="size-4 text-loss" aria-label="Needs attention" />}
            <span className={cn(c.status === "fail" && "font-semibold")}>{c.title}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

const STATUS = ["suggested", "done", "skipped"] as const;

function AdviceList({ d }: { d: DashboardResp }) {
  const qc = useQueryClient();
  const set = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.patch(`/api/recommendations/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard"] }),
  });
  return (
    <Section eyebrow="From your advisor" title="Latest advice">
      {d.advice.length === 0 ? (
        <EmptyState title="No advice yet" body="Ask the advisor for a plan; each step appears here so you can mark it done or skipped." icon={<MessageCircle className="size-5" />} />
      ) : (
        <ul className="divide-y">
          {d.advice.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm">{r.title}</p>
                <p className="text-xs text-muted-foreground">Suggested {date(r.suggested_at)}</p>
              </div>
              <div role="radiogroup" aria-label="Status" className="flex rounded-full border p-0.5 text-xs">
                {STATUS.map((s) => (
                  <button key={s} role="radio" aria-checked={r.status === s} onClick={() => set.mutate({ id: r.id, status: s })}
                    className={cn("rounded-full px-2.5 py-1 font-semibold capitalize", r.status === s ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>
                    {s}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
