"""
Market Sentiment Agent (FinBERT)
==================================
This agent analyzes market psychology and news sentiment for Indian financial topics.
It uses ProsusAI/FinBERT — a BERT model specially pre-trained on tens of thousands
of financial news articles and earnings reports.

Why FinBERT instead of standard sentiment models?
  Standard NLP models often fail on financial text. For example, "Profits decreased"
  or "Liabilities rose" are clearly negative in finance, whereas "Shares traded flat"
  is neutral. FinBERT understands nuanced financial language.

Pipeline:
  1. Fetch recent headlines related to the query topic (e.g. "mutual fund", "gold", "SIP").
  2. Pass headlines through the Hugging Face FinBERT pipeline to obtain labels and confidence scores.
  3. Map labels to continuous scores: Positive (+confidence), Negative (-confidence), Neutral (0.0).
  4. Average the scores into an overall metric (-1.0 to +1.0) and assign an aggregated sentiment label.
"""

from dataclasses import dataclass
from transformers import pipeline
from sentiment.headline_fetcher import fetch_headlines
from config import FINBERT_MODEL


@dataclass
class SentimentResult:
    """
    Data model representing the sentiment analysis of an individual news headline.
    """
    headline: str           # The headline text
    source: str             # News publication or RSS source
    sentiment: str          # Model label: "positive", "negative", or "neutral"
    confidence: float       # Model probability score (0.0 to 1.0)
    timestamp: str          # Publication date/time


@dataclass
class SentimentSummary:
    """
    Aggregated market sentiment for a financial asset or topic across multiple headlines.
    """
    topic: str                                  # The financial topic searched
    overall_sentiment: str                      # Consolidated label: "positive", "negative", or "neutral"
    overall_score: float                        # Continuous score from -1.0 (bearish) to +1.0 (bullish)
    num_headlines: int                          # Total number of headlines evaluated
    individual_results: list[SentimentResult]   # Detailed breakdown per headline


# Singleton handle for lazy-loaded Hugging Face FinBERT pipeline
_classifier = None


def _get_classifier():
    """
    Lazily loads the FinBERT transformer model into memory on first invocation.
    Avoids expensive startup overhead until sentiment analysis is actually needed.
    """
    global _classifier
    if _classifier is None:
        _classifier = pipeline("sentiment-analysis", model=FINBERT_MODEL)
    return _classifier


def analyze_sentiment(
    topic: str,
    max_headlines: int = 10,
) -> SentimentSummary:
    """
    Fetches the latest financial headlines for a given topic and classifies sentiment.

    Scoring Logic:
      - Positive: +score (bullish signal)
      - Negative: -score (bearish signal)
      - Neutral:   0.0   (no strong directional sentiment)
      
    Consolidation:
      - Overall Score > +0.2  -> "positive"
      - Overall Score < -0.2  -> "negative"
      - Otherwise             -> "neutral"

    Parameters:
      topic: Asset or market subject (e.g. "equity mutual funds", "gold prices").
      max_headlines: Maximum number of recent news items to evaluate (default: 10).

    Returns:
      SentimentSummary object with scores and per-headline results.
    """
    # Step 1: Scrape or retrieve latest live financial headlines
    headlines = fetch_headlines(topic, max_results=max_headlines)

    # If no headlines could be retrieved (e.g. offline mode), return neutral fallback
    if not headlines:
        return SentimentSummary(
            topic=topic,
            overall_sentiment="neutral",
            overall_score=0.0,
            num_headlines=0,
            individual_results=[]
        )

    # Step 2: Run inference using FinBERT pipeline
    classifier = _get_classifier()
    texts = [h["headline"] for h in headlines]
    results = classifier(texts)

    individual_results = []
    score_sum = 0.0

    # Step 3: Compute continuous numeric score for each headline
    for h, res in zip(headlines, results):
        label = res["label"].lower()  # FinBERT outputs: "positive", "negative", "neutral"
        score = res["score"]

        # Map label and probability into a bipolar scale [-1.0, +1.0]
        if label == "positive":
            val = score
        elif label == "negative":
            val = -score
        else:
            val = 0.0

        score_sum += val

        individual_results.append(SentimentResult(
            headline=h["headline"],
            source=h["source"],
            sentiment=label,
            confidence=score,
            timestamp=h["timestamp"]
        ))

    # Step 4: Calculate the mathematical mean across all headlines
    overall_score = score_sum / len(individual_results)

    # Step 5: Assign consolidated market direction
    if overall_score > 0.2:
        overall_sentiment = "positive"
    elif overall_score < -0.2:
        overall_sentiment = "negative"
    else:
        overall_sentiment = "neutral"

    return SentimentSummary(
        topic=topic,
        overall_sentiment=overall_sentiment,
        overall_score=overall_score,
        num_headlines=len(individual_results),
        individual_results=individual_results
    )

