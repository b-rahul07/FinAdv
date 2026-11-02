import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, BookOpen, ChevronDown, ExternalLink, Minus, Newspaper } from "lucide-react";
import { useState } from "react";
import { Pill } from "@/components/common";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { date, dateTime } from "@/lib/format";
import type { EvidenceCard, Headline } from "@/lib/types";
import { cn } from "@/lib/utils";

const MOOD: Record<string, { label: string; icon: typeof Minus; cls: string }> = {
  positive: { label: "Positive", icon: ArrowUpRight, cls: "text-good" },
  negative: { label: "Negative", icon: ArrowDownRight, cls: "text-loss" },
  neutral: { label: "Neutral", icon: Minus, cls: "text-muted-foreground" },
  mixed: { label: "Mixed", icon: Minus, cls: "text-muted-foreground" },
};

/** "What I looked at": library passages and market headlines behind a Plan or Check answer. */
export function EvidenceView({ card }: { card: EvidenceCard }) {
  const [open, setOpen] = useState(false);
  const [reading, setReading] = useState<{ source: string; title: string } | null>(null);
  const news = card.news;
  const counts = [
    card.documents.length ? `${card.documents.length} document${card.documents.length === 1 ? "" : "s"}` : null,
    news?.items.length ? `${news.items.length} headline${news.items.length === 1 ? "" : "s"}` : null,
  ].filter(Boolean);
  return (
    <div className="rounded-xl border">
      <button className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm font-semibold" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span>
          What I looked at
          {counts.length > 0 && <span className="ml-2 font-normal text-muted-foreground">{counts.join(" · ")}</span>}
        </span>
        <ChevronDown className={cn("size-4 shrink-0 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className="space-y-5 border-t px-4 py-4 text-sm">
          {card.documents.length > 0 && (
            <section aria-labelledby="ev-docs">
              <h4 id="ev-docs" className="mb-2 flex items-center gap-2 font-semibold">
                <BookOpen className="size-4" aria-hidden /> From FinAdvisor's library
              </h4>
              <ol className="space-y-2">
                {card.documents.map((d) => (
                  <li key={d.n} className="rounded-lg bg-surface-2 px-3 py-2.5">
                    <div className="flex items-start justify-between gap-3">
                      <p className="font-medium">
                        <span className="num mr-1.5 text-muted-foreground">[{d.n}]</span>
                        {d.title}
                      </p>
                      <button className="shrink-0 rounded-md px-2 py-0.5 text-xs font-semibold text-primary underline-offset-2 hover:underline" onClick={() => setReading({ source: d.source, title: d.title })}>
                        Read
                      </button>
                    </div>
                    <p className="mt-1 text-muted-foreground">{d.snippet}</p>
                  </li>
                ))}
              </ol>
              <p className="mt-2 text-xs text-muted-foreground">{card.library}. Every number in your plan comes from FinAdvisor's calculators, not from these passages.</p>
            </section>
          )}
          {news && (
            <section aria-labelledby="ev-news">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h4 id="ev-news" className="flex items-center gap-2 font-semibold">
                  <Newspaper className="size-4" aria-hidden /> Market news I read
                </h4>
                {news.mood && <MoodPill mood={news.mood} prefix="Overall mood: " />}
              </div>
              {news.items.length === 0 ? (
                <p className="text-muted-foreground">No headlines are available right now; the news feed will refresh shortly.</p>
              ) : (
                <ul className="divide-y">
                  {news.items.map((h, i) => (
                    <HeadlineRow key={i} h={h} />
                  ))}
                </ul>
              )}
              <p className="mt-2 text-xs text-muted-foreground">
                {news.as_of ? `Headlines as of ${dateTime(news.as_of)}` : "Headlines not fetched yet"} · {news.source}
                {news.model ? ` · mood scored by FinBERT` : ""}
                {news.stale ? " · older than usual, the feed hasn't refreshed" : ""}
              </p>
              <p className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-xs">{news.note}</p>
            </section>
          )}
        </div>
      )}
      <DocumentDialog doc={reading} onClose={() => setReading(null)} />
    </div>
  );
}

function MoodPill({ mood, prefix = "" }: { mood: string; prefix?: string }) {
  const m = MOOD[mood] ?? MOOD.neutral;
  const Icon = m.icon;
  return (
    <Pill className="gap-1">
      <Icon className={cn("size-3.5", m.cls)} aria-hidden />
      {prefix}
      {m.label}
    </Pill>
  );
}

function HeadlineRow({ h }: { h: Headline }) {
  const m = h.mood ? MOOD[h.mood] : null;
  const Icon = m?.icon;
  return (
    <li className="flex items-start gap-3 py-2">
      <span className={cn("mt-0.5 flex w-[74px] shrink-0 items-center gap-1 text-xs font-semibold", m?.cls)}>
        {Icon && <Icon className="size-3.5" aria-hidden />}
        {m ? m.label : "—"}
      </span>
      <span className="min-w-0">
        {h.url ? (
          <a href={h.url} target="_blank" rel="noopener noreferrer" className="font-medium underline-offset-2 hover:underline">
            {h.headline}
            <ExternalLink className="ml-1 inline size-3 align-baseline text-muted-foreground" aria-label="(opens in a new tab)" />
          </a>
        ) : (
          <span className="font-medium">{h.headline}</span>
        )}
        <span className="block text-xs text-muted-foreground">
          {h.source}
          {h.published ? ` · ${dateTime(h.published)}` : ""}
        </span>
      </span>
    </li>
  );
}

function DocumentDialog({ doc, onClose }: { doc: { source: string; title: string } | null; onClose: () => void }) {
  const q = useQuery({
    queryKey: ["library", doc?.source],
    queryFn: () => api.get<{ title: string; text: string; updated: string }>(`/api/library/${encodeURIComponent(doc!.source)}`),
    enabled: !!doc,
    staleTime: Infinity,
  });
  return (
    <Dialog open={!!doc} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{doc?.title}</DialogTitle>
          <DialogDescription>From FinAdvisor's library of Indian regulatory and product guides.</DialogDescription>
        </DialogHeader>
        {q.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {q.isError && <p className="text-sm text-loss">This document couldn't be loaded. Try again in a moment.</p>}
        {q.data && (
          <>
            <p className="rounded-lg bg-warn-soft px-3 py-2 text-xs">
              Guide last updated {date(q.data.updated)}. Interest rates, limits and tax rules in it may have changed since; check the official source before
              acting. Your plan's numbers come from FinAdvisor's calculators, not from this guide.
            </p>
            <div className="whitespace-pre-wrap text-sm leading-relaxed">{q.data.text}</div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
