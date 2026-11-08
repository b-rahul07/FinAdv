import { ChevronDown, ExternalLink, ListChecks } from "lucide-react";
import { useState } from "react";
import { date, pct } from "@/lib/format";
import type { FundFinderCard, FundRow } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Past return with its sign in text, so gains and losses never rely on colour alone. */
function Ret({ v }: { v: number | null | undefined }) {
  if (v === null || v === undefined) {
    return (
      <span className="text-muted-foreground">
        —<span className="sr-only">not available</span>
      </span>
    );
  }
  return <span className={cn("num", v < 0 ? "text-loss" : "text-good")}>{pct(v, 1, true)}</span>;
}

function Row({ f }: { f: FundRow }) {
  return (
    <tr className="border-t align-top">
      <th scope="row" className="py-2 pr-3 text-left font-normal">
        <span className="block font-medium">{f.name}</span>
        <span className="block text-xs text-muted-foreground">
          {f.amc}
          {f.since ? ` · since ${new Date(f.since).getFullYear()}` : ""}
        </span>
      </th>
      <td className="num py-2 pr-3 text-right">{f.expense_ratio === null ? <span className="text-muted-foreground">—<span className="sr-only">not published</span></span> : pct(f.expense_ratio / 100, 2)}</td>
      <td className="py-2 pr-3 text-right"><Ret v={f.returns?.["1y"]} /></td>
      <td className="py-2 pr-3 text-right"><Ret v={f.returns?.["3y"]} /></td>
      <td className="py-2 text-right"><Ret v={f.returns?.["5y"]} /></td>
    </tr>
  );
}

/** "Funds of this type": every matching AMFI scheme (Direct, Growth), cheapest first, with facts from FinAdvisor's code. */
export function FundFinderView({ card }: { card: FundFinderCard }) {
  const [tips, setTips] = useState(false);
  const shown = card.funds.length;
  return (
    <section className="rounded-xl border" aria-label={`${card.label}: funds to compare`}>
      <header className="px-4 pt-3">
        <h4 className="font-semibold">
          {card.label} you can compare
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            {shown < card.total ? `the ${shown} cheapest of ${card.total}` : `${card.total} fund${card.total === 1 ? "" : "s"}`}
          </span>
        </h4>
        <p className="mt-1 text-xs text-muted-foreground">Direct plan, Growth option. Returns are yearly averages over each period. Past returns don't predict future returns.</p>
      </header>
      <div className="overflow-x-auto px-4">
        <table className="mt-2 w-full min-w-[560px] text-sm">
          <caption className="sr-only">{card.label}, sorted by expense ratio, lowest first</caption>
          <thead>
            <tr className="text-xs text-muted-foreground">
              <th scope="col" className="pb-1 text-left font-semibold">Fund</th>
              <th scope="col" className="pb-1 pr-3 text-right font-semibold">Expense ratio</th>
              <th scope="col" className="pb-1 pr-3 text-right font-semibold">1 year</th>
              <th scope="col" className="pb-1 pr-3 text-right font-semibold">3 years</th>
              <th scope="col" className="pb-1 text-right font-semibold">5 years</th>
            </tr>
          </thead>
          <tbody>
            {card.funds.map((f) => (
              <Row key={f.code} f={f} />
            ))}
          </tbody>
        </table>
      </div>
      <div className="space-y-3 px-4 py-3 text-sm">
        <button className="flex items-center gap-2 text-sm font-semibold" aria-expanded={tips} onClick={() => setTips((o) => !o)}>
          <ListChecks className="size-4" aria-hidden /> How to choose one
          <ChevronDown className={cn("size-4 transition-transform", tips && "rotate-180")} aria-hidden />
        </button>
        {tips && (
          <ul className="list-disc space-y-1 pl-5">
            {card.checklist.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        )}
        <p className="rounded-lg bg-surface-2 px-3 py-2 text-xs">{card.note}</p>
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {card.links.map((l) => (
            <li key={l.url}>
              <a href={l.url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-primary underline-offset-2 hover:underline">
                {l.label}
                <ExternalLink className="ml-1 inline size-3 align-baseline" aria-label="(opens in a new tab)" />
              </a>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">
          {card.sources.nav} · {card.sources.expense_ratio ?? "Expense ratios unavailable right now"} · {card.sources.returns} · list built {date(card.built_at)}
          {card.stale ? " · older than usual, the weekly update hasn't run" : ""}. Not a SEBI-registered adviser.
        </p>
      </div>
    </section>
  );
}
