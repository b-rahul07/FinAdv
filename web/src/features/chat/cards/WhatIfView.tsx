import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Slider } from "@/components/ui/slider";
import { api } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import type { WhatIfCard, WhatIfResult } from "@/lib/types";
import { CardShell, cap } from "./AdviceCards";

type Key = "take_home_monthly" | "expenses_monthly" | "liquid_savings" | "dependants" | "new_emi";

export function WhatIfView({ card }: { card: WhatIfCard }) {
  const base = card.sliders;
  const [v, setV] = useState(base);
  const m = useMutation({ mutationFn: (changes: Partial<typeof base>) => api.post<WhatIfResult>("/api/what-if", changes) });
  const changed = (Object.keys(base) as Key[]).filter((k) => v[k] !== base[k]);

  useEffect(() => {
    if (!changed.length) return;
    const t = setTimeout(() => m.mutate(Object.fromEntries(changed.map((k) => [k, v[k]]))), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v]);

  const sliders: { k: Key; label: string; max: number; step: number; fmt: (n: number) => string }[] = [
    { k: "take_home_monthly", label: "Take-home pay", max: Math.max(base.take_home_monthly * 2, 50_000), step: 1000, fmt: (n) => `${inr(n)}/month` },
    { k: "expenses_monthly", label: "Expenses", max: Math.max(base.expenses_monthly * 2, 30_000), step: 1000, fmt: (n) => `${inr(n)}/month` },
    { k: "liquid_savings", label: "Emergency savings", max: Math.max(base.liquid_savings * 3, base.expenses_monthly * 12, 100_000), step: 5000, fmt: (n) => inr(n) },
    { k: "new_emi", label: "A new EMI", max: Math.max(base.take_home_monthly * 0.5, 10_000), step: 500, fmt: (n) => `${inr(n)}/month` },
    { k: "dependants", label: "Dependants", max: 6, step: 1, fmt: (n) => String(n) },
  ];

  const r = m.data;
  return (
    <CardShell eyebrow="What if" title="Move a slider to see what changes and why">
      <div className="space-y-4">
        {sliders.map((s) => (
          <div key={s.k}>
            <div className="mb-1.5 flex justify-between text-sm">
              <label id={`wi-${s.k}`} className="font-medium">
                {s.label}
              </label>
              <span className="num font-bold">{s.fmt(v[s.k])}</span>
            </div>
            <Slider aria-labelledby={`wi-${s.k}`} value={[v[s.k]]} min={0} max={s.max} step={s.step} onValueChange={([n]) => setV((x) => ({ ...x, [s.k]: n }))} />
          </div>
        ))}
      </div>
      {changed.length > 0 && (
        <div className="mt-5 rounded-xl bg-surface-2 p-4" aria-live="polite">
          {m.isPending && !r && <p className="text-sm text-muted-foreground">Recalculating…</p>}
          {r && (
            <>
              <div className="grid grid-cols-3 gap-2 text-center text-sm">
                <Compare label="Capacity" a={cap(r.before.capacity_level)} b={cap(r.after.capacity_level)} />
                <Compare label="Investing starts" a={`month ${r.before.invest_start_month}`} b={`month ${r.after.invest_start_month}`} />
                <Compare label="Risky share" a={pct(r.before.rho, 0)} b={pct(r.after.rho, 0)} />
              </div>
              <ul className="mt-3 space-y-1 text-sm">
                {r.explanations.map((e) => (
                  <li key={e}>• {e}</li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-muted-foreground">Illustrative: computed instantly from the rules with a standard mix. Ask the advisor for a full, audited plan.</p>
            </>
          )}
          <button className="mt-3 text-sm font-semibold text-brand underline-offset-2 hover:underline" onClick={() => setV(base)}>
            Reset
          </button>
        </div>
      )}
      {card.twins.length > 0 && (
        <details className="mt-5 border-t pt-4">
          <summary className="cursor-pointer text-sm font-bold">What would change this advice (checked by the auditor)</summary>
          <ul className="mt-3 divide-y text-sm">
            {card.twins.map((t) => (
              <li key={t.relation + t.change} className="flex flex-wrap justify-between gap-2 py-2">
                <span>{t.change}</span>
                <span className="text-muted-foreground">
                  capacity {cap(t.capacity)} · investing from month {t.invest_start_month} · risky share {pct(t.rho ?? 0, 0)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </CardShell>
  );
}

function Compare({ label, a, b }: { label: string; a: string; b: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="num font-bold">
        {a === b ? a : (
          <>
            <span className="text-muted-foreground line-through decoration-1">{a}</span> → {b}
          </>
        )}
      </p>
    </div>
  );
}
