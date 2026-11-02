import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { ProfileView, QItem } from "@/lib/types";
import { cn } from "@/lib/utils";

type Q = { version: string; attribution: string; items: QItem[] };

/** Grable & Lytton 13-item scale, one question at a time (VELTO-style stepped flow). */
export function Questionnaire({ onDone }: { onDone?: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["questionnaire"], queryFn: () => api.get<Q>("/api/questionnaire") });
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => api.get<ProfileView>("/api/profile") });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [step, setStep] = useState(0);
  const save = useMutation({
    mutationFn: () => {
      const data = { ...profile.data!.data, gl_answers: answers };
      return api.put<ProfileView>("/api/profile", { data, sources: { ...profile.data!.sources, gl_answers: "user" } });
    },
    onSuccess: (v) => {
      qc.setQueryData(["profile"], v);
      toast.success(`Saved. Willingness to take risk: ${v.willingness?.level}`);
      onDone?.();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  if (!q.data || !profile.data) return <div className="skeleton h-48" />;
  const items = q.data.items;
  const item = items[step];
  const chosen = answers[String(item.n)];
  const last = step === items.length - 1;

  return (
    <div>
      <div className="mb-5 flex gap-1" aria-hidden>
        {items.map((_, i) => (
          <span key={i} className={cn("h-1 flex-1 rounded-full", i <= step ? "bg-primary" : "bg-surface-2")} />
        ))}
      </div>
      <p className="eyebrow">
        {String(step + 1).padStart(2, "0")} / {items.length} · Comfort with risk
      </p>
      <fieldset className="mt-2">
        <legend className="text-lg font-bold leading-snug">{item.text}</legend>
        <div role="radiogroup" className="mt-4 space-y-2">
          {item.options.map((o) => (
            <button
              key={o.key}
              type="button"
              role="radio"
              aria-checked={chosen === o.key}
              onClick={() => setAnswers((a) => ({ ...a, [String(item.n)]: o.key }))}
              className={cn(
                "w-full rounded-xl border px-4 py-3 text-left text-sm transition-colors",
                chosen === o.key ? "border-primary bg-surface-2 font-semibold" : "hover:bg-surface-2/60",
              )}
            >
              {o.text}
            </button>
          ))}
        </div>
      </fieldset>
      <div className="mt-5 flex justify-between gap-3">
        <Button variant="ghost" className="rounded-full" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
          Back
        </Button>
        {last ? (
          <Button className="rounded-full px-6" disabled={Object.keys(answers).length < items.length || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save answers"}
          </Button>
        ) : (
          <Button className="rounded-full px-6" disabled={!chosen} onClick={() => setStep((s) => s + 1)}>
            Next
          </Button>
        )}
      </div>
      <p className="mt-5 text-xs text-muted-foreground">{q.data.attribution}</p>
    </div>
  );
}
