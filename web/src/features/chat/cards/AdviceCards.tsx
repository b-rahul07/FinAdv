import { CheckCircle2, CircleAlert, ShieldCheck, ShieldAlert, Target, Wrench, XCircle } from "lucide-react";
import { Pill } from "@/components/common";
import { inr, months, pct } from "@/lib/format";
import type { GoalCard, HealthCheck, NotYetCard, PlanCard } from "@/lib/types";
import { cn } from "@/lib/utils";

export function CardShell({ eyebrow, title, children, aside, className }: { eyebrow: string; title: React.ReactNode; children: React.ReactNode; aside?: React.ReactNode; className?: string }) {
  return (
    <section className={cn("card fade-in overflow-hidden", className)}>
      <header className="flex items-start justify-between gap-3 px-5 pb-3 pt-4">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h3 className="mt-1 text-base font-bold leading-snug tracking-tight">{title}</h3>
        </div>
        {aside}
      </header>
      <div className="px-5 pb-5">{children}</div>
    </section>
  );
}

export function HealthCheckView({ card }: { card: HealthCheck }) {
  return (
    <CardShell
      eyebrow="Money health check"
      title={
        <>
          <span className="num">{card.score}</span> of <span className="num">{card.out_of}</span> checks pass
        </>
      }
      aside={<Pill>Capacity: {cap(card.capacity_level)}</Pill>}
    >
      <ul className="divide-y">
        {card.checks.map((c) => (
          <li key={c.key} className="flex gap-3 py-2.5">
            {c.status === "pass" ? (
              <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-good" aria-label="Pass" />
            ) : (
              <XCircle className="mt-0.5 size-5 shrink-0 text-loss" aria-label="Needs attention" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-semibold">
                {c.title} <span className="sr-only">{c.status === "pass" ? "passes" : "needs attention"}</span>
                <span className={cn("ml-2 text-xs font-bold", c.status === "pass" ? "text-good" : "text-loss")} aria-hidden>
                  {c.status === "pass" ? "Pass" : "Needs attention"}
                </span>
              </p>
              <p className="text-sm text-muted-foreground">{c.reason}</p>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted-foreground">Thresholds from SEBI's investor-portal Financial Health Check.</p>
    </CardShell>
  );
}

const AUDIT: Record<string, { label: string; icon: typeof ShieldCheck; tone: string }> = {
  pass: { label: "Audit passed", icon: ShieldCheck, tone: "text-good" },
  repaired: { label: "Audit repaired the plan", icon: Wrench, tone: "text-warn" },
  fallback: { label: "Safe plan used", icon: ShieldAlert, tone: "text-warn" },
  off: { label: "Not audited", icon: CircleAlert, tone: "text-muted-foreground" },
  illustrative: { label: "Illustrative", icon: CircleAlert, tone: "text-muted-foreground" },
};

export function PlanView({ card }: { card: PlanCard }) {
  const a = AUDIT[card.audit_status] ?? AUDIT.off;
  const Icon = a.icon;
  return (
    <CardShell
      eyebrow="Your plan"
      title={`${card.steps.length} step${card.steps.length === 1 ? "" : "s"}, in this order`}
      aside={
        <span className={cn("inline-flex items-center gap-1 text-xs font-bold", a.tone)}>
          <Icon className="size-4" aria-hidden /> {a.label}
        </span>
      }
    >
      <p className="mb-3 text-sm text-muted-foreground">
        Money left after expenses and EMIs: <strong className="num text-foreground">{inr(card.monthly_surplus)}/month</strong>
      </p>
      <ol className="space-y-3">
        {card.steps.map((s) => (
          <li key={s.order} className="flex gap-3">
            <span className="num grid size-7 shrink-0 place-items-center rounded-full bg-surface-2 text-sm font-bold">{s.order}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm leading-relaxed">{s.text}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {s.monthly > 0 && <Pill className="num">{inr(s.monthly)}/month</Pill>}
                {s.months > 0 && <Pill className="num">{months(s.months)}</Pill>}
                {s.action === "invest" && <Pill className="num">from month {s.start_month}</Pill>}
                {s.rule && <Pill>{s.rule}</Pill>}
              </div>
            </div>
          </li>
        ))}
      </ol>
      {card.notes.length > 0 && (
        <ul className="mt-4 space-y-1 text-xs text-muted-foreground">
          {card.notes.map((n) => (
            <li key={n}>• {n}</li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

export function GoalView({ card }: { card: GoalCard }) {
  const needed = card.sip_needed ?? 0;
  const share = needed > 0 ? Math.min(1, card.monthly_assigned / needed) : card.fundable ? 1 : 0;
  return (
    <CardShell
      eyebrow="Goal"
      title={card.name}
      aside={
        <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2.5 py-0.5 text-[11px] font-bold tracking-wider">
          <Target className="size-3.5" aria-hidden /> GOAL
        </span>
      }
    >
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <div>
          <dt className="text-muted-foreground">Cost today</dt>
          <dd className="num font-bold">{inr(card.target_today)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">In {card.horizon_years} years</dt>
          <dd className="num font-bold">{inr(card.target_future)}</dd>
          <dd className="text-xs text-muted-foreground">at {card.inflation_pa}% inflation</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">SIP needed</dt>
          <dd className="num font-bold">{card.sip_needed !== null ? `${inr(card.sip_needed)}/month` : "—"}</dd>
          {card.assumed_return_pa !== null && <dd className="text-xs text-muted-foreground">assumes {card.assumed_return_pa.toFixed(1)}% a year, not guaranteed</dd>}
        </div>
        <div>
          <dt className="text-muted-foreground">Your budget covers</dt>
          <dd className="num font-bold">{inr(card.monthly_assigned)}/month</dd>
          <dd className="text-xs text-muted-foreground">from month {card.starts_month}</dd>
        </div>
      </dl>
      <div className="mt-4">
        <div className="mb-1 flex justify-between text-xs">
          <span className="font-semibold">{card.fundable ? "Fully funded by your budget" : card.fundable === false ? "Partly funded" : "Not sized yet"}</span>
          <span className="num text-muted-foreground">{pct(share, 0)}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={Math.round(share * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Share of the SIP your budget covers">
          <div className="h-full rounded-full bg-series-3" style={{ width: `${share * 100}%` }} />
        </div>
        {card.fundable === false && card.shortfall > 0 && (
          <p className="mt-2 text-sm text-muted-foreground">
            Short by <strong className="num text-foreground">{inr(card.shortfall)}/month</strong>. Options: a later date, a smaller target, or more income.
          </p>
        )}
      </div>
    </CardShell>
  );
}

export function NotYetView({ card }: { card: NotYetCard }) {
  const fits = card.verdict === "fits";
  return (
    <CardShell
      eyebrow={fits ? "Suitability check" : card.verdict === "after_priorities" ? "After your priorities" : "Not yet"}
      title={card.product_name}
      className={fits ? "" : "border-warn/40"}
      aside={<Pill>Suitability: {cap(card.suitability)}</Pill>}
    >
      {fits && <p className="text-sm">This fits your current situation. Keep it within your plan's monthly amounts.</p>}
      {card.new_emi !== undefined && card.emi_ratio_after !== undefined && (
        <p className="mb-3 text-sm">
          EMIs today: <strong className="num">{pct(card.emi_ratio_now ?? 0)}</strong> of take-home. With this {inr(card.new_emi)}/month EMI:{" "}
          <strong className="num">{pct(card.emi_ratio_after)}</strong> (limit 40%).
        </p>
      )}
      {card.blockers.length > 0 && (
        <>
          <h4 className="mb-1 text-sm font-bold">Why not now</h4>
          <ul className="mb-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {card.blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </>
      )}
      {card.changes.length > 0 && !fits && (
        <>
          <h4 className="mb-1 text-sm font-bold">What would need to change first</h4>
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {card.changes.map((c) => (
              <li key={c.text}>{c.text}</li>
            ))}
          </ol>
        </>
      )}
      {card.fact && (
        <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
          {card.fact.text} <span className="block">Source: {card.fact.source}</span>
        </p>
      )}
    </CardShell>
  );
}

export function cap(s: string | null | undefined) {
  return s ? s[0].toUpperCase() + s.slice(1) : "—";
}
