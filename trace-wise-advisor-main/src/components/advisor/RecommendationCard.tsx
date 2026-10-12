/**
 * Recommendation Card Component
 * ==============================
 * This component renders the final synthesized financial recommendation from the LLM.
 * 
 * Special Interactive Feature (Anti-Hallucination Citations):
 * Instead of presenting a wall of unverifiable text, the recommendation contains
 * numeric footnote citations like [1], [2].
 * This component parses those markers with a regular expression and replaces them
 * with interactive chip buttons. When clicked, it activates the `EvidencePanel` to
 * scroll directly to the exact source chunk that justified that specific sentence!
 */

import { Fragment } from "react";
import { Sparkle } from "lucide-react";
import type { RecommendationResponse } from "@/lib/advisor/types";

// Properties accepted by RecommendationCard
type Props = {
  data: RecommendationResponse;       // Complete recommendation payload (text, evidence, rule, sentiment)
  onCite: (chunkId: string) => void;  // Callback when a user clicks on a footnote marker [n]
};

export function RecommendationCard({ data, onCite }: Props) {
  // Normalize text: converts raw [CHUNK_ID: xyz] tags into numbered [1], [2] badges,
  // and cleans up internal [RULE_ID: ...] tags so the text is pristine and interactive.
  const normalizedText = normalizeRecommendationText(data.recommendation_text, data.evidence);

  // Check if the recommendation text contains inline citation brackets like [1] or [2]
  const hasInlineCitations = /\[\d+\]/.test(normalizedText);

  return (
    <div className="rounded-2xl border border-border bg-card p-6">
      {/* Header Badge */}
      <div className="mb-4 flex items-center gap-2">
        <Sparkle className="size-4 text-primary" />
        <h3 className="text-sm font-semibold uppercase tracking-wider text-primary">
          Your recommendation
        </h3>
      </div>

      {/* Main Recommendation Text Body (split into clean paragraphs) */}
      <div className="space-y-4 text-[0.95rem] leading-7">
        {normalizedText.split(/\n\n+/).map((para, i) => (
          <p key={i}>{renderWithCitations(para, data, onCite)}</p>
        ))}
      </div>

      {/* Fallback Citation List: If LLM didn't format inline [n] markers, show list at bottom */}
      {!hasInlineCitations && data.evidence.length > 0 ? (
        <div className="mt-6 border-t border-border pt-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Evidence used
          </p>
          <ul className="space-y-1.5">
            {data.evidence.map((c, i) => (
              <li key={c.chunk_id}>
                <button
                  type="button"
                  onClick={() => onCite(c.chunk_id)}
                  className="text-left text-sm text-evidence underline-offset-4 hover:underline"
                >
                  {i + 1}. {c.source_document}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Mandatory SEBI / Legal Disclaimer Footer */}
      <p className="mt-6 text-xs leading-relaxed text-muted-foreground">
        Educational suitability guidance only — not investment advice, and no returns are
        guaranteed.
      </p>
    </div>
  );
}

/**
 * Normalizes raw LLM output text by mapping [CHUNK_ID: ...] tags into clean [1], [2]
 * citation numbers based on their position in the evidence list, and cleans up raw rule tags.
 */
function normalizeRecommendationText(
  raw: string,
  evidence: RecommendationResponse["evidence"],
): string {
  if (!raw) return "";

  // Build a lookup map from chunk_id to its 1-based index in the evidence array
  const chunkMap = new Map<string, number>();
  evidence.forEach((c, idx) => {
    chunkMap.set(c.chunk_id.trim(), idx + 1);
  });

  // Convert [CHUNK_ID: some_chunk_id] to [1], [2], etc.
  let text = raw.replace(/\[CHUNK_ID:\s*([^\]]+)\]/g, (_, id) => {
    const idx = chunkMap.get(id.trim());
    return idx ? ` [${idx}]` : "";
  });

  // Strip internal rule ID tags (e.g., [RULE_ID: rule_80c_limit]) from user-facing narrative
  text = text.replace(/\[RULE_ID:\s*[^\]]+\]/g, "");

  // Clean up punctuation artifacts like " , " or ", ," left behind by tag replacement
  text = text.replace(/\s+,\s+/g, ", ").replace(/,\s*,/g, ",");
  return text.trim();
}

/**
 * Parses raw text with regular expression /(\[\d+\])/g
 * Splits strings like:
 * "Invest in ELSS funds [1] for tax savings under 80C [2]."
 * into alternating text segments and clickable interactive badge buttons [1], [2].
 */
function renderWithCitations(
  text: string,
  data: RecommendationResponse,
  onCite: (chunkId: string) => void,
) {
  // Split paragraph by citation patterns e.g. [1], [2]
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    // Check if this chunk is a citation marker
    const match = /^\[(\d+)\]$/.exec(part);
    if (!match) return <Fragment key={i}>{part}</Fragment>;

    // Convert 1-based index (e.g. [1]) to 0-based array index (0)
    const idx = Number(match[1]) - 1;
    const chunk = data.evidence[idx];
    if (!chunk) return <Fragment key={i}>{part}</Fragment>;

    // Render an interactive badge button linking to the source chunk
    return (
      <button
        key={i}
        type="button"
        className="trace-marker mx-0.5 inline-flex items-center justify-center rounded bg-evidence/20 px-1.5 py-0.5 text-xs font-semibold text-evidence transition-colors hover:bg-evidence hover:text-white"
        title={chunk.source_document}
        onClick={() => onCite(chunk.chunk_id)}
      >
        {idx + 1}
      </button>
    );
  });
}
