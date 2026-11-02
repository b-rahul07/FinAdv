import { useState } from "react";
import { ProfileForm } from "@/features/profile/ProfileForm";
import { Questionnaire } from "@/features/profile/Questionnaire";
import type { ProfileCardT } from "@/lib/types";
import { CardShell } from "./AdviceCards";

const FIELD: Record<string, string> = {
  take_home_monthly: "take-home pay",
  expenses_monthly: "expenses",
  liquid_savings: "emergency savings",
  dependants: "dependants",
  life_cover: "life cover",
  health_cover: "health cover",
  card_dues_paid_in_full: "card payments",
  experience: "investing experience",
  debts: "loans",
  goals: "goals",
  age: "age",
};

export function ChatProfileCard({ card, onConfirmed }: { card: ProfileCardT; onConfirmed: () => void }) {
  const [done, setDone] = useState(false);
  if (done)
    return (
      <CardShell eyebrow="Profile card" title="Confirmed">
        <p className="text-sm text-muted-foreground">Saved as a new profile version. FinAdvisor will use it from now on.</p>
      </CardShell>
    );
  return (
    <CardShell
      eyebrow="Profile card · check before confirming"
      title={card.changed.length ? `I picked up: ${card.changed.map((c) => FIELD[c] ?? c).join(", ")}` : "Your financial profile"}
    >
      <ProfileForm
        compact
        initial={card.proposed}
        changed={card.changed}
        onSaved={() => {
          setDone(true);
          onConfirmed();
        }}
      />
    </CardShell>
  );
}

export function ChatQuestionnaireCard({ onDone }: { onDone: () => void }) {
  const [done, setDone] = useState(false);
  return (
    <CardShell eyebrow="13 questions · about 3 minutes" title={done ? "Thanks, saved" : "How comfortable are you with risk?"}>
      {done ? (
        <p className="text-sm text-muted-foreground">Your answers are saved with your profile.</p>
      ) : (
        <Questionnaire
          onDone={() => {
            setDone(true);
            onDone();
          }}
        />
      )}
    </CardShell>
  );
}
