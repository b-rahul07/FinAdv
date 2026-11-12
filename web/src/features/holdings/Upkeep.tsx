import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Repeat } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ErrorState, Pill, Section, Skeleton } from "@/components/common";
import { api } from "@/lib/api";
import { date, inr, num, pct, signedInr } from "@/lib/format";
import type { GainsStatement, SipsResp } from "@/lib/types";
import { cn } from "@/lib/utils";

const SIP_STATUS: Record<string, { label: string; tone: string }> = {
  active: { label: "Running", tone: "bg-gain-soft text-gain" },
  missed: { label: "Instalment missed", tone: "bg-warn-soft text-warn" },
  stopped: { label: "Looks stopped", tone: "bg-surface-2 text-muted-foreground" },
  off: { label: "Marked stopped", tone: "bg-surface-2 text-muted-foreground" },
};

/** SIPs found from the purchases already tracked: nothing to type. The person can only say whether one is running. */
export function Sips() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["sips"], queryFn: () => api.get<SipsResp>("/api/sips") });
  const set = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => api.patch(`/api/sips/${id}`, { active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sips"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      qc.invalidateQueries({ queryKey: ["nudges"] });
    },
    onError: (e) => toast.error((e as Error).message),
  });
  if (!q.data || q.data.items.length === 0) return null;      // no SIP found: say nothing rather than explain an empty list
  const d = q.data;
  return (
    <Section className="mb-4" eyebrow="Found from your purchases" title={`SIPs · ${inr(d.monthly_total)} a month`}>
      <ul className="divide-y">
        {d.items.map((s) => {
          const st = SIP_STATUS[s.status];
          return (
            <li key={s.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-surface-2 text-muted-foreground"><Repeat className="size-4" aria-hidden /></span>
              <div className="min-w-0 flex-1 basis-48">
                <p className="truncate text-sm font-semibold">{s.instrument.name}</p>
                <p className="num whitespace-normal text-xs text-muted-foreground">
                  {s.instalments} instalments since {date(s.since)}, around day {s.day_of_month} · last {date(s.last_date)}
                  {s.status === "active" || s.status === "missed" ? ` · next expected ${date(s.next_expected)}` : ""}
                </p>
              </div>
              <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-bold", st.tone)}>{st.label}</span>
              <span className="num text-sm font-bold">{inr(s.amount)}<span className="font-normal text-muted-foreground">/month</span></span>
              <button disabled={set.isPending} onClick={() => set.mutate({ id: s.id, active: !s.active })}
                className="rounded-full border px-3 py-1.5 text-xs font-semibold hover:bg-surface-2 disabled:opacity-50">
                {s.active ? "I stopped this" : "It is running"}
              </button>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        A SIP is {d.window.min_instalments} or more buys of the same fund, about a month apart, each within {pct(d.window.tolerance, 0)} of the same amount.
        An instalment more than {d.window.grace_days} days late counts as missed.
      </p>
    </Section>
  );
}

/** Realised gains for a financial year, sale by sale, with the estimate and a CSV for the tax return. */
export function CapitalGains() {
  const [fy, setFy] = useState<string | undefined>();
  const q = useQuery({
    queryKey: ["capital-gains", fy ?? "current"],
    queryFn: () => api.get<GainsStatement>(`/api/tax/capital-gains${fy ? `?fy=${fy}` : ""}`),
    placeholderData: (p) => p,
  });
  if (q.isError) return <ErrorState message="Could not load capital gains." onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-40" />;
  const d = q.data;
  if (d.rows.length === 0 && d.years.length <= 1) return null;     // nothing sold in any year: no section
  const e = d.equity;
  return (
    <Section
      eyebrow="Capital gains · estimate"
      title={`Sales in FY ${d.financial_year}`}
      action={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <label className="sr-only" htmlFor="cg-fy">Financial year</label>
          <select id="cg-fy" className="rounded-full border bg-card px-3 py-1.5 text-sm font-semibold" value={d.financial_year} onChange={(ev) => setFy(ev.target.value)}>
            {d.years.map((y) => <option key={y} value={y}>FY {y}</option>)}
          </select>
          <button
            disabled={d.rows.length === 0}
            onClick={() => api.download(`/api/tax/capital-gains.csv?fy=${d.financial_year}`, `capital-gains-${d.financial_year}.csv`).catch(() => toast.error("Download failed"))}
            className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-semibold hover:bg-surface-2 disabled:opacity-40">
            <Download className="size-4" aria-hidden /> CSV
          </button>
        </div>
      }
    >
      {d.rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing was sold between {date(d.from)} and {date(d.to)}.</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div><dt className="text-muted-foreground">Short-term (equity)</dt><dd className="num text-lg font-bold">{signedInr(e.short_term)}</dd><dd className="text-xs text-muted-foreground">taxed at {pct(e.short_term_rate, 0)}</dd></div>
            <div><dt className="text-muted-foreground">Long-term (equity)</dt><dd className="num text-lg font-bold">{signedInr(e.long_term)}</dd><dd className="num text-xs text-muted-foreground">{pct(e.long_term_rate, 1)} above {inr(e.exemption)}</dd></div>
            <div><dt className="text-muted-foreground">Estimated tax</dt><dd className="num text-lg font-bold">{inr(e.tax)}</dd><dd className="text-xs text-muted-foreground">equity gains only</dd></div>
            <div><dt className="text-muted-foreground">At your slab rate</dt><dd className="num text-lg font-bold">{signedInr(d.slab.gain)}</dd><dd className="text-xs text-muted-foreground">debt and other funds</dd></div>
          </dl>
          <ul className="mt-4 divide-y border-t">
            {d.rows.map((r, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{r.name}</p>
                  <p className="num whitespace-normal text-xs text-muted-foreground">
                    {num(r.quantity, r.kind === "mf" ? 3 : 0)} bought {date(r.buy_date)} at {inr(r.buy_price, 2)}, sold {date(r.sell_date)} at {inr(r.sell_price, 2)}
                  </p>
                </div>
                <span className="flex items-center gap-2">
                  <Pill>{r.term === "long" ? "Long-term" : "Short-term"}</Pill>
                  <span className="num font-bold">{signedInr(r.gain)}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="mt-3 text-xs text-muted-foreground">{d.note}</p>
    </Section>
  );
}
