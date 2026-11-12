import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Plus, Upload, Wallet } from "lucide-react";
import { useState } from "react";
import { Delta, EmptyState, ErrorState, InfoNote, PageHeader, Section, Skeleton } from "@/components/common";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { AllocationDonut, Segmented, ValueChart } from "@/features/charts/Charts";
import { AddTransactionDialog } from "@/features/holdings/AddTransaction";
import { CasImportDialog } from "@/features/holdings/CasImport";
import { HoldingsList, useHoldings, Watchlist } from "@/features/holdings/HoldingsList";
import { OthersSection } from "@/features/holdings/OthersTab";
import { FactsSync, FactsTab } from "@/features/profile/FactsTab";
import { api } from "@/lib/api";
import { date, inr, pct, signedInr } from "@/lib/format";
import type { DashboardResp } from "@/lib/types";

/** Everything owned, owed and insured, and the facts the advisor uses. One place, seven short tabs. */
export const MONEY_TABS = ["Overview", "Stocks", "Funds", "Deposits & other", "Loans", "Insurance", "Facts"] as const;
export type MoneyTab = (typeof MONEY_TABS)[number];

const RANGES = ["1M", "6M", "1Y", "3Y", "ALL"] as const;

export function MoneyPage() {
  const search = useSearch({ strict: false }) as { tab?: string; fill?: boolean };
  const navigate = useNavigate();
  const tab: MoneyTab = (MONEY_TABS as readonly string[]).includes(search.tab ?? "") ? (search.tab as MoneyTab) : "Overview";
  const setTab = (t: MoneyTab, fill = false) => navigate({ to: "/money", search: { tab: t, ...(fill ? { fill: true } : {}) }, replace: true });
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const market = tab === "Stocks" || tab === "Funds";
  const isMf = tab === "Funds";
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-8 md:py-10">
      <PageHeader
        eyebrow="What you own, owe and are covered for"
        title="My money"
        actions={
          market && (
            <>
              <button onClick={() => setImporting(true)} className="inline-flex items-center gap-2 rounded-full border px-5 py-2.5 text-sm font-semibold hover:bg-surface-2">
                <Upload className="size-4" aria-hidden /> Import CAS
              </button>
              <button onClick={() => setAdding(true)} className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground">
                <Plus className="size-4" aria-hidden /> Add {isMf ? "fund" : "stock"}
              </button>
            </>
          )
        }
      />
      {tab !== "Facts" && <FactsSync onReview={() => setTab("Facts", true)} />}
      <div className="-mx-4 mb-4 overflow-x-auto px-4 [&_button]:whitespace-nowrap md:mx-0 md:px-0">
        <Segmented label="Section of My money" value={tab} options={MONEY_TABS} onChange={(t) => setTab(t)} />
      </div>
      {tab === "Overview" && <Overview onAdd={() => setTab("Stocks")} />}
      {market && <Market mf={isMf} onAdd={() => setAdding(true)} onImport={() => setImporting(true)} />}
      {tab === "Stocks" && <Watchlist />}
      {tab === "Deposits & other" && <OthersSection part="assets" />}
      {tab === "Loans" && <OthersSection part="loans" />}
      {tab === "Insurance" && <OthersSection part="insurance" />}
      {tab === "Facts" && <FactsTab fill={!!search.fill} />}
      <AddTransactionDialog open={adding} onOpenChange={setAdding} kind={isMf ? "mf" : "listed"} />
      <CasImportDialog open={importing} onOpenChange={setImporting} />
    </div>
  );
}

function Market({ mf, onAdd, onImport }: { mf: boolean; onAdd: () => void; onImport: () => void }) {
  const h = useHoldings();
  if (h.isError) return <ErrorState message="Could not load holdings." onRetry={() => h.refetch()} />;
  if (!h.data) return <Skeleton className="h-64" />;
  const items = h.data.items.filter((x) => (mf ? x.instrument.kind === "mf" : x.instrument.kind !== "mf"));
  if (items.length === 0)
    return (
      <EmptyState icon={<Wallet className="size-5" />} title={mf ? "No mutual funds yet" : "No stocks yet"}
        body={mf ? "Import your CAS, or add a purchase or SIP instalment, to track NAV, gains and XIRR." : "Add a purchase or import a demat CAS to track price, day change, gains and the 52-week range."}>
        <button onClick={onImport} className="rounded-full border px-5 py-2.5 text-sm font-semibold hover:bg-surface-2">Import CAS</button>
        <button onClick={onAdd} className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground">Add {mf ? "a fund" : "a stock"}</button>
      </EmptyState>
    );
  return <HoldingsList items={items} mf={mf} loading={h.data.loading} />;
}

function Explain({ children, tip }: { children: React.ReactNode; tip: string }) {
  return (
    <Tooltip>
      <TooltipTrigger className="text-left underline decoration-dotted decoration-muted-foreground/50 underline-offset-4">{children}</TooltipTrigger>
      <TooltipContent className="max-w-xs">{tip}</TooltipContent>
    </Tooltip>
  );
}

/** Net worth in parts, its trend, the allocation and the returns: the charts that used to fill the dashboard. */
function Overview({ onAdd }: { onAdd: () => void }) {
  const [range, setRange] = useState<(typeof RANGES)[number]>("1Y");
  const q = useQuery({ queryKey: ["dashboard", range], queryFn: () => api.get<DashboardResp>(`/api/dashboard?range=${range}`), placeholderData: (p) => p });
  if (q.isError) return <ErrorState message="Could not load your overview." onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-72" />;
  const d = q.data;
  if (d.holdings_count === 0)
    return (
      <EmptyState icon={<Wallet className="size-5" />} title="Nothing tracked yet"
        body="Add what you own and owe to see your net worth, its daily trend and how it is split. Until then we show nothing rather than a guess.">
        <button onClick={onAdd} className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground">Add a holding</button>
      </EmptyState>
    );
  const r = d.returns;
  return (
    <div className="space-y-4">
      <Section eyebrow="Net worth" title={inr(d.net_worth.value)}
        action={d.latest_price_date ? <span className="rounded-full bg-surface-2 px-2.5 py-1 text-xs font-semibold text-muted-foreground">as of {date(d.latest_price_date)} close</span> : undefined}>
        <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div><dt className="text-muted-foreground">Stocks and funds</dt><dd className="num text-lg font-bold">{inr(d.net_worth.market_assets)}</dd></div>
          <div><dt className="text-muted-foreground">Deposits and other</dt><dd className="num text-lg font-bold">{inr(d.net_worth.other_assets)}</dd></div>
          <div><dt className="text-muted-foreground">Loans</dt><dd className="num text-lg font-bold">−{inr(d.net_worth.liabilities)}</dd></div>
          <div><dt className="text-muted-foreground">Today</dt><dd><Delta value={d.day_change} text={signedInr(d.day_change)} /></dd></div>
        </dl>
        <p className="num mt-3 whitespace-normal text-xs text-muted-foreground">
          {d.net_worth.self_reported > 0 ? `Includes ${inr(d.net_worth.self_reported)} you estimated yourself. ` : ""}
          {d.unpriced ? `${d.unpriced} holding(s) have no price yet and are left out. ` : ""}
          {d.net_worth.unvalued.length ? `Not valued: ${d.net_worth.unvalued.join(", ")}.` : ""}
        </p>
      </Section>

      <Section eyebrow="Value over time" title="Portfolio" action={<Segmented label="Range" value={range} options={RANGES} onChange={setRange} />}>
        {d.series.points.length < 2 ? (
          <InfoNote>Not enough daily prices yet to draw a trend. History loads in the background after you add a holding.</InfoNote>
        ) : (
          <>
            {d.range_change != null && (
              <p className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                <Delta value={d.range_change} text={signedInr(d.range_change)} />
                <Explain tip="Change in value over the selected range, excluding money you added or withdrew.">market change over {range}</Explain>
              </p>
            )}
            <ValueChart points={d.series.points} benchmarkLabel={d.series.benchmark_label} />
          </>
        )}
      </Section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
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
    </div>
  );
}
