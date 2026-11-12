import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api } from "@/lib/api";
import type { Nudge } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * The inbox: at most four kinds of reminder, shown only here, each dismissible and each with a switch in settings.
 * `floating` is the phone version, a small button that appears only when there is something to read.
 */
export function Nudges({ floating = false }: { floating?: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ["nudges"], queryFn: () => api.get<Nudge[]>("/api/nudges"), staleTime: 5 * 60_000 });
  const dismiss = useMutation({
    mutationFn: (id: string) => api.post("/api/nudges/dismiss", { id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["nudges"] }),
  });
  const items = q.data ?? [];
  const n = items.length;
  if (floating && n === 0) return null;
  const label = n === 0 ? "Reminders: none" : `Reminders: ${n}`;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          aria-label={label}
          className={cn(
            floating
              ? "fixed right-3 top-3 z-30 grid size-10 place-items-center rounded-full border bg-card shadow-md md:hidden"
              : "relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground",
          )}
        >
          <span className="relative">
            <Bell className="size-5" aria-hidden />
            {n > 0 && <span className="num absolute -right-1.5 -top-1.5 grid min-w-4 place-items-center rounded-full bg-primary px-1 text-[10px] font-bold leading-4 text-primary-foreground" aria-hidden>{n}</span>}
          </span>
          {!floating && <span className="hidden xl:inline">Reminders</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent align={floating ? "end" : "start"} side={floating ? "bottom" : "right"} className="w-[min(92vw,22rem)] p-0">
        <p className="border-b px-4 py-3 text-sm font-bold">Reminders</p>
        {n === 0 ? (
          <p className="px-4 py-5 text-sm text-muted-foreground">Nothing needs your attention.</p>
        ) : (
          <ul className="max-h-[60vh] divide-y overflow-y-auto">
            {items.map((x) => (
              <li key={x.id} className="px-4 py-3">
                <p className="text-sm font-semibold">{x.title}</p>
                <p className="mt-0.5 text-sm text-muted-foreground">{x.body}</p>
                <div className="mt-2 flex gap-2">
                  {x.tab ? (
                    <Link to="/money" search={{ tab: x.tab }} onClick={() => setOpen(false)} className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">Open</Link>
                  ) : (
                    <Link to="/" onClick={() => setOpen(false)} className="rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">Open</Link>
                  )}
                  <button disabled={dismiss.isPending} onClick={() => dismiss.mutate(x.id)} className="rounded-full border px-3 py-1 text-xs font-semibold hover:bg-surface-2">Dismiss</button>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="border-t px-4 py-2.5 text-xs text-muted-foreground">
          Shown here only. <Link to="/settings" onClick={() => setOpen(false)} className="font-semibold text-brand">Choose which ones</Link>
        </p>
      </PopoverContent>
    </Popover>
  );
}
