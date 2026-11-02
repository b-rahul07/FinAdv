import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { EmptyState, InfoNote, Pill, Section, Skeleton } from "@/components/common";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { CLASS_META } from "@/features/charts/Charts";
import { api } from "@/lib/api";
import { date, inr } from "@/lib/format";

type Asset = { id: string; kind: string; name: string; asset_class: string; account_last4: string | null; data: Record<string, any>; value: number | null; source: string | null; as_of: string | null; self_reported: boolean; note: string | null; matured?: boolean };
type Loan = { id: string; kind: string; lender: string; outstanding: number; rate_pa: number | null; emi_monthly: number; end_date: string | null; as_of: string; account_last4: string | null };
type Cover = { id: string; kind: string; insurer: string; sum_assured: number; premium_yearly: number | null; renewal_date: string | null; employer_provided: boolean };
type Others = { assets: Asset[]; liabilities: Loan[]; insurance: Cover[]; gold_reference: { rate_per_gram_999: number; as_of: string; source: string } | null };

const KINDS: Record<string, { label: string; fields: [string, string, string?][] }> = {
  fd: { label: "Fixed deposit", fields: [["principal", "Principal (₹)"], ["rate_pa", "Interest rate (% a year)"], ["start", "Start date", "date"], ["maturity", "Maturity date", "date"]] },
  rd: { label: "Recurring deposit", fields: [["instalment", "Monthly instalment (₹)"], ["rate_pa", "Interest rate (% a year)"], ["start", "Start date", "date"], ["maturity", "Maturity date", "date"]] },
  savings: { label: "Savings account", fields: [["balance", "Balance (₹)"], ["as_of", "As of", "date"]] },
  cash: { label: "Cash", fields: [["balance", "Amount (₹)"], ["as_of", "As of", "date"]] },
  epf: { label: "EPF", fields: [["balance", "Balance (₹)"], ["as_of", "As of (from your passbook)", "date"]] },
  ppf: { label: "PPF", fields: [["balance", "Balance (₹)"], ["as_of", "As of", "date"]] },
  nps: { label: "NPS", fields: [["balance", "Value (₹)"], ["as_of", "As of", "date"]] },
  ssy: { label: "Sukanya Samriddhi", fields: [["balance", "Balance (₹)"], ["as_of", "As of", "date"]] },
  gold_physical: { label: "Physical gold", fields: [["grams", "Weight (grams)"], ["purity", "Purity (999, 995, 916, 750, 585)"]] },
  gold_digital: { label: "Digital gold", fields: [["grams", "Grams"]] },
  silver_physical: { label: "Physical silver", fields: [["grams", "Weight (grams)"], ["purity", "Purity (999 etc.)"], ["rate_per_gram", "Your rate per gram (₹)"], ["rate_date", "Rate date", "date"]] },
  property: { label: "Property", fields: [["balance", "Your estimate of value (₹)"], ["as_of", "As of", "date"]] },
  vehicle: { label: "Vehicle", fields: [["balance", "Your estimate of value (₹)"], ["as_of", "As of", "date"]] },
  other: { label: "Other", fields: [["balance", "Value (₹)"], ["as_of", "As of", "date"]] },
};
const LOAN_KINDS = ["home", "car", "two_wheeler", "personal", "education", "bnpl", "credit_card", "gold", "other"];

export function OthersTab() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["others"], queryFn: () => api.get<Others>("/api/others") });
  const [dialog, setDialog] = useState<null | "asset" | "loan" | "cover">(null);
  const del = useMutation({ mutationFn: (p: string) => api.del(p), onSuccess: () => qc.invalidateQueries() });
  if (!q.data) return <Skeleton className="h-64" />;
  const d = q.data;
  const btn = "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2";
  return (
    <div className="space-y-4">
      <Section eyebrow="Deposits, retirement, cash, gold, property" title="Other assets" action={<button className={btn} onClick={() => setDialog("asset")}><Plus className="size-4" aria-hidden /> Add</button>}>
        {d.assets.length === 0 ? <EmptyState title="Nothing added yet" body="FDs, EPF/PPF/NPS, savings, physical gold and property make your net worth and emergency-fund check complete." /> : (
          <ul className="divide-y">
            {d.assets.map((a) => (
              <li key={a.id} className="flex items-center gap-3 py-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-surface-2"><span className="size-3 rounded-full" style={{ background: `var(--series-${CLASS_META[a.asset_class]?.slot ?? 8})` }} aria-hidden /></span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{a.name} {a.self_reported && <Pill className="ml-1">self-reported</Pill>} {a.matured && <Pill className="ml-1">matured</Pill>}</p>
                  <p className="truncate text-xs text-muted-foreground">{KINDS[a.kind]?.label}{a.account_last4 ? ` · ending ${a.account_last4}` : ""} · {a.note ?? `${a.source}${a.as_of ? `, as of ${date(a.as_of)}` : ""}`}</p>
                </div>
                <span className="num text-right text-sm font-semibold">{a.value != null ? inr(a.value) : "—"}</span>
                <button aria-label={`Delete ${a.name}`} className="rounded-lg p-1.5 text-muted-foreground hover:bg-surface-2" onClick={() => del.mutate(`/api/others/assets/${a.id}`)}><Trash2 className="size-4" /></button>
              </li>
            ))}
          </ul>
        )}
        {d.gold_reference && <p className="mt-3 text-xs text-muted-foreground">Gold valued at {inr(d.gold_reference.rate_per_gram_999)}/g (999), {d.gold_reference.source}, as of {date(d.gold_reference.as_of)}. Not an IBJA rate.</p>}
      </Section>

      <Section eyebrow="Counted against net worth" title="Loans and dues" action={<button className={btn} onClick={() => setDialog("loan")}><Plus className="size-4" aria-hidden /> Add</button>}>
        {d.liabilities.length === 0 ? <p className="text-sm text-muted-foreground">No loans, BNPL or card dues added.</p> : (
          <ul className="divide-y">
            {d.liabilities.map((l) => (
              <li key={l.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <div><p className="font-semibold capitalize">{l.kind.replace("_", " ")}{l.lender ? ` · ${l.lender}` : ""}</p><p className="text-xs text-muted-foreground">{l.rate_pa != null ? `${l.rate_pa}% a year · ` : ""}EMI {inr(l.emi_monthly)}{l.end_date ? ` · ends ${date(l.end_date)}` : ""}{l.account_last4 ? ` · ending ${l.account_last4}` : ""} · as of {date(l.as_of)}</p></div>
                <span className="flex items-center gap-2"><span className="num font-semibold">−{inr(l.outstanding)}</span><button aria-label="Delete loan" className="rounded-lg p-1.5 text-muted-foreground hover:bg-surface-2" onClick={() => del.mutate(`/api/others/liabilities/${l.id}`)}><Trash2 className="size-4" /></button></span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section eyebrow="Used by the health check, not net worth" title="Insurance" action={<button className={btn} onClick={() => setDialog("cover")}><Plus className="size-4" aria-hidden /> Add</button>}>
        {d.insurance.length === 0 ? <p className="text-sm text-muted-foreground">No term or health cover added.</p> : (
          <ul className="divide-y">
            {d.insurance.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <div><p className="font-semibold">{c.kind === "term" ? "Term life" : "Health"}{c.insurer ? ` · ${c.insurer}` : ""}{c.employer_provided && <Pill className="ml-2">employer</Pill>}</p><p className="text-xs text-muted-foreground">{c.premium_yearly ? `${inr(c.premium_yearly)} a year · ` : ""}{c.renewal_date ? `renews ${date(c.renewal_date)}` : ""}</p></div>
                <span className="flex items-center gap-2"><span className="num font-semibold">{inr(c.sum_assured)} cover</span><button aria-label="Delete policy" className="rounded-lg p-1.5 text-muted-foreground hover:bg-surface-2" onClick={() => del.mutate(`/api/others/insurance/${c.id}`)}><Trash2 className="size-4" /></button></span>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <InfoNote>Loan, folio and account numbers: enter only the last 4 digits. FinAdvisor never stores full numbers.</InfoNote>
      <AddOther kind={dialog} onClose={() => setDialog(null)} />
    </div>
  );
}

function AddOther({ kind, onClose }: { kind: null | "asset" | "loan" | "cover"; onClose: () => void }) {
  const qc = useQueryClient();
  const [assetKind, setAssetKind] = useState("fd");
  const [f, setF] = useState<Record<string, string>>({});
  const set = (k: string, v: string) => setF((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => {
      if (kind === "asset") {
        const data = Object.fromEntries(KINDS[assetKind].fields.map(([k, , t]) => [k, t === "date" ? f[k] : f[k] ? Number(f[k]) : null]));
        return api.post("/api/others/assets", { kind: assetKind, name: f.name || KINDS[assetKind].label, data, account_last4: f.last4 || null });
      }
      if (kind === "loan")
        return api.post("/api/others/liabilities", { kind: f.kind || "personal", lender: f.lender || "", outstanding: Number(f.outstanding || 0), rate_pa: f.rate ? Number(f.rate) : null, emi_monthly: Number(f.emi || 0), end_date: f.end || null, account_last4: f.last4 || null });
      return api.post("/api/others/insurance", { kind: f.kind || "term", insurer: f.insurer || "", sum_assured: Number(f.sum || 0), premium_yearly: f.premium ? Number(f.premium) : null, renewal_date: f.renewal || null, employer_provided: f.employer === "yes" });
    },
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Saved");
      setF({});
      onClose();
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const input = "mt-1 w-full rounded-xl border bg-card px-3 py-2.5";
  const field = (k: string, label: string, type = "text") => (
    <label key={k} className="text-sm font-medium">{label}<input type={type} inputMode={type === "text" ? "decimal" : undefined} className={input} value={f[k] ?? ""} onChange={(e) => set(k, e.target.value)} /></label>
  );
  return (
    <Dialog open={!!kind} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg rounded-2xl">
        <DialogTitle>{kind === "asset" ? "Add an asset" : kind === "loan" ? "Add a loan or due" : "Add insurance"}</DialogTitle>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          {kind === "asset" && (
            <>
              <label className="text-sm font-medium sm:col-span-2">Type
                <select className={input} value={assetKind} onChange={(e) => setAssetKind(e.target.value)}>
                  {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
              </label>
              <label className="text-sm font-medium sm:col-span-2">Name<input className={input} placeholder={KINDS[assetKind].label} value={f.name ?? ""} onChange={(e) => set("name", e.target.value)} /></label>
              {KINDS[assetKind].fields.map(([k, label, t]) => field(k, label, t ?? "text"))}
              {["fd", "rd", "savings", "epf", "ppf", "nps", "ssy"].includes(assetKind) && field("last4", "Account number, last 4 digits")}
            </>
          )}
          {kind === "loan" && (
            <>
              <label className="text-sm font-medium sm:col-span-2">Type
                <select className={input} value={f.kind ?? "personal"} onChange={(e) => set("kind", e.target.value)}>
                  {LOAN_KINDS.map((k) => <option key={k} value={k}>{k.replace("_", " ")}</option>)}
                </select>
              </label>
              {field("lender", "Lender")}{field("outstanding", "Outstanding (₹)")}{field("rate", "Interest rate (% a year)")}{field("emi", "EMI per month (₹)")}{field("end", "End date", "date")}{field("last4", "Loan account, last 4 digits")}
            </>
          )}
          {kind === "cover" && (
            <>
              <label className="text-sm font-medium">Type
                <select className={input} value={f.kind ?? "term"} onChange={(e) => set("kind", e.target.value)}><option value="term">Term life</option><option value="health">Health</option></select>
              </label>
              <label className="text-sm font-medium">Through employer?
                <select className={input} value={f.employer ?? "no"} onChange={(e) => set("employer", e.target.value)}><option value="no">No, my own</option><option value="yes">Yes</option></select>
              </label>
              {field("insurer", "Insurer")}{field("sum", "Sum assured (₹)")}{field("premium", "Premium per year (₹)")}{field("renewal", "Renewal date", "date")}
            </>
          )}
          <button disabled={save.isPending} className="rounded-full bg-primary py-2.5 font-semibold text-primary-foreground sm:col-span-2">{save.isPending ? "Saving…" : "Save"}</button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
