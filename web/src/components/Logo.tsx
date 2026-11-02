export function Logo({ withText = true }: { withText?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-8 shrink-0" aria-hidden>
        <rect width="32" height="32" rx="9" className="fill-primary" />
        <path d="M9 21.5 14 16l3.5 3.5L23 12" fill="none" stroke="var(--series-3)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="23" cy="12" r="2.2" fill="var(--series-4)" />
      </svg>
      {withText && <span className="hidden text-[17px] font-extrabold tracking-tight xl:inline">FinAdvisor</span>}
    </span>
  );
}
