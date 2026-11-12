import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ErrorState, Section, Skeleton } from "@/components/common";
import { cap, HealthCheckView } from "@/features/chat/cards/AdviceCards";
import { ProfileForm } from "@/features/profile/ProfileForm";
import { Questionnaire } from "@/features/profile/Questionnaire";
import { api } from "@/lib/api";
import { inr } from "@/lib/format";
import type { Profile, ProfileView } from "@/lib/types";

type Proposal = { proposed: Profile; changed: string[] };

const FACT_LABEL: Record<string, string> = {
  liquid_savings: "Emergency savings",
  life_cover: "Life cover",
  health_cover: "Health cover",
  debts: "Loans and EMIs",
};

function useProfile() {
  return useQuery({ queryKey: ["profile"], queryFn: () => api.get<ProfileView>("/api/profile") });
}

function useProposal(enabled: boolean) {
  return useQuery({ queryKey: ["profile-proposal"], queryFn: () => api.get<Proposal>("/api/profile/proposal"), enabled });
}

/**
 * When what the person tracks (loans, policies, liquid savings) no longer matches the facts the advisor uses, say so
 * and offer one confirm. Nothing changes until they confirm; the values shown are the API's, not computed here.
 */
export function FactsSync({ onReview }: { onReview: () => void }) {
  const qc = useQueryClient();
  const profile = useProfile();
  const proposal = useProposal(!!profile.data?.version);
  const [hidden, setHidden] = useState(false);
  const apply = useMutation({
    mutationFn: () =>
      api.put<ProfileView>("/api/profile", {
        data: proposal.data!.proposed,
        sources: { ...(profile.data?.sources ?? {}), ...Object.fromEntries(proposal.data!.changed.map((c) => [c, "tracked"])) },
      }),
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Facts updated. Your health check and cash flow now use them.");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const changed = proposal.data?.changed ?? [];
  if (hidden || !profile.data?.version || changed.length === 0) return null;
  const now = profile.data.data;
  const next = proposal.data!.proposed;
  return (
    <div role="status" className="mb-4 rounded-2xl border bg-info-soft px-4 py-3.5">
      <p className="text-sm font-semibold">What you track no longer matches the facts your advice uses.</p>
      <ul className="mt-1.5 space-y-0.5 text-sm">
        {changed.map((k) => (
          <li key={k}>
            {FACT_LABEL[k] ?? k}:{" "}
            {k === "debts" ? (
              <span>{next.debts.length} loan{next.debts.length === 1 ? "" : "s"} tracked (your facts list {now.debts.length})</span>
            ) : (
              <span className="num">{inr(now[k as "liquid_savings" | "life_cover" | "health_cover"])} → <strong>{inr(next[k as "liquid_savings" | "life_cover" | "health_cover"])}</strong></span>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        <button disabled={apply.isPending} onClick={() => apply.mutate()} className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60">
          {apply.isPending ? "Updating…" : "Update my facts"}
        </button>
        <button onClick={onReview} className="rounded-full border bg-card px-4 py-2 text-sm font-semibold hover:bg-surface-2">Review first</button>
        <button onClick={() => setHidden(true)} className="rounded-full px-3 py-2 text-sm font-semibold text-muted-foreground hover:text-foreground">Not now</button>
      </div>
    </div>
  );
}

/** The facts every answer is built from, the risk questionnaire, and the health check they produce. */
export function FactsTab({ fill = false }: { fill?: boolean }) {
  const q = useProfile();
  const [retake, setRetake] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const loadProposal = (quiet = false) =>
    api.get<Proposal>("/api/profile/proposal").then((p) => {
      if (p.changed.length) setProposal(p);
      else if (!quiet) toast.info("Your facts already match what you track.");
    });
  useEffect(() => {
    if (fill) loadProposal(true);
  }, [fill]);
  if (q.isError) return <ErrorState message="Could not load your facts." onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-96" />;
  const d = q.data;
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.7fr_1fr]">
      <Section eyebrow={d.version ? `Version ${d.version}` : "Not set up yet"} title="Your facts"
        action={<button onClick={() => loadProposal()} className="rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2">Fill from what I track</button>}>
        {proposal && <p className="mb-4 rounded-xl bg-info-soft px-3 py-2 text-sm">Filled from your holdings, loans and insurance. Highlighted fields changed; check them and confirm to save.</p>}
        <ProfileForm key={(d.version ?? 0) + (proposal ? "-p" : "")} initial={proposal?.proposed ?? d.data} changed={proposal?.changed} onSaved={() => setProposal(null)} />
      </Section>
      <div className="space-y-4">
        <Section eyebrow="Willingness to take risk" title={d.willingness?.score ? `${cap(d.willingness.level)} (score ${d.willingness.score} of 47)` : "Not measured yet"}>
          {d.willingness?.capped_by_experience && (
            <p className="mb-3 text-sm text-muted-foreground">Your answers score {d.willingness.band_level}; it is capped at Medium until you have some investing experience.</p>
          )}
          {!d.version ? (
            <p className="text-sm text-muted-foreground">Confirm your facts first, then answer 13 short questions.</p>
          ) : retake || !d.willingness?.score ? (
            <Questionnaire onDone={() => setRetake(false)} />
          ) : (
            <button className="rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2" onClick={() => setRetake(true)}>
              Retake the questionnaire
            </button>
          )}
        </Section>
        {d.version && <TaxFacts data={d.data} />}
        {d.health && <HealthCheckView card={d.health} />}
      </div>
    </div>
  );
}

const TAX_FIELDS: [keyof NonNullable<Profile["tax"]>, string][] = [
  ["gross_salary_annual", "Yearly salary before tax"],
  ["deductions_80c", "80C investments"],
  ["deductions_80d", "Health-insurance premium (80D)"],
  ["nps_80ccd1b", "Own NPS contribution"],
  ["hra_exemption_annual", "HRA exemption"],
];

/** Optional, and used for tax estimates only: they change no health check and no plan. */
function TaxFacts({ data }: { data: Profile }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>(() => Object.fromEntries(TAX_FIELDS.map(([k]) => [k, data.tax?.[k] != null ? String(data.tax[k]) : ""])));
  const filled = TAX_FIELDS.filter(([k]) => f[k].trim() !== "");
  const answers = Object.fromEntries(filled.map(([k]) => [k, Number(f[k].replace(/,/g, ""))]));
  const valid = filled.length > 0 && Object.values(answers).every((v) => Number.isFinite(v) && v >= 0);
  const save = useMutation({
    mutationFn: () => api.post<ProfileView>("/api/profile/answer", { answers }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile"] });
      setOpen(false);
      toast.success("Saved. Ask the advisor how much tax you will pay.");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <Section eyebrow="For tax estimates · optional" title={data.tax?.gross_salary_annual ? `Salary ${inr(data.tax.gross_salary_annual)} a year` : "Not added yet"}>
      {!open ? (
        <button className="rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2" onClick={() => setOpen(true)}>
          {data.tax ? "Edit tax facts" : "Add tax facts"}
        </button>
      ) : (
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); if (valid) save.mutate(); }}>
          {TAX_FIELDS.map(([k, label]) => (
            <label key={k} className="text-sm font-medium">
              {label}
              <input inputMode="decimal" placeholder="₹ a year" className="num mt-1 w-full rounded-xl border bg-card px-3 py-2.5" value={f[k]} onChange={(e) => setF((x) => ({ ...x, [k]: e.target.value }))} />
            </label>
          ))}
          <button disabled={!valid || save.isPending} className="rounded-full bg-primary py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-40">
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </form>
      )}
      <p className="mt-3 text-xs text-muted-foreground">Used only when you ask about income tax. They do not change your health check or your plan.</p>
    </Section>
  );
}
