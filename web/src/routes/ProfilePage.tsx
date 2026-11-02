import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { ErrorState, PageHeader, Section, Skeleton } from "@/components/common";
import { cap } from "@/features/chat/cards/AdviceCards";
import { HealthCheckView } from "@/features/chat/cards/AdviceCards";
import { ProfileForm } from "@/features/profile/ProfileForm";
import { Questionnaire } from "@/features/profile/Questionnaire";
import { api } from "@/lib/api";
import type { ProfileView } from "@/lib/types";

export function ProfilePage() {
  const q = useQuery({ queryKey: ["profile"], queryFn: () => api.get<ProfileView>("/api/profile") });
  const [retake, setRetake] = useState(false);
  const [proposal, setProposal] = useState<{ proposed: ProfileView["data"]; changed: string[] } | null>(null);
  const loadProposal = () => api.get<{ proposed: ProfileView["data"]; changed: string[] }>("/api/profile/proposal").then((p) => {
    if (!p.changed.length) toast.info("Your profile already matches what you track.");
    else setProposal(p);
  });
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:px-8 md:py-10">
      <PageHeader eyebrow="One profile for every chat" title="Financial profile" />
      {q.isError && <ErrorState message="Could not load your profile." onRetry={() => q.refetch()} />}
      {q.isLoading && <Skeleton className="h-96" />}
      {q.data && (
        <div className="grid gap-4 lg:grid-cols-[1.7fr_1fr]">
          <Section eyebrow={q.data.version ? `Version ${q.data.version}` : "Not set up yet"} title="Your facts"
            action={<button onClick={loadProposal} className="rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2">Fill from what I track</button>}>
            {proposal && <p className="mb-4 rounded-xl bg-info-soft px-3 py-2 text-sm">Filled from your holdings, loans and insurance. Highlighted fields changed; check them and confirm to save.</p>}
            <ProfileForm key={(q.data.version ?? 0) + (proposal ? "-p" : "")} initial={proposal?.proposed ?? q.data.data} changed={proposal?.changed} onSaved={() => setProposal(null)} />
          </Section>
          <div className="space-y-4">
            <Section eyebrow="Willingness to take risk" title={q.data.willingness?.score ? `${cap(q.data.willingness.level)} (score ${q.data.willingness.score} of 47)` : "Not measured yet"}>
              {q.data.willingness?.capped_by_experience && (
                <p className="mb-3 text-sm text-muted-foreground">Your answers score {q.data.willingness.band_level}; it is capped at Medium until you have some investing experience.</p>
              )}
              {!q.data.version ? (
                <p className="text-sm text-muted-foreground">Confirm your facts first, then answer 13 short questions.</p>
              ) : retake || !q.data.willingness?.score ? (
                <Questionnaire onDone={() => setRetake(false)} />
              ) : (
                <button className="rounded-full border px-4 py-2 text-sm font-semibold hover:bg-surface-2" onClick={() => setRetake(true)}>
                  Retake the questionnaire
                </button>
              )}
            </Section>
            {q.data.health && <HealthCheckView card={q.data.health} />}
          </div>
        </div>
      )}
    </div>
  );
}
