import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { inr } from "@/lib/format";
import type { Instrument } from "@/lib/types";
import { cn } from "@/lib/utils";

export function instrumentLabel(i: Instrument) {
  if (i.kind === "mf") return i.name;
  return `${i.symbol} · ${i.name}`;
}

export function InstrumentSearch({ kind, onPick, autoFocus }: { kind: "listed" | "mf"; onPick: (i: Instrument) => void; autoFocus?: boolean }) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);
  const r = useQuery({
    queryKey: ["search", kind, debounced],
    queryFn: () => api.get<Instrument[]>(`/api/instruments/search?kind=${kind}&q=${encodeURIComponent(debounced)}`),
    enabled: debounced.length >= 2,
  });
  return (
    <div>
      <label className="flex items-center gap-2 rounded-xl border bg-card px-3 focus-within:ring-2 focus-within:ring-ring">
        <Search className="size-4 text-muted-foreground" aria-hidden />
        <span className="sr-only">{kind === "mf" ? "Search mutual fund schemes" : "Search stocks by name or NSE/BSE symbol"}</span>
        <input autoFocus={autoFocus} value={q} onChange={(e) => setQ(e.target.value)} className="w-full bg-transparent py-2.5 outline-none"
          placeholder={kind === "mf" ? "Scheme name, e.g. Parag Parikh Flexi Cap" : "Symbol or company, e.g. RELIANCE"} />
      </label>
      {debounced.length >= 2 && (
        <ul className="mt-2 max-h-72 overflow-y-auto rounded-xl border" role="listbox" aria-label="Results">
          {r.isLoading && <li className="px-3 py-2 text-sm text-muted-foreground">Searching…</li>}
          {r.data?.length === 0 && <li className="px-3 py-2 text-sm text-muted-foreground">No matches.</li>}
          {r.data?.map((i) => (
            <li key={i.id}>
              <button role="option" aria-selected={false} onClick={() => onPick(i)} className="w-full px-3 py-2 text-left text-sm hover:bg-surface-2">
                <span className="font-semibold">{i.kind === "mf" ? i.name : i.symbol}</span>
                <span className="block text-xs text-muted-foreground">
                  {i.kind === "mf" ? [i.amc, i.category].filter(Boolean).join(" · ") : `${i.name} · ${i.exchange}${i.kind !== "stock" ? ` · ${i.kind.toUpperCase()}` : ""}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AddTransactionDialog({ open, onOpenChange, kind, preset }: { open: boolean; onOpenChange: (o: boolean) => void; kind: "listed" | "mf"; preset?: Instrument }) {
  const qc = useQueryClient();
  const [inst, setInst] = useState<Instrument | null>(preset ?? null);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [d, setD] = useState(new Date().toISOString().slice(0, 10));
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [charges, setCharges] = useState("");
  useEffect(() => {
    if (open) setInst(preset ?? null);
  }, [open, preset]);
  const m = useMutation({
    mutationFn: () => api.post("/api/transactions", { instrument_id: inst!.id, kind: side, trade_date: d, quantity: Number(qty), price: Number(price), charges: Number(charges || 0) }),
    onSuccess: () => {
      toast.success(`${side === "buy" ? "Purchase" : "Sale"} saved`);
      qc.invalidateQueries();
      onOpenChange(false);
      setQty("");
      setPrice("");
      setCharges("");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const unit = kind === "mf" ? "Units" : "Shares";
  const input = "w-full rounded-xl border bg-card px-3 py-2.5 outline-none focus:ring-2 focus:ring-ring";
  const total = Number(qty) * Number(price) + (side === "buy" ? 1 : -1) * Number(charges || 0);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg rounded-2xl">
        <DialogTitle>{kind === "mf" ? "Add a mutual fund transaction" : "Add a stock transaction"}</DialogTitle>
        <DialogDescription>Enter it as it appears in your contract note or statement. FinAdvisor never places trades.</DialogDescription>
        {!inst ? (
          <InstrumentSearch kind={kind} onPick={setInst} autoFocus />
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              m.mutate();
            }}
          >
            <div className="flex items-start justify-between gap-3 rounded-xl bg-surface-2 px-3 py-2.5">
              <div className="text-sm">
                <p className="font-semibold">{instrumentLabel(inst)}</p>
                <p className="text-xs text-muted-foreground">{inst.kind === "mf" ? `AMFI code ${inst.scheme_code}` : `${inst.exchange} · ISIN ${inst.isin}`}</p>
              </div>
              {!preset && <button type="button" className="text-sm font-semibold text-brand" onClick={() => setInst(null)}>Change</button>}
            </div>
            <div role="radiogroup" aria-label="Type" className="inline-flex rounded-full bg-surface-2 p-1">
              {(["buy", "sell"] as const).map((x) => (
                <button key={x} type="button" role="radio" aria-checked={side === x} onClick={() => setSide(x)}
                  className={cn("rounded-full px-4 py-1.5 text-sm font-semibold capitalize", side === x ? "bg-card shadow-sm" : "text-muted-foreground")}>
                  {kind === "mf" ? (x === "buy" ? "Purchase" : "Redemption") : x}
                </button>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm font-medium">Date<input type="date" required max={new Date().toISOString().slice(0, 10)} className={input + " mt-1"} value={d} onChange={(e) => setD(e.target.value)} /></label>
              <label className="text-sm font-medium">{unit}<input required inputMode="decimal" className={input + " num mt-1"} value={qty} onChange={(e) => setQty(e.target.value.replace(/[^\d.]/g, ""))} /></label>
              <label className="text-sm font-medium">{kind === "mf" ? "NAV (₹ per unit)" : "Price (₹ per share)"}<input required inputMode="decimal" className={input + " num mt-1"} value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ""))} /></label>
              <label className="text-sm font-medium">Charges (₹, optional)<input inputMode="decimal" className={input + " num mt-1"} value={charges} onChange={(e) => setCharges(e.target.value.replace(/[^\d.]/g, ""))} /></label>
            </div>
            {total > 0 && <p className="num text-sm text-muted-foreground">Total: <strong className="text-foreground">{inr(total, 2)}</strong></p>}
            <button disabled={m.isPending} className="w-full rounded-full bg-primary py-2.5 font-semibold text-primary-foreground disabled:opacity-60">
              {m.isPending ? "Saving…" : "Save"}
            </button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
