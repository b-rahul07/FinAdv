import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { Debt, Goal, Profile, ProfileView } from "@/lib/types";
import { cn } from "@/lib/utils";

export const EMPTY_PROFILE: Profile = {
  age: null,
  take_home_monthly: 0,
  expenses_monthly: 0,
  liquid_savings: 0,
  debts: [],
  card_dues_paid_in_full: true,
  dependants: 0,
  life_cover: 0,
  health_cover: 0,
  goals: [],
  salaried: true,
  experience: "none",
  gl_answers: {},
  wishes: [],
};

const DEBT_KINDS = [
  ["home", "Home loan"],
  ["car", "Car loan"],
  ["two_wheeler", "Two-wheeler loan"],
  ["personal", "Personal loan"],
  ["education", "Education loan"],
  ["bnpl", "BNPL"],
  ["credit_card", "Credit-card dues"],
  ["gold", "Gold loan"],
  ["other", "Other"],
] as const;

const GOAL_KINDS = ["retirement", "home", "education", "marriage", "vehicle", "travel", "wealth", "other"];

export function MoneyInput({ value, onChange, label, hint, highlight }: { value: number; onChange: (n: number) => void; label: string; hint?: string; highlight?: boolean }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
        {highlight && <span className="ml-2 rounded-full bg-info-soft px-2 py-0.5 text-[11px] font-bold">suggested</span>}
      </label>
      <div className={cn("flex items-center rounded-xl border bg-card px-3 focus-within:ring-2 focus-within:ring-ring", highlight && "border-brand")}>
        <span className="text-muted-foreground" aria-hidden>
          ₹
        </span>
        <input
          id={id}
          inputMode="numeric"
          className="num w-full bg-transparent px-2 py-2.5 outline-none"
          value={value ? num(value) : ""}
          placeholder="0"
          onChange={(e) => onChange(Number(e.target.value.replace(/[^\d]/g, "")) || 0)}
          aria-describedby={hint ? id + "-h" : undefined}
        />
      </div>
      {hint && (
        <p id={id + "-h"} className="mt-1 text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

function NumberField({ value, onChange, label, min = 0, max = 100, step = 1, suffix }: { value: number | null; onChange: (n: number) => void; label: string; min?: number; max?: number; step?: number; suffix?: string }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      <div className="flex items-center rounded-xl border bg-card px-3 focus-within:ring-2 focus-within:ring-ring">
        <input id={id} type="number" min={min} max={max} step={step} className="num w-full bg-transparent py-2.5 outline-none" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))} />
        {suffix && <span className="text-sm text-muted-foreground">{suffix}</span>}
      </div>
    </div>
  );
}

export function ProfileForm({ initial, changed = [], onSaved, compact = false }: { initial: Profile; changed?: string[]; onSaved?: (v: ProfileView) => void; compact?: boolean }) {
  const qc = useQueryClient();
  const [p, setP] = useState<Profile>({ ...EMPTY_PROFILE, ...initial });
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setP((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => api.put<ProfileView>("/api/profile", { data: p, sources: Object.fromEntries(changed.map((c) => [c, "llm_confirmed"])) }),
    onSuccess: (v) => {
      qc.setQueryData(["profile"], v);
      qc.invalidateQueries({ queryKey: ["profile"] });
      toast.success(`Profile saved (version ${v.version})`);
      onSaved?.(v);
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const hl = (k: string) => changed.includes(k);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
      className="space-y-6"
    >
      <fieldset className={cn("grid gap-4", compact ? "sm:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-3")}>
        <legend className="eyebrow mb-3">Money in and out</legend>
        <MoneyInput label="Take-home pay per month" value={p.take_home_monthly} onChange={(n) => set("take_home_monthly", n)} highlight={hl("take_home_monthly")} hint="After tax and PF, what reaches your bank" />
        <MoneyInput label="Expenses per month" value={p.expenses_monthly} onChange={(n) => set("expenses_monthly", n)} highlight={hl("expenses_monthly")} hint="Rent, food, bills, transport; not EMIs" />
        <MoneyInput label="Emergency savings" value={p.liquid_savings} onChange={(n) => set("liquid_savings", n)} highlight={hl("liquid_savings")} hint="Savings account, FDs, liquid funds you could use in a week" />
      </fieldset>

      <fieldset className={cn("grid gap-4", compact ? "sm:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-3")}>
        <legend className="eyebrow mb-3">Family and protection</legend>
        <NumberField label="People who depend on your income" value={p.dependants} onChange={(n) => set("dependants", Math.max(0, Math.round(n) || 0))} max={20} />
        <MoneyInput label="Term life cover" value={p.life_cover} onChange={(n) => set("life_cover", n)} highlight={hl("life_cover")} />
        <MoneyInput label="Health cover" value={p.health_cover} onChange={(n) => set("health_cover", n)} highlight={hl("health_cover")} hint="Your own or family floater, not only your employer's" />
        <NumberField label="Age" value={p.age} onChange={(n) => set("age", n || null)} min={16} max={100} />
      </fieldset>

      <fieldset>
        <legend className="eyebrow mb-3">Loans, EMIs and cards</legend>
        <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border px-4 py-3">
          <label htmlFor="cardpaid" className="text-sm font-medium">
            I pay my full credit-card bill every month
          </label>
          <Switch id="cardpaid" checked={p.card_dues_paid_in_full} onCheckedChange={(v) => set("card_dues_paid_in_full", v)} />
        </div>
        <ul className="space-y-3">
          {p.debts.map((d, i) => (
            <li key={i} className="grid items-end gap-3 rounded-xl border p-3 sm:grid-cols-[1.2fr_1fr_1fr_0.7fr_auto]">
              <div>
                <label className="mb-1 block text-sm font-medium" htmlFor={`dk${i}`}>
                  Type
                </label>
                <select id={`dk${i}`} className="w-full rounded-xl border bg-card px-3 py-2.5" value={d.kind} onChange={(e) => set("debts", p.debts.map((x, j) => (j === i ? { ...x, kind: e.target.value } : x)))}>
                  {DEBT_KINDS.map(([k, l]) => (
                    <option key={k} value={k}>
                      {l}
                    </option>
                  ))}
                </select>
              </div>
              <MoneyInput label="Outstanding" value={d.outstanding} onChange={(n) => set("debts", p.debts.map((x, j) => (j === i ? { ...x, outstanding: n } : x)))} />
              <MoneyInput label="EMI per month" value={d.emi_monthly} onChange={(n) => set("debts", p.debts.map((x, j) => (j === i ? { ...x, emi_monthly: n } : x)))} />
              <NumberField label="Rate" suffix="% a year" step={0.1} value={d.rate_pa} onChange={(n) => set("debts", p.debts.map((x, j) => (j === i ? { ...x, rate_pa: Number.isNaN(n) ? null : n } : x)))} />
              <Button type="button" variant="ghost" size="icon" aria-label="Remove loan" onClick={() => set("debts", p.debts.filter((_, j) => j !== i))}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
        <Button type="button" variant="outline" className="mt-3 rounded-full" onClick={() => set("debts", [...p.debts, { kind: "personal", outstanding: 0, emi_monthly: 0, rate_pa: null } as Debt])}>
          <Plus /> Add a loan or EMI
        </Button>
      </fieldset>

      <fieldset>
        <legend className="eyebrow mb-3">Goals</legend>
        <ul className="space-y-3">
          {p.goals.map((g, i) => (
            <li key={g.id} className="grid items-end gap-3 rounded-xl border p-3 sm:grid-cols-[1.4fr_1fr_1fr_0.8fr_auto]">
              <div>
                <label className="mb-1 block text-sm font-medium" htmlFor={`gn${i}`}>
                  Goal
                </label>
                <input id={`gn${i}`} className="w-full rounded-xl border bg-card px-3 py-2.5" value={g.name} onChange={(e) => set("goals", p.goals.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <select aria-label="Goal type" className="mt-2 w-full rounded-xl border bg-card px-3 py-2 text-sm" value={g.kind} onChange={(e) => set("goals", p.goals.map((x, j) => (j === i ? { ...x, kind: e.target.value } : x)))}>
                  {GOAL_KINDS.map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </div>
              <MoneyInput label="Cost in today's money" value={g.target_today} onChange={(n) => set("goals", p.goals.map((x, j) => (j === i ? { ...x, target_today: n } : x)))} />
              <MoneyInput label="Saved so far" value={g.saved_so_far} onChange={(n) => set("goals", p.goals.map((x, j) => (j === i ? { ...x, saved_so_far: n } : x)))} />
              <NumberField label="In" suffix="years" step={0.5} min={0.5} max={60} value={g.horizon_years} onChange={(n) => set("goals", p.goals.map((x, j) => (j === i ? { ...x, horizon_years: Number.isNaN(n) ? 0 : n } : x)))} />
              <Button type="button" variant="ghost" size="icon" aria-label="Remove goal" onClick={() => set("goals", p.goals.filter((_, j) => j !== i))}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
        <Button
          type="button"
          variant="outline"
          className="mt-3 rounded-full"
          onClick={() => set("goals", [...p.goals, { id: `g${Date.now().toString(36)}`, name: "", kind: "other", target_today: 0, horizon_years: 5, saved_so_far: 0 } as Goal])}
        >
          <Plus /> Add a goal
        </Button>
      </fieldset>

      <fieldset>
        <legend className="eyebrow mb-3">Investing experience</legend>
        <div role="radiogroup" className="flex flex-wrap gap-2">
          {(["none", "beginner", "intermediate", "advanced"] as const).map((x) => (
            <button
              type="button"
              role="radio"
              aria-checked={p.experience === x}
              key={x}
              onClick={() => set("experience", x)}
              className={cn("rounded-full border px-4 py-2 text-sm font-medium", p.experience === x ? "border-primary bg-primary text-primary-foreground" : "hover:bg-surface-2")}
            >
              {x === "none" ? "Never invested" : x[0].toUpperCase() + x.slice(1)}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-wrap items-center gap-3 border-t pt-4">
        <Button type="submit" className="rounded-full px-6" disabled={save.isPending || p.goals.some((g) => !g.name || !g.target_today || !(g.horizon_years > 0))}>
          {save.isPending ? "Saving…" : "Confirm profile"}
        </Button>
        <p className="text-xs text-muted-foreground">FinAdvisor only uses facts you confirm. Each confirmation is saved as a new version.</p>
      </div>
    </form>
  );
}
