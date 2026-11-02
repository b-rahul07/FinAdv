import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileUp, Lock } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { InfoNote } from "@/components/common";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { api, ApiError, getToken } from "@/lib/api";
import { inr, num } from "@/lib/format";
import type { Instrument } from "@/lib/types";
import { cn } from "@/lib/utils";

type Item = {
  key: string;
  kind: string;
  name: string;
  folio_last4: string | null;
  units: number;
  value: number | null;
  valuation_date: string | null;
  cost: number | null;
  transactions: unknown[];
  needs_cost: boolean;
  instrument: Instrument | null;
  tracked_units: number;
  difference: number;
};
type Preview = { id: string; file_type: string; cas_type: string; period_from: string | null; period_to: string | null; items: Item[]; warnings: string[] };
type Choice = { include: boolean; avg_price?: string; date?: string };

const STEPS = ["Upload", "Review", "Done"];

export function CasImportDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const reset = () => {
    setStep(0);
    setFile(null);
    setPassword("");
    setPreview(null);
    setChoices({});
    setResult(null);
  };

  const parse = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append("file", file!);
      fd.append("password", password);
      const token = await getToken();
      const r = await fetch(api.base + "/api/cas/preview", { method: "POST", body: fd, headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!r.ok) throw new ApiError(r.status, (await r.json().catch(() => ({}))).detail ?? "Could not read the statement.");
      return (await r.json()) as Preview;
    },
    onSuccess: (p) => {
      setPassword("");
      setPreview(p);
      setChoices(Object.fromEntries(p.items.map((i) => [i.key, { include: !!i.instrument }])));
      setStep(1);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const doImport = useMutation({
    mutationFn: () =>
      api.post<Record<string, unknown>>(`/api/cas/${preview!.id}/import`, {
        choices: Object.entries(choices).map(([key, c]) => ({ key, include: c.include, avg_price: c.avg_price ? Number(c.avg_price) : null, date: c.date || null })),
      }),
    onSuccess: (r) => {
      setResult(r);
      setStep(2);
      qc.invalidateQueries();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const input = "w-full rounded-lg border bg-card px-2 py-1.5 text-sm";
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) reset(); }}>
      <DialogContent className="max-h-[90dvh] max-w-3xl overflow-y-auto rounded-2xl">
        <div className="flex gap-1" aria-hidden>
          {STEPS.map((_, i) => <span key={i} className={cn("h-1 flex-1 rounded-full", i <= step ? "bg-primary" : "bg-surface-2")} />)}
        </div>
        <p className="eyebrow">{String(step + 1).padStart(2, "0")} / {STEPS[step]}</p>
        {step === 0 && (
          <>
            <DialogTitle className="text-xl">Import a Consolidated Account Statement</DialogTitle>
            <DialogDescription>CAMS or KFintech (mutual fund transactions), or NSDL / CDSL (demat holdings). Use the original PDF you received by email.</DialogDescription>
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); parse.mutate(); }}>
              <label className="flex cursor-pointer flex-col items-center gap-2 rounded-2xl border border-dashed px-6 py-8 text-center hover:bg-surface-2/50">
                <FileUp className="size-6 text-muted-foreground" aria-hidden />
                <span className="text-sm font-semibold">{file ? file.name : "Choose the PDF"}</span>
                <input type="file" accept="application/pdf" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </label>
              <label className="block text-sm font-medium">
                Statement password
                <input type="password" required autoComplete="off" className="mt-1 w-full rounded-xl border bg-card px-3 py-2.5" value={password} onChange={(e) => setPassword(e.target.value)} />
              </label>
              <InfoNote><span className="inline-flex items-center gap-1 font-semibold"><Lock className="size-3.5" aria-hidden /> Never stored.</span> The PDF is read in memory and discarded; the password is used once to open it. Only the holdings you choose to import are saved, with folio numbers reduced to the last 4 digits.</InfoNote>
              <button disabled={!file || !password || parse.isPending} className="w-full rounded-full bg-primary py-2.5 font-semibold text-primary-foreground disabled:opacity-50">
                {parse.isPending ? "Reading statement…" : "Read statement"}
              </button>
            </form>
          </>
        )}
        {step === 1 && preview && (
          <>
            <DialogTitle className="text-xl">Review before importing</DialogTitle>
            <DialogDescription>
              {preview.file_type} {preview.cas_type.toLowerCase()} statement{preview.period_to ? `, ${preview.period_from} to ${preview.period_to}` : ""}. A CAS is a month-end snapshot; daily prices still come from AMFI and the exchanges.
            </DialogDescription>
            <ul className="divide-y rounded-xl border">
              {preview.items.map((it) => {
                const c = choices[it.key] ?? { include: false };
                const set = (patch: Partial<Choice>) => setChoices((x) => ({ ...x, [it.key]: { ...c, ...patch } }));
                return (
                  <li key={it.key} className="space-y-2 p-3">
                    <label className="flex items-start gap-3">
                      <input type="checkbox" className="mt-1 size-4" checked={c.include} disabled={!it.instrument} onChange={(e) => set({ include: e.target.checked })} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold">{it.name}</span>
                        <span className="block text-xs text-muted-foreground">
                          {it.folio_last4 ? `ending ${it.folio_last4} · ` : ""}{num(it.units, it.kind === "mf" ? 3 : 0)} {it.kind === "mf" ? "units" : "shares"}
                          {it.value != null ? ` · ${inr(it.value)} on ${it.valuation_date}` : ""}
                          {it.transactions.length ? ` · ${it.transactions.length} transactions` : ""}
                        </span>
                        {!it.instrument && <span className="block text-xs font-semibold text-warn">Not matched to a listed stock or AMFI scheme; skipped.</span>}
                        {it.instrument && it.difference !== 0 && it.tracked_units > 0 && (
                          <span className="block text-xs text-warn">FinAdvisor already tracks {num(it.tracked_units, 3)}; the statement says {num(it.units, 3)}. Duplicates are skipped on import.</span>
                        )}
                      </span>
                    </label>
                    {c.include && it.needs_cost && (
                      <div className="ml-7 grid gap-2 sm:grid-cols-2">
                        <label className="text-xs font-medium">Average cost per {it.kind === "mf" ? "unit" : "share"} (₹)
                          <input inputMode="decimal" className={input} placeholder={it.cost ? String((it.cost / it.units).toFixed(2)) : ""} value={c.avg_price ?? ""} onChange={(e) => set({ avg_price: e.target.value })} />
                        </label>
                        <label className="text-xs font-medium">Bought on (or first purchase)
                          <input type="date" className={input} value={c.date ?? ""} onChange={(e) => set({ date: e.target.value })} />
                        </label>
                        <p className="text-xs text-muted-foreground sm:col-span-2">This statement has holdings but no transactions, so cost and date come from you. They drive gains, holding period and XIRR.</p>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
            {preview.warnings.length > 0 && <InfoNote tone="warn">Parser notes: {preview.warnings.join("; ")}</InfoNote>}
            <div className="flex justify-between gap-2">
              <button className="rounded-full px-4 py-2 text-sm font-semibold" onClick={reset}>Start over</button>
              <button disabled={doImport.isPending || !Object.values(choices).some((c) => c.include)} onClick={() => doImport.mutate()} className="rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-50">
                {doImport.isPending ? "Importing…" : "Import selected"}
              </button>
            </div>
          </>
        )}
        {step === 2 && result && (
          <>
            <DialogTitle className="text-xl">Imported</DialogTitle>
            <p className="text-sm">{String(result.transactions_added)} transactions added{Number(result.duplicates_skipped) ? `, ${result.duplicates_skipped} duplicates skipped` : ""}. Price history is loading in the background.</p>
            <button className="rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground" onClick={() => { onOpenChange(false); reset(); }}>Done</button>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
