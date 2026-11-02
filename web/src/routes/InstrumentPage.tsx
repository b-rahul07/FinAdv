import { useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Delta, ErrorState, InfoNote, PageHeader, Section, Skeleton } from "@/components/common";
import { PriceChart, RangeBar, Segmented } from "@/features/charts/Charts";
import { AddTransactionDialog } from "@/features/holdings/AddTransaction";
import { api } from "@/lib/api";
import { date, inr, num, pct, signedInr } from "@/lib/format";
import type { Holding, Instrument, TxRow } from "@/lib/types";
import { SourceNote } from "./HoldingsPage";

type Detail = {
  instrument: Instrument;
  range: string;
  points: { date: string; close: number }[];
  marks: { date: string; kind: string; quantity: number; price: number }[];
  holding: Holding | null;
  note: string;
  price_source: string | null;
  price_date: string | null;
  history_starts: string | null;
  week52: { low: number; high: number } | null;
  corporate_actions: { ex_date: string; factor: number }[];
  loading: boolean;
};

const RANGES = ["1M", "6M", "1Y", "5Y"] as const;

export function InstrumentPage() {
  const { instrumentId } = useParams({ strict: false }) as { instrumentId: string };
  const [range, setRange] = useState<(typeof RANGES)[number]>("1Y");
  const [adding, setAdding] = useState(false);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["instrument", instrumentId, range],
    queryFn: () => api.get<Detail>(`/api/instruments/${instrumentId}?range=${range}`),
    refetchInterval: (x) => (x.state.data?.loading ? 4000 : false),
  });
  const txs = useQuery({ queryKey: ["tx", instrumentId], queryFn: () => api.get<TxRow[]>(`/api/transactions?instrument_id=${instrumentId}`) });
  const [note, setNote] = useState("");
  useEffect(() => setNote(q.data?.note ?? ""), [q.data?.note]);
  const saveNote = useMutation({ mutationFn: () => api.put(`/api/instruments/${instrumentId}/note`, { text: note }), onSuccess: () => toast.success("Note saved") });
  const delTx = useMutation({
    mutationFn: (id: string) => api.del(`/api/transactions/${id}`),
    onSuccess: () => qc.invalidateQueries(),
    onError: (e) => toast.error((e as Error).message),
  });

  if (q.isError) return <div className="mx-auto max-w-5xl p-8"><ErrorState message="Could not load this instrument." onRetry={() => q.refetch()} /></div>;
  if (!q.data) return <div className="mx-auto max-w-5xl p-8"><Skeleton className="h-96" /></div>;
  const d = q.data;
  const i = d.instrument;
  const h = d.holding;
  const last = d.points.at(-1)?.close ?? null;
  const mf = i.kind === "mf";
  const from = d.points[0]?.date;
  const visibleMarks = from ? d.marks.filter((m) => m.date >= from) : [];
  return (
    <div className="mx-auto max-w-5xl px-4 py-6 md:px-8 md:py-10">
      <PageHeader crumbs={["Holdings", mf ? "Mutual funds" : "Stocks"]} eyebrow={mf ? [i.amc, i.category].filter(Boolean).join(" · ") : `${i.exchange} · ${i.isin}`}
        title={mf ? i.name : `${i.symbol}`}
        actions={<button onClick={() => setAdding(true)} className="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2"><Plus className="size-4" aria-hidden /> Add transaction</button>} />
      {!mf && <p className="-mt-4 mb-6 text-muted-foreground">{i.name}</p>}

      <Section>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-3xl font-extrabold">{last != null ? inr(last, mf ? 4 : 2) : "—"}</p>
            <SourceNote source={d.price_source} d={d.price_date} />
          </div>
          <Segmented label="Chart range" value={range} options={RANGES} onChange={setRange} />
        </div>
        {d.loading && d.points.length === 0 ? (
          <div className="grid h-72 place-items-center text-sm text-muted-foreground">Loading price history from the exchange archives…</div>
        ) : d.points.length < 2 ? (
          <div className="grid h-72 place-items-center text-sm text-muted-foreground">Not enough price history for this range yet.</div>
        ) : (
          <PriceChart points={d.points} marks={visibleMarks} />
        )}
        <ul className="mt-3 flex flex-wrap gap-x-5 text-xs text-muted-foreground">
          <li className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-series-1" aria-hidden />{mf ? "NAV" : "Close"} (adjusted)</li>
          {visibleMarks.some((m) => m.kind === "buy") && <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-series-3" aria-hidden />Your buys</li>}
          {visibleMarks.some((m) => m.kind === "sell") && <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-series-2" aria-hidden />Your sells</li>}
        </ul>
        {d.marks.length > visibleMarks.length && <p className="mt-2 text-xs text-muted-foreground">{d.marks.length - visibleMarks.length} of your transactions fall before this range; pick a longer one to see them.</p>}
        {d.history_starts && <p className="mt-2 text-xs text-muted-foreground">History stored from {date(d.history_starts)}. Older ranges show what is available.</p>}
        {d.corporate_actions.length > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">
            Adjusted for {d.corporate_actions.map((a) => `a split/bonus on ${date(a.ex_date)} (×${num(a.factor, 3)})`).join(", ")}, derived from the exchange's published previous close.
          </p>
        )}
      </Section>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {!mf && (
          <Section eyebrow="52-week range" title={d.week52 ? `${inr(d.week52.low, 2)} – ${inr(d.week52.high, 2)}` : "Not enough data"}>
            {d.week52 && <RangeBar low={d.week52.low} high={d.week52.high} value={last} />}
            <p className="mt-2 text-xs text-muted-foreground">From adjusted daily highs and lows over the last 52 weeks.</p>
          </Section>
        )}
        <Section eyebrow="Your position" title={h ? `${num(h.qty, mf ? 3 : 0)} ${mf ? "units" : "shares"}` : "You don't hold this"}>
          {h ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-muted-foreground">Invested</dt><dd className="num font-semibold">{inr(h.invested, 2)}</dd></div>
              <div><dt className="text-muted-foreground">Value</dt><dd className="num font-semibold">{h.value != null ? inr(h.value, 2) : "—"}</dd></div>
              <div><dt className="text-muted-foreground">Gain</dt><dd className="flex items-center gap-2"><span className="num font-semibold">{h.unrealised != null ? signedInr(h.unrealised, 2) : "—"}</span>{h.unrealised_pct != null && <Delta value={h.unrealised ?? 0} text={pct(h.unrealised_pct, 2, true)} />}</dd></div>
              <div><dt className="text-muted-foreground">{h.xirr != null ? "XIRR" : "Return"}</dt><dd className="num font-semibold">{h.xirr != null ? pct(h.xirr, 1) : h.unrealised_pct != null ? pct(h.unrealised_pct, 1) : "—"}</dd>{h.xirr == null && <dd className="text-xs text-muted-foreground">Under a year: not annualised</dd>}</div>
              <div><dt className="text-muted-foreground">Long-term / short-term</dt><dd className="num">{num(h.long_term_qty, mf ? 3 : 0)} / {num(h.short_term_qty, mf ? 3 : 0)}</dd></div>
              {h.realised !== 0 && <div><dt className="text-muted-foreground">Realised</dt><dd className="num">{signedInr(h.realised, 2)}</dd></div>}
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">Add a purchase to track it.</p>
          )}
        </Section>
      </div>

      {mf && i.plan === "Regular" && (
        <div className="mt-4">
          <InfoNote>
            This is a <strong>regular</strong> plan: part of its expense ratio pays a distributor's commission. The same fund's direct plan has the same portfolio and a lower expense ratio, so it usually returns a little more each year. This is an explanation of costs, not an instruction to switch; switching can trigger tax and exit loads.
          </InfoNote>
        </div>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Section eyebrow="History" title="Your transactions">
          {txs.data?.length ? (
            <ul className="divide-y text-sm">
              {txs.data.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div>
                    <p className="font-semibold capitalize">{t.kind} · <span className="num">{num(t.quantity, mf ? 3 : 0)} @ {inr(t.price, 2)}</span></p>
                    <p className="text-xs text-muted-foreground">{date(t.trade_date)} · {t.source === "cas" ? "from CAS" : "added by you"}</p>
                  </div>
                  <button aria-label="Delete transaction" className="rounded-lg p-1.5 text-muted-foreground hover:bg-surface-2" onClick={() => delTx.mutate(t.id)}><Trash2 className="size-4" /></button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No transactions.</p>
          )}
        </Section>
        <Section eyebrow="Private" title="Notes">
          <label htmlFor="note" className="sr-only">Your notes</label>
          <textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} className="h-32 w-full rounded-xl border bg-card p-3 text-sm" placeholder="Why you bought it, what you're watching…" />
          <button onClick={() => saveNote.mutate()} className="mt-2 rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-surface-2">Save note</button>
        </Section>
      </div>
      <AddTransactionDialog open={adding} onOpenChange={setAdding} kind={mf ? "mf" : "listed"} preset={i} />
    </div>
  );
}
