/**
 * Profile Card Component (Human-in-the-Loop Review)
 * ==================================================
 * In Step 2 of the Ledgerly workflow, after the chatbot has asked all 7 elicitation
 * questions, this card renders the structured `UserProfile` inferred by the AI.
 * 
 * Crucially, this gives the user agency:
 *   - Every field can be clicked and edited inline (e.g., correcting an income number or risk tolerance).
 *   - When the user clicks "Confirm", the finalized profile is posted to the backend
 *     and triggers the RAG retrieval + LLM recommendation pipeline.
 */

import { useState } from "react";
import { Check, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PROFILE_FIELDS, type UserProfile } from "@/lib/advisor/types";

// Properties accepted by the ProfileCard component
type Props = {
  profile: UserProfile;                        // Profile object extracted from conversation
  confirmed: boolean;                          // Whether the user has already confirmed this profile
  loading?: boolean;                           // Loading spinner state while generating recommendations
  onConfirm: (profile: UserProfile) => void;   // Callback triggered when the confirm button is pressed
};

export function ProfileCard({ profile, confirmed, loading = false, onConfirm }: Props) {
  // Local editable draft state of the profile fields
  const [draft, setDraft] = useState<UserProfile>(profile);

  // Tracks which field is currently being edited (or null if none)
  const [editing, setEditing] = useState<keyof UserProfile | null>(null);

  // Helper function to update a specific profile attribute in state
  const set = (key: keyof UserProfile, value: string) =>
    setDraft((d) => ({ ...d, [key]: value }));

  return (
    <div className="rounded-2xl border border-accent/40 bg-card p-6">
      <h3 className="text-base font-semibold">Here's what we understood</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Please review and correct anything before we continue. Every field is editable.
      </p>

      {/* Grid of Profile Fields (Age, Horizon, Goal, Risk, etc.) */}
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        {PROFILE_FIELDS.map((field) => {
          const value = draft[field.key];
          const isEditing = editing === field.key && !confirmed;
          return (
            <div
              key={field.key}
              className="rounded-xl border border-border bg-surface-2 px-4 py-3"
            >
              {/* Field Label */}
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {field.label}
              </p>

              {/* Editable Mode: If the user clicked to edit this specific field */}
              {isEditing ? (
                field.options ? (
                  // Dropdown select for fields with preset choices (like risk tolerance)
                  <Select
                    defaultValue={String(value ?? "")}
                    onValueChange={(v) => {
                      set(field.key, v);
                      setEditing(null);
                    }}
                  >
                    <SelectTrigger className="mt-2 w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {field.options.map((o) => (
                        <SelectItem key={o} value={o}>
                          {o}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  // Free text input for numeric/open fields (like age, income, goal)
                  <div className="mt-2 flex gap-2">
                    <Input
                      autoFocus
                      value={String(value ?? "")}
                      onChange={(e) => set(field.key, e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && setEditing(null)}
                    />
                    <Button size="icon" variant="secondary" onClick={() => setEditing(null)}>
                      <Check className="size-4" />
                    </Button>
                  </div>
                )
              ) : (
                // View Mode: Click to activate inline editing
                <button
                  type="button"
                  disabled={confirmed}
                  onClick={() => setEditing(field.key)}
                  className="mt-1 flex w-full items-center justify-between gap-2 text-left text-sm font-medium disabled:cursor-default"
                >
                  <span>{value || "—"}</span>
                  {!confirmed ? (
                    <Pencil className="size-3.5 shrink-0 text-accent" />
                  ) : null}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Bottom Action Area: "Confirm Profile" button or "Confirmed" green checkmark */}
      {confirmed ? (
        <p className="mt-5 flex items-center gap-2 text-sm text-primary">
          <Check className="size-4" /> Profile confirmed
        </p>
      ) : (
        <Button
          className="mt-5 w-full sm:w-auto"
          disabled={loading}
          onClick={() => onConfirm(draft)}
        >
          {loading ? "Generating recommendation…" : "Confirm and get my recommendation"}
        </Button>
      )}
    </div>
  );
}
