import { Navigate, useNavigate, useSearch } from "@tanstack/react-router";
import { ArrowRight, ArrowUpRight, Check, ChevronDown, Lock, Moon, ShieldCheck, Sparkles, Sun, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Logo } from "@/components/Logo";
import { NOT_ADVISER } from "@/components/common";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useThemePref } from "@/components/ThemeToggle";
import { authMode, useAuth } from "@/lib/auth";
import { resolvedTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const GOOGLE = (import.meta.env.VITE_GOOGLE_AUTH as string | undefined) === "true";
const reduce = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ----------------------------------------------------------------------------- page

export function SignIn() {
  const auth = useAuth();
  const search = useSearch({ strict: false }) as { mode?: "in" | "up" };
  const navigate = useNavigate();
  const [authOpen, setAuthOpen] = useState<null | "in" | "up">(search.mode ?? null);
  const [banner, setBanner] = useState(true);
  if (auth.ready && auth.signedIn) return <Navigate to="/" />;
  const open = (m: "in" | "up") => setAuthOpen(m);

  return (
    <div className="min-h-dvh bg-background text-foreground">
      {banner && (
        <div className="relative bg-forest px-10 py-2.5 text-center text-sm text-forest-foreground">
          <Sparkles className="mr-2 inline size-4 align-[-3px]" aria-hidden />
          Research preview for young Indian earners · free, and your data stays yours
          <button aria-label="Dismiss" onClick={() => setBanner(false)} className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full p-1 opacity-80 hover:opacity-100">
            <X className="size-4" />
          </button>
        </div>
      )}
      <Nav onLogin={() => open("in")} onSignup={() => open("up")} />
      <main>
        <Hero onStart={() => open("up")} onLogin={() => open("in")} />
        <Sources />
        <Features />
        <Numbers />
        <HowItWorks onStart={() => open("up")} />
        <Faq />
      </main>
      <Footer />
      <AuthDialog mode={authOpen} onMode={setAuthOpen} onDone={() => navigate({ to: "/" })} />
    </div>
  );
}

function Nav({ onLogin, onSignup }: { onLogin: () => void; onSignup: () => void }) {
  const [pref, setPref] = useThemePref();
  const dark = pref === "dark" || (pref === "system" && typeof window !== "undefined" && resolvedTheme() === "dark");
  return (
    <header className="sticky top-0 z-40 border-b border-transparent bg-background/80 backdrop-blur-md supports-[backdrop-filter]:bg-background/65">
      <div className="mx-auto flex h-20 max-w-7xl items-center gap-8 px-5 md:px-10">
        <a href="#top" className="flex items-center gap-2.5" aria-label="FinAdvisor home">
          <Logo withText={false} />
          <span className="text-xl font-extrabold tracking-tight">FinAdvisor</span>
        </a>
        <nav aria-label="Sections" className="hidden items-center gap-8 text-[15px] font-medium text-foreground/80 lg:flex">
          <a href="#features" className="hover:text-foreground">Features</a>
          <a href="#numbers" className="hover:text-foreground">Numbers</a>
          <a href="#how" className="hover:text-foreground">How it works</a>
          <a href="#faq" className="hover:text-foreground">FAQ</a>
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <button aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setPref(dark ? "light" : "dark")}
            className="grid size-10 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground">
            {dark ? <Sun className="size-5" /> : <Moon className="size-5" />}
          </button>
          <button onClick={onLogin} className="hidden rounded-full border px-5 py-2.5 text-[15px] font-semibold transition-colors hover:bg-surface-2 sm:block">Log in</button>
          <button onClick={onSignup} className="rounded-full bg-primary px-5 py-2.5 text-[15px] font-semibold text-primary-foreground transition-transform hover:-translate-y-px">Sign up</button>
        </div>
      </div>
    </header>
  );
}

function Pill({ children, onClick, variant = "solid", className }: { children: ReactNode; onClick?: () => void; variant?: "solid" | "outline"; className?: string }) {
  return (
    <button onClick={onClick} className={cn(
      "group inline-flex items-center gap-3 rounded-full py-2 pl-6 pr-2 text-base font-semibold transition-all",
      variant === "solid" ? "bg-primary text-primary-foreground hover:-translate-y-0.5 hover:shadow-lg" : "border bg-card hover:bg-surface-2",
      className)}>
      {children}
      <span className={cn("grid size-9 place-items-center rounded-full transition-transform group-hover:translate-x-0.5",
        variant === "solid" ? "bg-primary-foreground/15" : "bg-surface-2")}>
        <ArrowRight className="size-4" aria-hidden />
      </span>
    </button>
  );
}

// ----------------------------------------------------------------------------- hero

function Hero({ onStart, onLogin }: { onStart: () => void; onLogin: () => void }) {
  return (
    <section id="top" className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0 hidden dark:block">
        <div className="absolute -right-40 -top-40 size-[44rem] rounded-full bg-[radial-gradient(circle_at_35%_35%,color-mix(in_oklab,var(--brand)_35%,transparent),transparent_60%)] blur-2xl" />
        <div className="absolute inset-0 opacity-[0.06] [background-image:repeating-linear-gradient(90deg,var(--foreground)_0_1px,transparent_1px_64px)]" />
        <div className="grain absolute inset-0" />
      </div>
      <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 pb-16 pt-10 md:px-10 md:pb-24 md:pt-16 lg:grid-cols-[1.05fr_1fr]">
        <div className="reveal">
          <p className="mb-5 text-sm font-semibold uppercase tracking-[0.14em] text-brand">Plan · Track · Understand</p>
          <h1 className="text-[44px] font-semibold leading-[1.02] tracking-[-0.035em] sm:text-6xl lg:text-[76px]">
            Advice that fits your <span className="font-serif text-[1.08em] font-normal italic tracking-[-0.01em]">money</span>, before it fits a sales target.
          </h1>
          <p className="mt-7 max-w-xl text-lg leading-relaxed text-muted-foreground">
            FinAdvisor works out how much risk you can actually afford from your real numbers, turns it into a plan in rupees and months,
            and checks every plan before you see it. Your stocks, funds, gold and deposits sit right next to it.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Pill onClick={onStart}>Get started free</Pill>
            <button onClick={onLogin} className="rounded-full px-5 py-3 text-base font-semibold text-foreground/80 underline-offset-4 hover:text-foreground hover:underline">
              I have an account
            </button>
          </div>
          <ul className="mt-9 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
            <li className="flex items-center gap-2"><Check className="size-4 text-brand" aria-hidden />No product commissions</li>
            <li className="flex items-center gap-2"><Check className="size-4 text-brand" aria-hidden />Never tips individual stocks</li>
            <li className="flex items-center gap-2"><Lock className="size-4 text-brand" aria-hidden />Runs on a model we host</li>
          </ul>
        </div>
        <Bento />
      </div>
    </section>
  );
}

function Bento() {
  return (
    <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 sm:gap-4" aria-label="What FinAdvisor shows you (example data)">
      <div className="min-[480px]:col-span-2 sm:col-span-1">
        <TiltCard />
      </div>
      <div className="relative min-h-52 overflow-hidden rounded-tl-[7rem] rounded-br-3xl rounded-tr-3xl rounded-bl-3xl bg-cream p-6 sm:min-h-64">
        <p className="text-right text-6xl font-semibold tracking-tight sm:text-7xl">7</p>
        <p className="mt-1 text-right text-lg leading-snug">point money<br />health check</p>
        <svg aria-hidden viewBox="0 0 80 80" className="absolute bottom-5 left-5 size-16 text-forest dark:text-primary">
          <circle cx="40" cy="40" r="32" fill="none" stroke="currentColor" strokeOpacity=".2" strokeWidth="6" />
          <circle cx="40" cy="40" r="32" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" strokeDasharray="201" strokeDashoffset="57" transform="rotate(-90 40 40)" className="ring-draw" />
        </svg>
      </div>
      <div className="relative min-h-52 overflow-hidden rounded-3xl rounded-tr-[7rem] bg-sage p-6 sm:min-h-64">
        <svg aria-hidden viewBox="0 0 120 60" className="w-28 text-forest dark:text-primary">
          <path d="M30 2 C33 22 38 27 58 30 C38 33 33 38 30 58 C27 38 22 33 2 30 C22 27 27 22 30 2Z" fill="currentColor" />
          <path d="M84 6 C86 22 90 26 106 28 C90 30 86 34 84 50 C82 34 78 30 62 28 C78 26 82 22 84 6Z" fill="currentColor" />
        </svg>
        <p className="mt-8 text-2xl font-semibold tracking-tight">6 twin checks</p>
        <p className="mt-1 text-sm text-muted-foreground">on every plan: less savings, a new EMI or one more dependant must never get riskier advice.</p>
      </div>
      <div className="relative min-h-52 overflow-hidden rounded-3xl bg-forest p-6 text-forest-foreground sm:min-h-64">
        <div className="flex items-start justify-between">
          <p className="text-[34px] font-semibold leading-none tracking-tight">₹6,000<span className="text-lg font-medium opacity-70">/mo</span></p>
          <ArrowUpRight className="size-6 opacity-80" aria-hidden />
        </div>
        <p className="mt-auto pt-14 text-right text-lg leading-snug opacity-90">for 10 months builds your<br />₹60,000 emergency fund</p>
        <span className="absolute bottom-4 left-6 text-[11px] uppercase tracking-wider opacity-60">Example plan step</span>
      </div>
    </div>
  );
}

/** A tilted, floating dashboard card. Follows the pointer gently; still under reduced motion. */
function TiltCard() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reduce()) return;
    const parent = el.parentElement!;
    const move = (e: PointerEvent) => {
      const r = parent.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      el.style.setProperty("--ry", `${-14 + x * 16}deg`);
      el.style.setProperty("--rx", `${10 - y * 12}deg`);
    };
    const leave = () => {
      el.style.removeProperty("--ry");
      el.style.removeProperty("--rx");
    };
    parent.addEventListener("pointermove", move);
    parent.addEventListener("pointerleave", leave);
    return () => {
      parent.removeEventListener("pointermove", move);
      parent.removeEventListener("pointerleave", leave);
    };
  }, []);
  return (
    <div className="relative grid h-full min-h-64 place-items-center overflow-hidden rounded-3xl bg-sage p-5 [perspective:1100px] dark:bg-surface-2">
      <div aria-hidden className="absolute -bottom-16 -left-16 size-56 rounded-full bg-[radial-gradient(circle,color-mix(in_oklab,var(--brand)_30%,transparent),transparent_70%)]" />
      <div ref={ref} className="tilt relative w-full max-w-[300px] rounded-2xl border bg-card p-4 shadow-[0_30px_60px_-20px_rgb(10_30_25/0.45)]">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Net worth</p>
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">Example data</span>
        </div>
        <p className="mt-2 text-[28px] font-extrabold tracking-tight">₹8,24,000<span className="text-base text-muted-foreground">.00</span></p>
        <p className="mt-1 inline-flex items-center gap-1 rounded-full bg-gain-soft px-2 py-0.5 text-[11px] font-bold text-gain">
          <ArrowUpRight className="size-3" aria-hidden /> +₹12,450 this month
        </p>
        <svg viewBox="0 0 260 70" className="mt-3 w-full" aria-hidden>
          <defs>
            <linearGradient id="tc-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="var(--series-1)" stopOpacity=".25" />
              <stop offset="1" stopColor="var(--series-1)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d="M0 58 C20 54 30 50 48 52 S80 40 98 42 S130 30 150 34 S190 18 210 22 S240 10 260 8 L260 70 L0 70Z" fill="url(#tc-fill)" />
          <path d="M0 58 C20 54 30 50 48 52 S80 40 98 42 S130 30 150 34 S190 18 210 22 S240 10 260 8" fill="none" stroke="var(--series-1)" strokeWidth="2.5" strokeLinecap="round" className="line-draw" />
        </svg>
        <div className="mt-3 flex h-2 overflow-hidden rounded-full" aria-hidden>
          {[["--series-1", 34], ["--series-2", 22], ["--series-3", 18], ["--series-4", 14], ["--series-6", 12]].map(([v, w]) => (
            <span key={v} style={{ width: `${w}%`, background: `var(${v})` }} className="h-full border-r-2 border-card last:border-0" />
          ))}
        </div>
        <div className="mt-2 flex justify-between text-[10px] text-muted-foreground">
          <span>Stocks</span><span>Funds</span><span>FDs</span><span>Gold</span><span>EPF</span>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------- sections

function Sources() {
  const items = ["NSE bhavcopy", "BSE bhavcopy", "AMFI NAVs", "NSE Indices", "SEBI health-check thresholds"];
  return (
    <section aria-label="Where the numbers come from" className="mx-auto max-w-7xl px-5 md:px-10">
      <div className="border-y py-8">
        <p className="mb-5 text-center text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Every price shows its source and date</p>
        <ul className="flex flex-wrap items-center justify-center gap-x-12 gap-y-4 text-xl font-bold tracking-tight text-foreground/55 md:justify-between">
          {items.map((i) => <li key={i}>{i}</li>)}
        </ul>
      </div>
    </section>
  );
}

function Eyebrow({ children, center }: { children: ReactNode; center?: boolean }) {
  return <p className={cn("text-sm font-semibold uppercase tracking-[0.14em] text-brand", center && "text-center")}>{children}</p>;
}

function Features() {
  return (
    <section id="features" className="mx-auto max-w-7xl scroll-mt-24 px-5 py-24 md:px-10 md:py-32">
      <Eyebrow center>Features</Eyebrow>
      <h2 className="mx-auto mt-4 max-w-3xl text-center text-4xl font-semibold leading-[1.08] tracking-[-0.03em] md:text-6xl">
        One place for your money, and advice that <span className="font-serif font-normal italic">stays put</span>
      </h2>
      <p className="mx-auto mt-5 max-w-2xl text-center text-lg text-muted-foreground">
        Pressure from a friend's small-cap win doesn't change your plan. A new EMI does, and FinAdvisor shows you exactly how.
      </p>

      <div className="mt-16 grid gap-4 lg:grid-cols-[1fr_1.6fr]">
        <div className="relative flex min-h-80 flex-col justify-end overflow-hidden rounded-3xl bg-forest p-8 text-forest-foreground">
          <svg aria-hidden viewBox="0 0 320 200" className="mb-6 h-32 w-full max-w-xs opacity-90 lg:absolute lg:inset-x-8 lg:top-8 lg:mb-0 lg:h-40">
            {[40, 62, 54, 90, 76, 118].map((h, i) => (
              <rect key={i} x={i * 50 + 10} y={190 - h} width="24" height={h} rx="4" fill="currentColor" opacity={i === 5 ? 1 : 0.25} />
            ))}
          </svg>
          <p className="relative text-2xl font-semibold tracking-tight">Track everything you own</p>
          <p className="relative mt-2 opacity-80">Stocks and ETFs, mutual funds, gold, FDs and RDs, EPF and PPF, property and loans. Net worth is assets minus loans, never a guess.</p>
        </div>
        <div className="relative min-h-80 overflow-hidden rounded-3xl rounded-bl-[9rem] bg-sage p-8 md:p-10">
          <p className="max-w-md text-3xl font-semibold leading-tight tracking-tight md:text-4xl">Your money health, checked in five seconds</p>
          <ul className="mt-8 grid max-w-lg gap-2.5 sm:grid-cols-2">
            {[["Emergency fund", true], ["Life cover", true], ["Health cover", false], ["Card dues", true], ["EMI load", true], ["Short goals", false]].map(([t, ok]) => (
              <li key={t as string} className="flex items-center gap-3 rounded-2xl bg-card/80 px-4 py-3 text-sm font-medium backdrop-blur">
                <span className={cn("grid size-6 place-items-center rounded-full text-xs font-bold", ok ? "bg-gain-soft text-gain" : "bg-loss-soft text-loss")}>{ok ? "✓" : "!"}</span>
                {t as string}
                <span className="sr-only">{ok ? "passes" : "needs attention"}</span>
              </li>
            ))}
          </ul>
          <span className="absolute bottom-5 right-7 text-[11px] uppercase tracking-wider text-muted-foreground">Example data</span>
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {[
          ["Plans in rupees and months", "₹6,000 a month for 10 months, not '30% in hybrid funds'. Every amount comes from tested calculators, never from the AI."],
          ["Suitable by construction", "Your capacity for loss is computed from your real numbers. Products that don't fit are held back, and the reason is shown."],
          ["Private by design", "Answers come from an open model FinAdvisor runs itself. Statement passwords are never stored; account numbers are masked."],
        ].map(([t, d]) => (
          <article key={t} className="group flex min-h-64 flex-col rounded-3xl border bg-card p-8 transition-colors hover:bg-surface-2/50">
            <h3 className="text-xl font-semibold tracking-tight">{t}</h3>
            <p className="mt-3 text-muted-foreground">{d}</p>
            <span className="mt-auto grid size-12 place-items-center rounded-full border transition-transform group-hover:rotate-45" aria-hidden>
              <ArrowUpRight className="size-5" />
            </span>
          </article>
        ))}
      </div>
    </section>
  );
}

function Numbers() {
  const stats = [["5,700+", "stocks, ETFs and gold bonds priced every trading day"], ["14,400+", "mutual fund schemes with daily NAVs"], ["0", "numbers written by the AI"]];
  return (
    <section id="numbers" className="satin relative scroll-mt-20 overflow-hidden text-forest-foreground">
      <div className="relative mx-auto max-w-7xl px-5 py-24 md:px-10 md:py-32">
        <div className="grid gap-6 lg:grid-cols-2 lg:items-end">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.14em] opacity-80">Numbers</p>
            <h2 className="mt-4 text-4xl font-semibold leading-[1.08] tracking-[-0.03em] md:text-6xl">Real data, honest gaps</h2>
          </div>
          <p className="text-lg opacity-85 lg:pl-16">If a price is stale or missing, FinAdvisor says so. It never fills a chart with invented numbers.</p>
        </div>
        <div className="mt-16 grid gap-10 border-t border-white/15 pt-12 sm:grid-cols-3">
          {stats.map(([n, l]) => (
            <div key={l}>
              <p className="text-6xl font-semibold tracking-[-0.04em] lg:text-7xl">{n}</p>
              <p className="mt-4 max-w-64 text-lg leading-snug opacity-90">{l}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks({ onStart }: { onStart: () => void }) {
  const steps = [
    ["01", "Tell it about you", "Income, expenses, savings, EMIs, cover and goals, in a chat or a form. Nothing is used until you confirm it."],
    ["02", "Answer 13 questions", "A validated risk questionnaire measures how much ups and downs you're comfortable with."],
    ["03", "Get a checked plan", "Steps in order with rupee amounts, audited against twin profiles, with 'Why this plan' one tap away."],
  ];
  return (
    <section id="how" className="mx-auto max-w-7xl scroll-mt-24 px-5 py-24 md:px-10 md:py-32">
      <div className="grid gap-10 lg:grid-cols-2">
        <div>
          <Eyebrow>How it works</Eyebrow>
          <h2 className="mt-4 text-4xl font-semibold leading-[1.08] tracking-[-0.03em] md:text-6xl">Make your money, <span className="font-serif font-normal italic">well-planned</span></h2>
        </div>
        <p className="self-end text-lg text-muted-foreground lg:pl-16">
          Three steps, about five minutes. Then the tracker keeps your numbers fresh every evening after the markets publish.
        </p>
      </div>
      <ol className="mt-14 grid gap-4 md:grid-cols-3">
        {steps.map(([n, t, d]) => (
          <li key={n} className="rounded-3xl border bg-card p-8">
            <p className="font-serif text-5xl italic text-brand">{n}</p>
            <h3 className="mt-6 text-xl font-semibold tracking-tight">{t}</h3>
            <p className="mt-2 text-muted-foreground">{d}</p>
          </li>
        ))}
      </ol>
      <div className="mt-12 flex justify-center"><Pill onClick={onStart}>Start your plan</Pill></div>
    </section>
  );
}

function Faq() {
  const qs = [
    ["Is FinAdvisor a SEBI-registered investment adviser?", NOT_ADVISER],
    ["Will it tell me which stock to buy?", "No. It shows prices, 52-week ranges and your own gains, and it comments on your portfolio as a whole (concentration, risk versus your capacity, costs), but never says buy, sell or hold for a stock."],
    ["Where does my financial data go?", "To FinAdvisor's own database and an open model it runs itself. It is never sent to a third-party AI service. You can export or delete everything from Settings."],
    ["Can I import my CAS?", "Yes. CAMS and KFintech statements bring in mutual fund transactions; NSDL and CDSL statements bring in demat holdings. The PDF and its password are never stored."],
    ["What does it cost?", "Nothing. FinAdvisor is a free research project and takes no commissions."],
  ];
  return (
    <section id="faq" className="mx-auto max-w-4xl scroll-mt-24 px-5 pb-24 md:px-10 md:pb-32">
      <Eyebrow center>FAQ</Eyebrow>
      <h2 className="mt-4 text-center text-4xl font-semibold tracking-[-0.03em] md:text-5xl">Questions, answered</h2>
      <div className="mt-12 divide-y rounded-3xl border bg-card">
        {qs.map(([q, a]) => (
          <details key={q} className="group px-6 py-5 md:px-8">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-lg font-semibold">
              {q}
              <ChevronDown className="size-5 shrink-0 transition-transform group-open:rotate-180" aria-hidden />
            </summary>
            <p className="mt-3 text-muted-foreground">{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex max-w-7xl flex-wrap items-start justify-between gap-6 px-5 py-10 text-sm text-muted-foreground md:px-10">
        <div className="flex items-center gap-2.5 text-foreground"><Logo withText={false} /><span className="font-bold">FinAdvisor</span></div>
        <p className="max-w-xl">{NOT_ADVISER}</p>
        <p className="flex items-center gap-1.5"><ShieldCheck className="size-4" aria-hidden /> Education and planning only</p>
      </div>
    </footer>
  );
}

// ----------------------------------------------------------------------------- auth

function AuthDialog({ mode, onMode, onDone }: { mode: null | "in" | "up"; onMode: (m: null | "in" | "up") => void; onDone: () => void }) {
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setErr(null);
    setMsg(null);
  }, [mode]);

  const run = async (fn: () => Promise<unknown>, after?: () => void) => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const r = await fn();
      if (typeof r === "string") setMsg(r);
      else after?.();
    } catch (e) {
      setErr(friendly((e as Error).message));
    } finally {
      setBusy(false);
    }
  };
  const input = "mt-1.5 w-full rounded-2xl border bg-background px-4 py-3.5 text-base outline-none transition-shadow focus:ring-2 focus:ring-ring";

  return (
    <Dialog open={mode !== null} onOpenChange={(o) => !o && onMode(null)}>
      <DialogContent className="max-w-md overflow-hidden rounded-[28px] p-0">
        <div className="bg-forest px-8 pb-7 pt-8 text-forest-foreground">
          <span className="inline-grid rounded-xl bg-forest-foreground p-1"><Logo withText={false} /></span>
          <DialogTitle className="mt-5 text-3xl font-semibold tracking-tight">
            {mode === "up" ? <>Start with your <span className="font-serif font-normal italic">real</span> numbers</> : "Welcome back"}
          </DialogTitle>
          <DialogDescription className="mt-2 text-forest-foreground/80">
            {mode === "up" ? "Free. Your chats and holdings follow you to any device." : "Pick up any chat right where you left it."}
          </DialogDescription>
        </div>
        <div className="px-8 pb-8 pt-6">
          {authMode === "supabase" && (
            <div role="tablist" aria-label="Account" className="mb-5 grid grid-cols-2 rounded-full bg-surface-2 p-1">
              {(["in", "up"] as const).map((m) => (
                <button key={m} role="tab" aria-selected={mode === m} onClick={() => onMode(m)}
                  className={cn("rounded-full py-2 text-sm font-semibold transition-colors", mode === m ? "bg-card shadow-sm" : "text-muted-foreground")}>
                  {m === "in" ? "Log in" : "Create account"}
                </button>
              ))}
            </div>
          )}
          {authMode === "dev" ? (
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(() => auth.devSignIn(email, name || undefined), onDone); }}>
              <p className="rounded-2xl bg-info-soft px-4 py-3 text-sm">Development mode: Supabase sign-in is not configured on this build.</p>
              <label className="block text-sm font-medium">Email<input type="email" required autoComplete="email" className={input} value={email} onChange={(e) => setEmail(e.target.value)} /></label>
              <label className="block text-sm font-medium">Name (optional)<input autoComplete="name" className={input} value={name} onChange={(e) => setName(e.target.value)} /></label>
              <Submit busy={busy}>Continue</Submit>
            </form>
          ) : (
            <form className="space-y-4" onSubmit={(e) => {
              e.preventDefault();
              run(() => (mode === "up" ? auth.signUpWithEmail(email, password, name) : auth.signInWithEmail(email, password)), onDone);
            }}>
              {GOOGLE && (
                <>
                  <button type="button" onClick={() => run(() => auth.signInWithGoogle())}
                    className="flex w-full items-center justify-center gap-2 rounded-full border bg-card px-4 py-3 font-semibold transition-colors hover:bg-surface-2">
                    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
                      <path fill="#4285F4" d="M22.6 12.3c0-.8-.1-1.6-.2-2.3H12v4.4h6a5 5 0 0 1-2.2 3.3v2.7h3.5c2-1.9 3.3-4.7 3.3-8.1z" />
                      <path fill="#34A853" d="M12 23c3 0 5.5-1 7.3-2.6l-3.5-2.7c-1 .7-2.3 1.1-3.8 1.1-2.9 0-5.4-2-6.3-4.6H2.1v2.8A11 11 0 0 0 12 23z" />
                      <path fill="#FBBC05" d="M5.7 14.2a6.6 6.6 0 0 1 0-4.3V7.1H2.1a11 11 0 0 0 0 9.9l3.6-2.8z" />
                      <path fill="#EA4335" d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.1-3.1A11 11 0 0 0 2.1 7.1l3.6 2.8C6.6 7.4 9.1 5.4 12 5.4z" />
                    </svg>
                    Continue with Google
                  </button>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" /></div>
                </>
              )}
              {mode === "up" && <label className="block text-sm font-medium">Name<input required autoComplete="name" className={input} value={name} onChange={(e) => setName(e.target.value)} /></label>}
              <label className="block text-sm font-medium">Email<input type="email" required autoComplete="email" className={input} value={email} onChange={(e) => setEmail(e.target.value)} /></label>
              <label className="block text-sm font-medium">Password
                <input type="password" required minLength={8} autoComplete={mode === "up" ? "new-password" : "current-password"} className={input} value={password} onChange={(e) => setPassword(e.target.value)} />
                {mode === "up" && <span className="mt-1 block text-xs font-normal text-muted-foreground">At least 8 characters.</span>}
              </label>
              <Submit busy={busy}>{mode === "up" ? "Create account" : "Log in"}</Submit>
            </form>
          )}
          {err && <p role="alert" className="mt-4 rounded-2xl bg-loss-soft px-4 py-3 text-sm">{err}</p>}
          {msg && <p role="status" className="mt-4 rounded-2xl bg-info-soft px-4 py-3 text-sm">{msg}</p>}
          <p className="mt-6 text-center text-xs text-muted-foreground">By continuing you agree that FinAdvisor offers education and planning, not investment advice.</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Submit({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button disabled={busy} className="group flex w-full items-center justify-center gap-3 rounded-full bg-primary py-3.5 text-base font-semibold text-primary-foreground transition-opacity disabled:opacity-60">
      {busy ? "Please wait…" : children}
      {!busy && <span className="grid size-6 place-items-center rounded-full bg-primary-foreground/15 transition-transform group-hover:translate-x-0.5"><ArrowRight className="size-3.5" aria-hidden /></span>}
    </button>
  );
}

function friendly(m: string): string {
  if (/invalid login credentials/i.test(m)) return "That email and password don't match. Check them, or create an account.";
  if (/email not confirmed/i.test(m)) return "Please confirm your email first: open the link we sent you, then log in.";
  if (/already registered/i.test(m)) return "An account with this email already exists. Log in instead.";
  if (/rate limit/i.test(m)) return "Too many attempts. Please wait a minute and try again.";
  return m;
}
