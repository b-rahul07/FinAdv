// Display formatting only. Every number arrives already computed by the backend; this file never does finance maths.

const MINUS = "−";
const IST = "Asia/Kolkata";

let grouping: "en-IN" | "en-US" = "en-IN";

/** Indian digit grouping (1,23,45,678) is the default; users can switch to international grouping in settings. */
export function setIndianGrouping(on: boolean) {
  grouping = on ? "en-IN" : "en-US";
}

function nf(decimals: number) {
  return new Intl.NumberFormat(grouping, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function num(n: number, decimals = 0): string {
  const s = nf(decimals).format(Math.abs(n));
  return n < 0 && Number(s.replace(/,/g, "")) !== 0 ? MINUS + s : s;
}

/** ₹ with grouping. inr(1234567.5, 2) -> "₹12,34,567.50" */
export function inr(n: number | null | undefined, decimals = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const s = "₹" + nf(decimals).format(Math.abs(n));
  return n < 0 && Math.abs(n) >= 0.5 * 10 ** -decimals ? MINUS + s : s;
}

/** Signed amount for changes: "+₹1,200" / "−₹1,200" / "₹0". */
export function signedInr(n: number, decimals = 0): string {
  if (Math.abs(n) < 0.5 * 10 ** -decimals) return inr(0, decimals);
  return (n > 0 ? "+" : MINUS) + inr(Math.abs(n), decimals);
}

/** Hero split: the whole rupees and the muted paise part. */
export function inrParts(n: number): { whole: string; fraction: string } {
  const s = inr(n, 2);
  const i = s.lastIndexOf(".");
  return { whole: s.slice(0, i), fraction: s.slice(i) };
}

/** Lakh / crore shorthand for prose: 1250000 -> "₹12.5 lakh". */
export function inrWords(n: number): string {
  const a = Math.abs(n);
  const sign = n < 0 ? MINUS : "";
  const trim = (v: number) => String(Math.round(v * 100) / 100);
  if (a >= 1e7) return `${sign}₹${trim(a / 1e7)} crore`;
  if (a >= 1e5) return `${sign}₹${trim(a / 1e5)} lakh`;
  return inr(n);
}

/** Compact axis label: ₹45K, ₹1.2L, ₹3.4Cr. */
export function inrAxis(n: number): string {
  const a = Math.abs(n);
  const sign = n < 0 ? MINUS : "";
  const t = (v: number) => (v >= 10 ? Math.round(v) : Math.round(v * 10) / 10).toString();
  if (a >= 1e7) return `${sign}₹${t(a / 1e7)}Cr`;
  if (a >= 1e5) return `${sign}₹${t(a / 1e5)}L`;
  if (a >= 1e3) return `${sign}₹${t(a / 1e3)}K`;
  return `${sign}₹${Math.round(a)}`;
}

/** Percent from a fraction: pct(0.1234) -> "12.3%"; signed adds +/−. */
export function pct(fraction: number | null | undefined, decimals = 1, signed = false): string {
  if (fraction === null || fraction === undefined || Number.isNaN(fraction)) return "—";
  const v = fraction * 100;
  const body = nf(decimals).format(Math.abs(v)) + "%";
  if (Math.abs(v) < 0.5 * 10 ** -decimals) return nf(decimals).format(0) + "%";
  if (v < 0) return MINUS + body;
  return (signed ? "+" : "") + body;
}

/** "31 Oct 2026" in IST. */
export function date(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: IST }).format(d);
}

/** "Nov 2026" for timelines. */
export function monthYear(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: IST }).format(d);
}

/** "31 Oct 2026, 8:15 pm IST" */
export function dateTime(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const t = new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: IST })
    .format(d)
    .replace(/\s?(am|pm)/i, (m) => " " + m.trim().toLowerCase());
  return `${date(d)}, ${t} IST`;
}

/** "Saturday, 31 October" for the dashboard date line. */
export function longDay(d: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: IST }).format(d);
}

export function months(n: number): string {
  if (n < 24) return `${n} month${n === 1 ? "" : "s"}`;
  const y = Math.round((n / 12) * 10) / 10;
  return `${y} years`;
}

/** Chat sidebar groups: Today, Yesterday, Previous 7 days, Previous 30 days, then "October 2026". */
export function dateGroup(iso: string, now: Date = new Date()): string {
  const key = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: IST }).format(d); // yyyy-mm-dd
  const d = new Date(iso);
  const days = Math.round((Date.parse(key(now)) - Date.parse(key(d))) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days <= 7) return "Previous 7 days";
  if (days <= 30) return "Previous 30 days";
  return new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: IST }).format(d);
}

/** Masked identifier: "ending 2914". Full numbers are never stored or shown. */
export function masked(last4: string | null | undefined): string {
  return last4 ? `ending ${last4}` : "";
}
