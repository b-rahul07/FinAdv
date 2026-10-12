/**
 * Evidence Panel Component
 * ========================
 * This component renders the right-hand "Evidence Trail" drawer/sidebar.
 * In a traditional black-box LLM, the user cannot see why the model made a recommendation.
 * Ledgerly solves this by displaying all underlying evidence side-by-side:
 *   1. The deterministic suitability rule that fired (e.g., TAX_80C, LOW_RISK_CAPITAL_PRESERVATION).
 *   2. The FinBERT sentiment score and the live financial headlines analyzed.
 *   3. The exact chunks retrieved from the ChromaDB vector database.
 *   4. The anti-hallucination provenance check results.
 */

import { useEffect, useRef } from "react";
import { FileText, Gauge, ScrollText, ShieldCheck, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { RecommendationResponse } from "@/lib/advisor/types";

// Properties passed from the parent chat window
type Props = {
  data: RecommendationResponse | null; // The recommendation result with evidence
  activeChunkId: string | null;         // The chunk ID clicked by the user in the text
  onClose?: () => void;                 // Optional callback when closed on mobile
};

export function EvidencePanel({ data, activeChunkId, onClose }: Props) {
  // Store DOM references to each citation card so we can smoothly scroll to it when clicked
  const refs = useRef<Record<string, HTMLDivElement | null>>({});

  // When the user clicks an inline citation [1] in the recommendation text,
  // this effect automatically scrolls the corresponding source chunk into view
  // and highlights it briefly with a yellow pulse animation.
  useEffect(() => {
    if (!activeChunkId) return;
    const el = refs.current[activeChunkId];
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("evidence-highlight");
    const t = setTimeout(() => el.classList.remove("evidence-highlight"), 1500);
    return () => clearTimeout(t);
  }, [activeChunkId]);

  return (
    <aside className="flex h-full w-full flex-col border-l border-border bg-surface">
      {/* Panel Header */}
      <header className="flex items-center justify-between gap-2 border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-evidence" />
          <h2 className="text-sm font-semibold tracking-tight">Evidence trail</h2>
        </div>
        {onClose ? (
          <Button variant="ghost" size="icon" className="size-7" onClick={onClose}>
            <X className="size-4" />
          </Button>
        ) : null}
      </header>

      {/* Scrollable Content Body */}
      <ScrollArea className="flex-1">
        <div className="space-y-6 px-5 py-5">
          {/* Empty state: Shown before the user completes their recommendation */}
          {!data ? (
            <p className="text-sm leading-relaxed text-muted-foreground">
              Every recommendation is traced back here — the documents it drew on, the market
              sentiment signal, and the rule that fired. Nothing is asserted without a source.
            </p>
          ) : (
            <>
              {/* SECTION 1: Deterministic Rule Audit */}
              {data.rule_fired ? (
                <section>
                  <SectionTitle icon={<ScrollText className="size-3.5" />} text="Rule fired" />
                  <div className="rounded-lg border border-border bg-surface-2 p-4">
                    <Badge variant="outline" className="mb-2 font-mono text-[0.65rem]">
                      {data.rule_fired.rule_id}
                    </Badge>
                    <p className="text-sm leading-relaxed">{data.rule_fired.description}</p>
                  </div>
                </section>
              ) : null}

              {/* SECTION 2: Market Sentiment (FinBERT + RSS Feeds) */}
              {data.sentiment_summary ? (
                <section>
                  <SectionTitle icon={<Gauge className="size-3.5" />} text="Sentiment signal" />
                  <div className="rounded-lg border border-border bg-surface-2 p-4">
                    <div className="flex items-baseline justify-between">
                      <span className="text-sm font-medium">{data.sentiment_summary.label}</span>
                      <span className="font-mono text-sm text-accent">
                        {data.sentiment_summary.score.toFixed(2)}
                      </span>
                    </div>
                    <Separator className="my-3" />
                    <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                      Headlines used
                    </p>
                    <ul className="space-y-1.5">
                      {data.sentiment_summary.headlines_used.map((h) => (
                        <li key={h} className="text-sm leading-relaxed text-muted-foreground">
                          {h}
                        </li>
                      ))}
                    </ul>
                  </div>
                </section>
              ) : null}

              {/* SECTION 3: RAG Retrieved Documents (ChromaDB Vector Chunks) */}
              <section>
                <SectionTitle icon={<FileText className="size-3.5" />} text="Source documents" />
                {data.evidence.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No evidence was attached to this response.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {data.evidence.map((chunk, i) => (
                      <div
                        key={chunk.chunk_id}
                        ref={(el) => {
                          refs.current[chunk.chunk_id] = el;
                        }}
                        className="rounded-lg border border-border bg-surface-2 p-4 transition-colors"
                      >
                        <div className="mb-2 flex items-start gap-2">
                          <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-md bg-evidence/20 text-[0.7rem] font-semibold text-evidence">
                            {i + 1}
                          </span>
                          <p className="text-sm font-medium leading-snug">
                            {chunk.source_document}
                          </p>
                        </div>
                        <p className="text-sm leading-relaxed text-muted-foreground">
                          {chunk.excerpt}
                        </p>
                        <p className="mt-2 font-mono text-[0.65rem] text-muted-foreground/70">
                          {chunk.chunk_id}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* SECTION 4: Anti-Hallucination & System Provenance Metadata */}
              {data.provenance ? (
                <section>
                  <SectionTitle icon={<ShieldCheck className="size-3.5" />} text="Provenance" />
                  <dl className="rounded-lg border border-border bg-surface-2 p-4 text-sm">
                    {Object.entries(data.provenance).map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-4 py-1">
                        <dt className="text-muted-foreground">{k.replace(/_/g, " ")}</dt>
                        <dd className="text-right font-mono text-xs">{String(v)}</dd>
                      </div>
                    ))}
                  </dl>
                </section>
              ) : null}
            </>
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}

/**
 * Small helper component for styled section headers inside the evidence panel
 */
function SectionTitle({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
      {icon}
      {text}
    </div>
  );
}
