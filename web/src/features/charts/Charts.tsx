import { useEffect, useState } from "react";
import { Area, CartesianGrid, Cell, ComposedChart, Line, Pie, PieChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { date, inr, inrAxis, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

// Asset classes take the validated categorical slots in fixed order (never cycled, never re-ranked).
export const CLASS_META: Record<string, { label: string; slot: number }> = {
  stocks: { label: "Stocks", slot: 1 },
  mutual_funds: { label: "Mutual funds", slot: 2 },
  deposits: { label: "Deposits", slot: 3 },
  gold: { label: "Gold", slot: 4 },
  cash: { label: "Cash", slot: 5 },
  retirement: { label: "Retirement", slot: 6 },
  silver: { label: "Silver", slot: 7 },
  other: { label: "Other", slot: 8 },
};
const ORDER = Object.keys(CLASS_META);

/** Animate charts only on first mount and only without reduced motion (brief §4.3). */
function useDrawOnce() {
  const [anim, setAnim] = useState(() => !matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const t = setTimeout(() => setAnim(false), 900);
    return () => clearTimeout(t);
  }, []);
  return anim;
}

const axisTick = { fill: "var(--muted-foreground)", fontSize: 12 };

export type SeriesPoint = { date: string; value: number; net_invested: number; benchmark?: number | null; missing?: number };

export function ValueChart({ points, benchmarkLabel }: { points: SeriesPoint[]; benchmarkLabel?: string | null }) {
  const anim = useDrawOnce();
  const hasBench = points.some((p) => p.benchmark != null);
  return (
    <div>
      <div className="h-64 md:h-72" role="img" aria-label="Portfolio value over time">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="fa-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.18} />
                <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--border)" strokeWidth={1} />
            <XAxis dataKey="date" tick={axisTick} tickLine={false} axisLine={false} minTickGap={48}
              tickFormatter={(d) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(new Date(d))} />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} width={64} tickFormatter={inrAxis} domain={["auto", "auto"]} />
            <Tooltip content={<ValueTip />} cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }} />
            <Area type="monotone" dataKey="value" name="Portfolio value" stroke="var(--series-1)" strokeWidth={2} fill="url(#fa-area)" isAnimationActive={anim} dot={false} activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }} />
            <Line type="stepAfter" dataKey="net_invested" name="Money put in" stroke="var(--muted-foreground)" strokeWidth={1.5} dot={false} isAnimationActive={anim} />
            {hasBench && <Line type="monotone" dataKey="benchmark" name="Nifty 50, same money" stroke="var(--series-7)" strokeWidth={2} dot={false} isAnimationActive={anim} connectNulls />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground" aria-label="Legend">
        <li className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-series-1" aria-hidden />Portfolio value</li>
        <li className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-muted-foreground" aria-hidden />Money put in</li>
        {hasBench && <li className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded bg-series-7" aria-hidden />Nifty 50, same money on the same dates</li>}
      </ul>
      {hasBench && benchmarkLabel && <p className="mt-1 text-xs text-muted-foreground">{benchmarkLabel}</p>}
    </div>
  );
}

function ValueTip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as SeriesPoint;
  return (
    <div className="rounded-xl border bg-card px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-semibold">{date(p.date)}</p>
      <p className="num">Value: <strong>{inr(p.value)}</strong></p>
      <p className="num text-muted-foreground">Money put in: {inr(p.net_invested)}</p>
      {p.benchmark != null && <p className="num text-muted-foreground">Nifty 50, same money: {inr(p.benchmark)}</p>}
      {!!p.missing && <p className="mt-1 text-muted-foreground">{p.missing} holding(s) had no price yet on this day.</p>}
    </div>
  );
}

export function AllocationDonut({ data }: { data: { asset_class: string; value: number; share: number }[] }) {
  const anim = useDrawOnce();
  const rows = [...data].sort((a, b) => ORDER.indexOf(a.asset_class) - ORDER.indexOf(b.asset_class));
  return (
    <div className="grid items-center gap-5 sm:grid-cols-[180px_1fr]">
      <div className="mx-auto h-44 w-44" role="img" aria-label={"Allocation: " + rows.map((r) => `${CLASS_META[r.asset_class].label} ${pct(r.share, 0)}`).join(", ")}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={rows} dataKey="value" nameKey="asset_class" innerRadius="62%" outerRadius="100%" startAngle={90} endAngle={-270}
              stroke="var(--card)" strokeWidth={2} isAnimationActive={anim}>
              {rows.map((r) => (
                <Cell key={r.asset_class} fill={`var(--series-${CLASS_META[r.asset_class].slot})`} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <table className="w-full text-sm">
        <caption className="sr-only">Allocation by asset class</caption>
        <tbody>
          {rows.map((r) => (
            <tr key={r.asset_class} className="border-b last:border-0">
              <th scope="row" className="py-2 text-left font-medium">
                <span className="inline-flex items-center gap-2">
                  <span className="size-2.5 rounded-full" style={{ background: `var(--series-${CLASS_META[r.asset_class].slot})` }} aria-hidden />
                  {CLASS_META[r.asset_class].label}
                </span>
              </th>
              <td className="num py-2 text-right text-muted-foreground">{inr(r.value)}</td>
              <td className="num w-16 py-2 text-right font-semibold">{pct(r.share, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PriceChart({ points, marks }: { points: { date: string; close: number }[]; marks: { date: string; kind: string; price: number }[] }) {
  const anim = useDrawOnce();
  const byDate = new Map(points.map((p) => [p.date, p.close]));
  const shown = marks.filter((m) => byDate.has(m.date) || (points.length && m.date >= points[0].date));
  return (
    <div className="h-72" role="img" aria-label="Daily closing price">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="date" tick={axisTick} tickLine={false} axisLine={false} minTickGap={48}
            tickFormatter={(d) => new Intl.DateTimeFormat("en-GB", { month: "short", year: "2-digit" }).format(new Date(d))} />
          <YAxis tick={axisTick} tickLine={false} axisLine={false} width={64} domain={["auto", "auto"]} tickFormatter={(v) => inr(v)} />
          <Tooltip content={({ active, payload }: any) => active && payload?.length ? (
            <div className="rounded-xl border bg-card px-3 py-2 text-xs shadow-lg">
              <p className="font-semibold">{date(payload[0].payload.date)}</p>
              <p className="num">Close {inr(payload[0].payload.close, 2)}</p>
            </div>) : null} cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }} />
          <Line type="monotone" dataKey="close" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={anim} activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }} />
          {shown.map((m, i) => (
            <ReferenceDot key={i} x={nearest(points, m.date)} y={byDate.get(nearest(points, m.date)) ?? m.price} r={5}
              fill={m.kind === "buy" ? "var(--series-3)" : "var(--series-2)"} stroke="var(--card)" strokeWidth={2} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function nearest(points: { date: string }[], d: string): string {
  const after = points.find((p) => p.date >= d);
  return after ? after.date : points[points.length - 1]?.date;
}

/** Where today's price sits in the 52-week range. Marker position plus text, never colour alone. */
export function RangeBar({ low, high, value, className }: { low: number; high: number; value: number | null; className?: string }) {
  const pos = value == null || high <= low ? null : Math.min(1, Math.max(0, (value - low) / (high - low)));
  return (
    <div className={cn("min-w-28", className)}>
      <div className="relative h-1.5 rounded-full bg-surface-2" aria-hidden>
        {pos != null && <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-foreground" style={{ left: `${pos * 100}%` }} />}
      </div>
      <div className="num mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span>{inr(low)}</span>
        <span>{inr(high)}</span>
      </div>
      <span className="sr-only">52-week low {inr(low)}, high {inr(high)}{pos != null ? `, today at ${Math.round(pos * 100)}% of the range` : ""}</span>
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: readonly T[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full bg-surface-2 p-1">
      {options.map((o) => (
        <button key={o} role="radio" aria-checked={value === o} onClick={() => onChange(o)}
          className={cn("rounded-full px-3 py-1 text-xs font-bold transition-colors", value === o ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>
          {o}
        </button>
      ))}
    </div>
  );
}
