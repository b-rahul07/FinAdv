import { Link } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Info } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Pill } from "@/components/common";
import { api } from "@/lib/api";
import { date, inr } from "@/lib/format";
import type { AskCard, PlanChangeCard, ProfileView, Summary, TaxCard, TaxRegime, WhatIfAnswerCard } from "@/lib/types";
import { cn } from "@/lib/utils";
import { cap, CardShell } from "./AdviceCards";

const INPUT = "mt-1 w-full rounded-xl border bg-card px-3 py-2.5 num";

/** Saves answers as a new version of the facts, then lets the caller carry on (usually: ask the question again). */
function useAnswer(onSaved: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (answers: Record<string, number>) => api.post<ProfileView>("/api/profile/answer", { answers }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      onSaved();
    },
    onError: (e) => toast.error((e as Error).message),
  });
}

/** One missing fact, asked once. The answer is remembered, and the original question is asked again. */
export function AskView({ card, onAsk }: { card: AskCard; onAsk: (text: string) => void }) {
  const id = useId();
  const [value, setValue] = useState("");
  const [done, setDone] = useState(false);
  const save = useAnswer(() => {
    setDone(true);
    onAsk(card.then);
  });
  const n = Number(value.replace(/,/g, ""));
  const ok = value.trim() !== "" && Number.isFinite(n) && n >= card.min && n <= card.max;
  return (
    <CardShell eyebrow="One question" title={<label htmlFor={id}>{card.question}</label>}>
      {done ? (
        <p className="flex items-center gap-2 text-sm font-semibold text-good"><Check className="size-4" aria-hidden /> Saved to your facts.</p>
      ) : (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (ok) save.mutate({ [card.field]: n }); }}>
          <div className="min-w-40 flex-1">
            <input id={id} inputMode="decimal" autoComplete="off" className={INPUT} value={value} onChange={(e) => setValue(e.target.value)} aria-describedby={`${id}-hint`} />
          </div>
          <span className="pb-3 text-sm text-muted-foreground">{card.unit}</span>
          <button disabled={!ok || save.isPending} className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-40">
            {save.isPending ? "Saving…" : "Save and answer"}
          </button>
        </form>
      )}
      {card.hint && <p id={`${id}-hint`} className="mt-2 text-xs text-muted-foreground">{card.hint}</p>}
    </CardShell>
  );
}

const ROWS: { key: keyof Summary; label: string; fmt: (s: Summary) => string }[] = [
  { key: "monthly_surplus", label: "Left each month", fmt: (s) => inr(s.monthly_surplus) },
  { key: "investing_monthly", label: "Investing a month", fmt: (s) => inr(s.investing_monthly) },
  { key: "invest_start_month", label: "Investing starts", fmt: (s) => `month ${s.invest_start_month}` },
  { key: "capacity_level", label: "Capacity for loss", fmt: (s) => cap(s.capacity_level) },
  { key: "suitability", label: "Suitability", fmt: (s) => cap(s.suitability) },
];

/** A follow-up "what if": today's facts against the changed ones. Illustrative; the saved plan does not move. */
export function WhatIfAnswerView({ card }: { card: WhatIfAnswerCard }) {
  const qc = useQueryClient();
  const [applied, setApplied] = useState(false);
  const apply = useMutation({
    mutationFn: () => api.put<ProfileView>("/api/profile", { data: card.apply, sources: {} }),
    onSuccess: () => {
      setApplied(true);
      qc.invalidateQueries();
      toast.success("Facts updated. Ask for a plan to rebuild it on them.");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <CardShell eyebrow="What if" title={card.label} aside={<Pill>Illustrative</Pill>}>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th className="py-1.5 font-semibold" scope="col"><span className="sr-only">Measure</span></th>
            <th className="py-1.5 text-right font-semibold" scope="col">Today</th>
            <th className="py-1.5 text-right font-semibold" scope="col">If so</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {ROWS.map((r) => {
            const moved = card.before[r.key] !== card.after[r.key];
            return (
              <tr key={r.key}>
                <th scope="row" className="py-2 text-left font-normal text-muted-foreground">{r.label}</th>
                <td className="num py-2 text-right">{r.fmt(card.before)}</td>
                <td className={cn("num py-2 text-right", moved && "font-bold")}>{r.fmt(card.after)}{moved && <span className="sr-only"> (changed)</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {card.apply ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button disabled={applied || apply.isPending} onClick={() => apply.mutate()} className="rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2 disabled:opacity-50">
            {applied ? "Saved as your facts" : apply.isPending ? "Saving…" : "Make this my profile"}
          </button>
          <span className="text-xs text-muted-foreground">Only if it has really happened. Your plan is rebuilt when you next ask for it.</span>
        </div>
      ) : card.apply_note ? (
        <p className="mt-4 text-sm text-muted-foreground">
          {card.apply_note} <Link to="/money" search={{ tab: "Loans" }} className="font-semibold text-brand">Open Loans</Link>
        </p>
      ) : null}
    </CardShell>
  );
}

const DEDUCTIONS: [keyof TaxCard["deductions"], string][] = [
  ["deductions_80c", "80C (EPF, PPF, ELSS, life premium)"],
  ["deductions_80d", "80D (health-insurance premium)"],
  ["nps_80ccd1b", "Own NPS contribution, 80CCD(1B)"],
  ["hra_exemption_annual", "HRA exemption (payslip or Form 16)"],
];

function Regime({ r, cheaper }: { r: TaxRegime; cheaper: boolean }) {
  return (
    <div className={cn("rounded-2xl border p-4", cheaper && "border-2 border-brand/50 bg-info-soft")}>
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-bold">{r.label}</h4>
        {cheaper && <span className="inline-flex items-center gap-1 text-xs font-bold text-good"><Check className="size-3.5" aria-hidden /> Cheaper</span>}
      </div>
      <p className="num mt-2 text-2xl font-extrabold">{inr(r.total)}</p>
      <p className="text-xs text-muted-foreground">tax for the year, with cess</p>
      <dl className="mt-3 space-y-1 text-xs">
        <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Standard deduction</dt><dd className="num">{inr(r.standard_deduction)}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Other deductions</dt><dd className="num">{inr(r.deductions_total)}</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Taxable income</dt><dd className="num font-semibold">{inr(r.taxable)}</dd></div>
        {r.rebate > 0 && <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Rebate</dt><dd className="num">−{inr(r.rebate)}</dd></div>}
      </dl>
    </div>
  );
}

/** Both regimes side by side from the calculator. Deductions can be added here; the question is then asked again. */
export function TaxView({ card, onAsk }: { card: TaxCard; onAsk: (text: string) => void }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>(() => Object.fromEntries(DEDUCTIONS.map(([k]) => [k, card.deductions[k] ? String(card.deductions[k]) : ""])));
  const save = useAnswer(() => {
    setOpen(false);
    onAsk(card.then);
  });
  const answers = Object.fromEntries(DEDUCTIONS.map(([k]) => [k, Number((f[k] || "0").replace(/,/g, ""))]));
  const valid = Object.values(answers).every((v) => Number.isFinite(v) && v >= 0);
  return (
    <CardShell eyebrow={`Income tax · FY ${card.financial_year}`} title={<>On <span className="num">{inr(card.gross)}</span> a year</>} aside={<Pill>Estimate</Pill>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Regime r={card.new} cheaper={card.better === "new"} />
        <Regime r={card.old} cheaper={card.better === "old"} />
      </div>
      <p className="mt-3 text-sm">
        {card.better === "same" ? "Both regimes cost the same." : <>The {card[card.better].label.toLowerCase()} saves <strong className="num">{inr(card.saving)}</strong> a year.</>}
      </p>
      <button className="mt-3 text-sm font-semibold text-primary underline-offset-4 hover:underline" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {card.deductions_known ? "Change my deductions" : "Add my deductions for an exact comparison"}
      </button>
      {open && (
        <form className="mt-3 grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); if (valid) save.mutate(answers); }}>
          {DEDUCTIONS.map(([k, label]) => (
            <label key={k} htmlFor={`${id}-${k}`} className="text-sm font-medium">
              {label}
              <input id={`${id}-${k}`} inputMode="decimal" placeholder="₹ a year" className={INPUT} value={f[k]} onChange={(e) => setF((x) => ({ ...x, [k]: e.target.value }))} />
            </label>
          ))}
          <button disabled={!valid || save.isPending} className="rounded-full bg-primary py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-40 sm:col-span-2">
            {save.isPending ? "Saving…" : "Save and recalculate"}
          </button>
        </form>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        Estimated, not tax advice. {card.source.replace(/, as of .*/, "")}, as of {date(card.as_of)}. The old regime's caps are applied for you.
      </p>
    </CardShell>
  );
}

/** One plan at a time: when it is re-made, this says what moved. */
export function PlanChangeView({ card }: { card: PlanChangeCard }) {
  return (
    <div role="note" className="flex gap-2.5 rounded-xl bg-info-soft px-3.5 py-3 text-sm">
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <p className="font-semibold">Since your last plan</p>
        <ul className="num mt-0.5 space-y-0.5 whitespace-normal">
          {card.lines.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </div>
    </div>
  );
}
