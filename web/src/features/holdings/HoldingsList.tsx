import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Delta, EmptyState } from "@/components/common";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { RangeBar } from "@/features/charts/Charts";
import { InstrumentSearch } from "@/features/holdings/AddTransaction";
import { api } from "@/lib/api";
import { date, inr, num, pct, signedInr } from "@/lib/format";
import type { Holding, HoldingsResp, WatchRow } from "@/lib/types";

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

function held(h: Holding) {
  return h.holding_days != null ? (h.holding_days >= 365 ? `${(h.holding_days / 365).toFixed(1)} y` : `${h.holding_days} d`) : "—";
}

const FOOT = "Prices are end-of-day closes, adjusted for splits and bonuses when compared across dates. FinAdvisor shows data, never buy/sell calls.";

/** A table from `md` up; one card per holding on a phone, so nothing scrolls sideways. */
export function HoldingsList({ items, mf, loading }: { items: Holding[]; mf: boolean; loading: string[] }) {
  return (
    <>
      <ul className="space-y-3 md:hidden">
        {items.map((h) => (
          <li key={h.instrument.id} className="card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Link to="/holdings/$instrumentId" params={{ instrumentId: h.instrument.id }} className="font-semibold hover:underline">
                  {mf ? h.instrument.name : h.instrument.symbol}
                </Link>
                <p className="truncate text-xs text-muted-foreground">
                  {mf ? [h.instrument.plan, h.instrument.option].filter(Boolean).join(" · ") : h.instrument.name}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="num font-bold">{h.value != null ? inr(h.value) : "—"}</p>
                {h.day_change != null && h.day_change_pct != null && <Delta value={h.day_change} text={pct(h.day_change_pct, 2, true)} />}
              </div>
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div><dt className="text-muted-foreground">{mf ? "Units" : "Qty"}</dt><dd className="num font-semibold">{num(h.qty, mf ? 3 : 0)}</dd></div>
              <div><dt className="text-muted-foreground">Invested</dt><dd className="num font-semibold">{inr(h.invested)}</dd></div>
              <div>
                <dt className="text-muted-foreground">Gain</dt>
                <dd className="num font-semibold">
                  {h.unrealised != null ? signedInr(h.unrealised) : "—"}
                  {h.unrealised != null && h.unrealised_pct != null && <span className="font-normal text-muted-foreground"> ({pct(h.unrealised_pct, 1, true)})</span>}
                </dd>
              </div>
            </dl>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 text-xs text-muted-foreground">
              {loading.includes(h.instrument.id) ? <span>Loading price history…</span> : <SourceNote source={h.price_source} d={h.price_date} stale={h.stale} />}
              <span className="num">held {held(h)}{mf && h.xirr != null ? ` · XIRR ${pct(h.xirr, 1)}` : ""}</span>
            </div>
          </li>
        ))}
        <li className="px-1 text-xs text-muted-foreground">{FOOT}</li>
      </ul>
      <div className="hidden md:block">
        <HoldingsTable items={items} mf={mf} loading={loading} />
      </div>
    </>
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
                  <span className="num">{held(h)}</span>
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
      <p className="border-t px-4 py-2.5 text-xs text-muted-foreground">{FOOT}</p>
    </div>
  );
}

export function Watchlist() {
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
    <section aria-labelledby="watch-h" className="mt-8">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 id="watch-h" className="text-lg font-bold tracking-tight">Watchlist</h2>
          <p className="text-sm text-muted-foreground">Stocks you follow but do not own.</p>
        </div>
        <button onClick={() => setAdding(true)} className="inline-flex shrink-0 items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2"><Plus className="size-4" aria-hidden /> Follow a stock</button>
      </div>
      {w.data?.length === 0 && <EmptyState title="Nothing on your watchlist" body="Follow stocks you don't own to see how they move from the day you added them." />}
      {!!w.data?.length && (
        <>
          <ul className="space-y-3 md:hidden">
            {w.data.map((r) => (
              <li key={r.id} className="card flex items-start justify-between gap-3 p-4">
                <div className="min-w-0">
                  <Link to="/holdings/$instrumentId" params={{ instrumentId: r.instrument.id }} className="font-semibold hover:underline">{r.instrument.symbol ?? r.instrument.name}</Link>
                  <p className="truncate text-xs text-muted-foreground">added {date(r.added_on)}{r.price_when_added != null ? ` at ${inr(r.price_when_added, 2)}` : ""}</p>
                  <SourceNote source={r.price_source} d={r.price_date} stale={r.stale} />
                </div>
                <div className="flex shrink-0 items-start gap-1">
                  <div className="text-right">
                    <p className="num font-bold">{r.current_price != null ? inr(r.current_price, 2) : "—"}</p>
                    {r.change_since_added != null && <Delta value={r.change_since_added} text={pct(r.change_since_added, 2, true)} />}
                  </div>
                  <button aria-label={`Remove ${r.instrument.symbol}`} className="rounded-lg p-1.5 text-muted-foreground hover:bg-surface-2" onClick={() => del.mutate(r.id)}><Trash2 className="size-4" /></button>
                </div>
              </li>
            ))}
          </ul>
          <div className="card hidden overflow-x-auto md:block">
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
        </>
      )}
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="max-w-lg rounded-2xl">
          <DialogTitle>Follow a stock</DialogTitle>
          <InstrumentSearch kind="listed" onPick={(i) => add.mutate(i.id)} autoFocus />
        </DialogContent>
      </Dialog>
    </section>
  );
}
