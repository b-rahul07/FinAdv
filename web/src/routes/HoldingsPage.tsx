import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Upload, Wallet } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Delta, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/common";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { RangeBar, Segmented } from "@/features/charts/Charts";
import { AddTransactionDialog, InstrumentSearch } from "@/features/holdings/AddTransaction";
import { CasImportDialog } from "@/features/holdings/CasImport";
import { OthersTab } from "@/features/holdings/OthersTab";
import { api } from "@/lib/api";
import { date, inr, num, pct, signedInr } from "@/lib/format";
import type { Holding, HoldingsResp, WatchRow } from "@/lib/types";

const TABS = ["Stocks", "Mutual funds", "Other & loans", "Watchlist"] as const;
type Tab = (typeof TABS)[number];

export function useHoldings() {
  return useQuery({
    queryKey: ["holdings"],
    queryFn: () => api.get<HoldingsResp>("/api/holdings"),
    refetchInterval: (q) => ((q.state.data?.loading.length ?? 0) > 0 ? 4000 : false),
  });
}

export function SourceNote({ source, d, stale }: { source: string | null; d: string | null; stale?: boolean }) {
  if (!source || !d) return <span className="text-xs text-muted-foreground">No price yet</span>;
  const short = source.replace(" bhavcopy", "").replace("MFapi.in (AMFI NAV history)", "AMFI via MFapi").replace("AMFI daily NAV", "AMFI");
  return (
    <span title={`${source}, as of ${date(d)}`} className={stale ? "block whitespace-nowrap text-xs font-semibold text-warn" : "block whitespace-nowrap text-xs text-muted-foreground"}>
      {short} · {date(d)}
      {stale ? " · not updated recently" : ""}
    </span>
  );
}

export function HoldingsPage() {
  const [tab, setTab] = useState<Tab>("Stocks");
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const h = useHoldings();
  const isMf = tab === "Mutual funds";
  const items = (h.data?.items ?? []).filter((x) => (isMf ? x.instrument.kind === "mf" : x.instrument.kind !== "mf"));
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-8 md:py-10">
      <PageHeader
        crumbs={["Home", "Holdings"]}
        title="Holdings"
        actions={
          (tab === "Stocks" || tab === "Mutual funds") && (
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
      <div className="mb-4">
        <Segmented label="Holdings type" value={tab} options={TABS} onChange={setTab} />
      </div>
      {h.isError && <ErrorState message="Could not load holdings." onRetry={() => h.refetch()} />}
      {h.isLoading && <Skeleton className="h-64" />}
      {h.data && (tab === "Stocks" || tab === "Mutual funds") && (items.length === 0 ? (
        <EmptyState icon={<Wallet className="size-5" />} title={isMf ? "No mutual funds yet" : "No stocks yet"}
          body={isMf ? "Import your CAS, or add a purchase or SIP instalment, to track NAV, gains and XIRR." : "Add a purchase or import a demat CAS to track price, day change, gains and the 52-week range."}>
          <button onClick={() => setImporting(true)} className="rounded-full border px-5 py-2.5 text-sm font-semibold hover:bg-surface-2">Import CAS</button>
          <button onClick={() => setAdding(true)} className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground">Add {isMf ? "a fund" : "a stock"}</button>
        </EmptyState>
      ) : (
        <HoldingsTable items={items} mf={isMf} loading={h.data.loading} />
      ))}
      {tab === "Watchlist" && <Watchlist />}
      {tab === "Other & loans" && <OthersTab />}
      <AddTransactionDialog open={adding} onOpenChange={setAdding} kind={isMf ? "mf" : "listed"} />
      <CasImportDialog open={importing} onOpenChange={setImporting} />
    </div>
  );
}

function HoldingsTable({ items, mf, loading }: { items: Holding[]; mf: boolean; loading: string[] }) {
  const th = "px-3 py-2.5 text-right text-xs font-semibold text-muted-foreground";
  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-sm">
          <thead className="border-b bg-surface-2/50">
            <tr>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground">{mf ? "Scheme" : "Stock"}</th>
              <th className={th}>{mf ? "Units" : "Qty"}</th>
              <th className={th}>{mf ? "Avg NAV" : "Avg price"}</th>
              <th className={th}>Invested</th>
              <th className={th}>{mf ? "NAV" : "Price"}</th>
              <th className={th}>Value</th>
              <th className={th}>Day</th>
              <th className={th}>Gain</th>
              {!mf && <th className="px-3 py-2.5 text-xs font-semibold text-muted-foreground">52-week range</th>}
              <th className={th}>Held</th>
              <th className={th}>Weight</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((h) => (
              <tr key={h.instrument.id} className="hover:bg-surface-2/40">
                <td className="max-w-60 px-4 py-3">
                  <Link to="/holdings/$instrumentId" params={{ instrumentId: h.instrument.id }} className="font-semibold hover:underline">
                    {mf ? h.instrument.name : h.instrument.symbol}
                  </Link>
                  <p className="truncate text-xs text-muted-foreground">
                    {mf ? [h.instrument.plan, h.instrument.option, h.instrument.category].filter(Boolean).join(" · ") : `${h.instrument.name} · ${h.instrument.exchange}`}
                  </p>
                  {loading.includes(h.instrument.id) ? (
                    <span className="text-xs text-muted-foreground">Loading price history…</span>
                  ) : (
                    <SourceNote source={h.price_source} d={h.price_date} stale={h.stale} />
                  )}
                </td>
                <td className="num px-3 text-right">{num(h.qty, mf ? 3 : 0)}</td>
                <td className="num px-3 text-right">{inr(h.avg_price, 2)}</td>
                <td className="num px-3 text-right">{inr(h.invested, 2)}</td>
                <td className="num px-3 text-right">{h.price != null ? inr(h.price, mf ? 4 : 2) : "—"}</td>
                <td className="num px-3 text-right font-semibold">{h.value != null ? inr(h.value, 2) : "—"}</td>
                <td className="px-3 text-right">
                  {h.day_change != null && h.day_change_pct != null ? (
                    <div className="flex flex-col items-end gap-0.5">
                      <Delta value={h.day_change} text={pct(h.day_change_pct, 2, true)} />
                      <span className="num text-xs text-muted-foreground">{signedInr(h.day_change, 2)}</span>
                    </div>
                  ) : "—"}
                </td>
                <td className="px-3 text-right">
                  {h.unrealised != null ? (
                    <div className="flex flex-col items-end gap-0.5">
                      <span className="num font-semibold">{signedInr(h.unrealised, 2)}</span>
                      {h.unrealised_pct != null && <Delta value={h.unrealised} text={pct(h.unrealised_pct, 2, true)} />}
                      {mf && (h.xirr != null ? (
                        <span className="num text-xs text-muted-foreground">XIRR {pct(h.xirr, 1)}</span>
                      ) : (
                        <Tooltip><TooltipTrigger className="text-xs text-muted-foreground underline decoration-dotted">simple return</TooltipTrigger><TooltipContent>{h.xirr_note}</TooltipContent></Tooltip>
                      ))}
                    </div>
                  ) : "—"}
                </td>
                {!mf && <td className="px-3">{h.week52 ? <RangeBar low={h.week52.low} high={h.week52.high} value={h.price} /> : <span className="text-xs text-muted-foreground">Not enough data</span>}</td>}
                <td className="whitespace-nowrap px-3 text-right text-xs">
                  <span className="num">{h.holding_days != null ? (h.holding_days >= 365 ? `${(h.holding_days / 365).toFixed(1)} y` : `${h.holding_days} d`) : "—"}</span>
                  <Tooltip>
                    <TooltipTrigger className="block w-full text-right text-muted-foreground underline decoration-dotted">
                      {h.long_term_qty > 0 && h.short_term_qty > 0 ? "part long-term" : h.long_term_qty > 0 ? "long-term" : "short-term"}
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      Equity gains are long-term after more than 12 months (FY 2026-27 rules). {num(h.long_term_qty, mf ? 3 : 0)} long-term, {num(h.short_term_qty, mf ? 3 : 0)} short-term. Estimated, not tax advice.
                    </TooltipContent>
                  </Tooltip>
                </td>
                <td className="num px-3 text-right">{h.weight != null ? pct(h.weight, 1) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t px-4 py-2.5 text-xs text-muted-foreground">
        Prices are end-of-day closes, adjusted for splits and bonuses when compared across dates. FinAdvisor shows data, never buy/sell calls.
      </p>
    </div>
  );
}

function Watchlist() {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const w = useQuery({ queryKey: ["watchlist"], queryFn: () => api.get<WatchRow[]>("/api/watchlist"), refetchInterval: (q) => (q.state.data?.some((r) => r.current_price == null) ? 4000 : false) });
  const add = useMutation({
    mutationFn: (id: string) => api.post("/api/watchlist", { instrument_id: id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      setAdding(false);
      toast.success("Added to watchlist");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/api/watchlist/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }) });
  const th = "px-3 py-2.5 text-right text-xs font-semibold text-muted-foreground";
  return (
    <>
      <div className="mb-3 flex justify-end">
        <button onClick={() => setAdding(true)} className="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2"><Plus className="size-4" aria-hidden /> Follow a stock</button>
      </div>
      {w.data?.length === 0 && <EmptyState title="Nothing on your watchlist" body="Follow stocks you don't own to see how they move from the day you added them." />}
      {!!w.data?.length && (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="border-b bg-surface-2/50">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground">Stock</th>
                <th className={th}>Date added</th>
                <th className="px-3 py-2.5 text-xs font-semibold text-muted-foreground">52-week range</th>
                <th className={th}>Price when added</th>
                <th className={th}>Current price</th>
                <th className={th}>Change since added</th>
                <th className="w-10" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {w.data.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-3">
                    <Link to="/holdings/$instrumentId" params={{ instrumentId: r.instrument.id }} className="font-semibold hover:underline">{r.instrument.symbol ?? r.instrument.name}</Link>
                    <p className="text-xs text-muted-foreground">{r.instrument.name}</p>
                    <SourceNote source={r.price_source} d={r.price_date} stale={r.stale} />
                  </td>
                  <td className="num px-3 text-right">{date(r.added_on)}</td>
                  <td className="px-3">{r.week52 ? <RangeBar low={r.week52.low} high={r.week52.high} value={r.current_price} /> : <span className="text-xs text-muted-foreground">Loading…</span>}</td>
                  <td className="num px-3 text-right">{r.price_when_added != null ? inr(r.price_when_added, 2) : "—"}{r.price_when_added_date && r.price_when_added_date !== r.added_on && <span className="block text-xs text-muted-foreground">close of {date(r.price_when_added_date)}</span>}</td>
                  <td className="num px-3 text-right">{r.current_price != null ? inr(r.current_price, 2) : "—"}</td>
                  <td className="px-3 text-right">{r.change_since_added != null ? <Delta value={r.change_since_added} text={pct(r.change_since_added, 2, true)} /> : "—"}</td>
                  <td className="px-2"><button aria-label={`Remove ${r.instrument.symbol}`} className="rounded-lg p-1.5 text-muted-foreground hover:bg-surface-2" onClick={() => del.mutate(r.id)}><Trash2 className="size-4" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="max-w-lg rounded-2xl">
          <DialogTitle>Follow a stock</DialogTitle>
          <InstrumentSearch kind="listed" onPick={(i) => add.mutate(i.id)} autoFocus />
        </DialogContent>
      </Dialog>
    </>
  );
}
