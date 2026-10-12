/**
 * Staged Progress Component (Pipeline Visualizer)
 * ===============================================
 * When the user confirms their profile, the backend takes a few seconds to run:
 *   1. Vector retrieval from ChromaDB
 *   2. FinBERT sentiment classification
 *   3. Deterministic SEBI suitability rules audit
 *   4. Ollama LLM recommendation generation & self-critique
 * 
 * This component displays an animated visual checklist showing each stage completing in real time,
 * providing immediate user feedback rather than an ambiguous loading spinner.
 */

import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";

// Human-readable labels for each pipeline step
const STAGES = [
  "Retrieving relevant documents…",
  "Checking market sentiment…",
  "Applying suitability rules…",
  "Generating your recommendation…",
];

export function StagedProgress() {
  // Current active stage index (0 to 3)
  const [stage, setStage] = useState(0);

  // Advances through the visual steps every 2.2 seconds while the backend completes the work
  useEffect(() => {
    const t = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 2200);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="rounded-2xl border border-border bg-card p-6">
      <ul className="space-y-3">
        {STAGES.map((label, i) => (
          <li key={label} className="flex items-center gap-3 text-sm">
            {/* Step Complete: Green checkmark */}
            {i < stage ? (
              <Check className="size-4 text-primary" />
            ) : i === stage ? (
              // Step In Progress: Spinning loader
              <Loader2 className="size-4 animate-spin text-primary" />
            ) : (
              // Step Pending: Empty circle
              <span className="size-4 rounded-full border border-border" />
            )}

            {/* Step Label */}
            <span className={i <= stage ? "text-foreground" : "text-muted-foreground"}>
              {label}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
