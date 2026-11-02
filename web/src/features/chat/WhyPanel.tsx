import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { Why } from "@/lib/types";
import { cn } from "@/lib/utils";
import { cap } from "./cards/AdviceCards";

const COMPONENTS: [string, string][] = [
  ["s_E", "Emergency fund"],
  ["s_D", "EMI load"],
  ["s_L", "Life cover"],
  ["s_H", "Health cover"],
  ["s_C", "Card dues / costly loans"],
];
const RELATIONS: Record<string, string> = {
  MR1: "less savings",
  MR2: "one more dependant",
  MR3: "a new EMI",
  MR4: "shorter goal horizon",
  MR5: "higher willingness at Low capacity",
  MR6: "same facts, different wording",
};

export function WhyPanel({ runId, live }: { runId: string | null; live?: Why }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["advice", runId],
    queryFn: () => api.get<{ why: Why; model: any; latency_s: number; versions: any }>(`/api/advice/${runId}`),
    enabled: open && !!runId && !live,
  });
  const why = live ?? q.data?.why;
  return (
    <div className="mt-3 rounded-xl border">
      <button className="flex w-full items-center justify-between px-4 py-2.5 text-sm font-semibold" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Why this plan
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className="space-y-4 border-t px-4 py-4 text-sm">
          {!why && <p className="text-muted-foreground">Loading…</p>}
          {why && (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <Stat label="Capacity for loss" value={cap(why.capacity?.level)} />
                <Stat label="Willingness" value={why.willingness ? `${cap(why.willingness.level)}${why.willingness.score ? ` (score ${why.willingness.score}/47)` : ""}` : "—"} />
                <Stat label="Suitability (lower of the two)" value={cap(why.suitability)} />
              </div>
              {why.capacity && (
                <div>
                  <p className="mb-2 font-semibold">Capacity is the weakest of these five scores</p>
                  <ul className="space-y-1.5">
                    {COMPONENTS.map(([k, label]) => {
                      const v = Number(why.capacity?.[k] ?? 0);
                      return (
                        <li key={k} className="grid grid-cols-[150px_1fr_40px] items-center gap-2">
                          <span className="text-muted-foreground">{label}</span>
                          <span className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                            <span className="block h-full rounded-full bg-series-1" style={{ width: `${v * 100}%` }} />
                          </span>
                          <span className="num text-right">{num(v, 2)}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
              {why.rules.length > 0 && (
                <div>
                  <p className="mb-1 font-semibold">Rules that applied</p>
                  <ul className="space-y-1">
                    {why.rules.map((r, i) => (
                      <li key={i}>
                        <strong>{r.rule}</strong> <span className="text-muted-foreground">{r.detail}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {why.gated_out && why.gated_out.length > 0 && (
                <div>
                  <p className="mb-1 font-semibold">Products held back</p>
                  <ul className="space-y-1 text-muted-foreground">
                    {why.gated_out.map((g) => (
                      <li key={g.product_id}>
                        <span className="text-foreground">{g.name}</span>: {g.reasons.join("; ")}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div>
                <p className="mb-1 font-semibold">Audit</p>
                <p className="text-muted-foreground">
                  {why.audit.status === "pass" && "Every check passed on the first try."}
                  {why.audit.status === "repaired" && `The first plan broke ${why.audit.failed_relations?.join(", ") || "a rule"}; it was repaired and re-checked.`}
                  {why.audit.status === "fallback" && "The planner could not pass every check, so a safe plan built from the rules alone is shown."}
                  {why.audit.status === "not_applicable" && "A suitability check, not a plan: no audit needed."}
                </p>
                {why.audit.relations_checked && why.audit.relations_checked.length > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Twin profiles checked: {why.audit.relations_checked.map((r) => `${r} (${RELATIONS[r] ?? r})`).join(", ")}.
                  </p>
                )}
              </div>
              {why.pressure && why.pressure.types.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Pressure noticed ({why.pressure.types.join(", ").replace(/_/g, " ")}). It was acknowledged; it does not change the plan unless your facts change.
                </p>
              )}
              {q.data?.model && (
                <p className="text-xs text-muted-foreground">
                  Model: {q.data.model.model} ({q.data.model.provider}, self-hosted) · {num(q.data.latency_s ?? 0, 1)} s
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-bold">{value}</p>
    </div>
  );
}
