import { useQueryClient } from "@tanstack/react-query";
import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { applyTheme, getThemePref, type ThemePref } from "@/lib/theme";
import { cn } from "@/lib/utils";

const OPTIONS: { v: ThemePref; label: string; icon: typeof Sun }[] = [
  { v: "light", label: "Light", icon: Sun },
  { v: "dark", label: "Dark", icon: Moon },
  { v: "system", label: "System", icon: Monitor },
];

export function useThemePref(): [ThemePref, (t: ThemePref) => void] {
  const qc = useQueryClient();
  const [pref, setPref] = useState<ThemePref>(getThemePref);
  useEffect(() => {
    const on = (e: Event) => setPref((e as CustomEvent).detail);
    window.addEventListener("fa-theme", on);
    return () => window.removeEventListener("fa-theme", on);
  }, []);
  return [
    pref,
    (t) => {
      applyTheme(t);
      api.put("/api/settings", { theme: t }).then(() => qc.invalidateQueries({ queryKey: ["me"] })).catch(() => {});
    },
  ];
}

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [pref, set] = useThemePref();
  if (compact) {
    const next: ThemePref = pref === "light" ? "dark" : pref === "dark" ? "system" : "light";
    const cur = OPTIONS.find((o) => o.v === pref)!;
    const Icon = cur.icon;
    return (
      <button
        onClick={() => set(next)}
        className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
        aria-label={`Theme: ${cur.label}. Switch to ${next}`}
      >
        <Icon className="size-5" aria-hidden />
        <span className="hidden xl:inline">Theme: {cur.label}</span>
      </button>
    );
  }
  return (
    <div role="radiogroup" aria-label="Appearance" className="inline-flex rounded-full border bg-surface-2 p-1">
      {OPTIONS.map(({ v, label, icon: Icon }) => (
        <button
          key={v}
          role="radio"
          aria-checked={pref === v}
          onClick={() => set(v)}
          className={cn(
            "flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors",
            pref === v ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
          )}
        >
          <Icon className="size-4" aria-hidden />
          {label}
        </button>
      ))}
    </div>
  );
}
