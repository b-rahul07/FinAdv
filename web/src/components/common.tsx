import { ArrowDownRight, ArrowUpRight, Info, Minus } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function PageHeader({ eyebrow, title, crumbs, actions }: { eyebrow?: string; title: ReactNode; crumbs?: string[]; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {crumbs && (
          <nav aria-label="Breadcrumb" className="mb-1 text-sm text-muted-foreground">
            {crumbs.join(" / ")}
          </nav>
        )}
        {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
        <h1 className="text-[28px] font-extrabold leading-tight tracking-tight md:text-[32px]">{title}</h1>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Section({ eyebrow, title, children, className, action }: { eyebrow?: string; title?: string; children: ReactNode; className?: string; action?: ReactNode }) {
  return (
    <section className={cn("card p-5 md:p-6", className)}>
      {(eyebrow || title) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && <h2 className="mt-1 text-lg font-bold tracking-tight">{title}</h2>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ title, body, children, icon }: { title: string; body: ReactNode; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed px-6 py-10 text-center">
      {icon && <div className="mb-3 grid size-12 place-items-center rounded-2xl bg-surface-2 text-muted-foreground">{icon}</div>}
      <h3 className="text-lg font-bold">{title}</h3>
      <div className="mt-1 max-w-md text-sm text-muted-foreground">{body}</div>
      {children && <div className="mt-5 flex flex-wrap justify-center gap-2">{children}</div>}
    </div>
  );
}

export function InfoNote({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return (
    <div className={cn("flex gap-2.5 rounded-xl px-3.5 py-3 text-sm", tone === "warn" ? "bg-warn-soft" : "bg-info-soft")}>
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

/** Gain/loss is never colour alone: sign, arrow and colour together. */
export function Delta({ value, text, className }: { value: number; text: string; className?: string }) {
  const Icon = value > 0 ? ArrowUpRight : value < 0 ? ArrowDownRight : Minus;
  return (
    <span
      className={cn(
        "num inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-bold",
        value > 0 ? "bg-gain-soft text-gain" : value < 0 ? "bg-loss-soft text-loss" : "bg-surface-2 text-muted-foreground",
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {text}
    </span>
  );
}

export function Pill({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center rounded-full bg-surface-2 px-2.5 py-0.5 text-xs font-semibold text-muted-foreground", className)}>{children}</span>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton h-4", className)} aria-hidden />;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-loss/30 bg-loss-soft px-4 py-3 text-sm">
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="rounded-full bg-card px-3 py-1 font-semibold">
          Try again
        </button>
      )}
    </div>
  );
}

export const NOT_ADVISER =
  "FinAdvisor is not a SEBI-registered investment adviser. It offers education and planning only, never recommends individual securities and does not carry out transactions.";
