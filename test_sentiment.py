"""
Quick Test Utility: Live Headline Fetcher & FinBERT Sentiment Analysis
=====================================================================
Run this script to verify:
  1. Live RSS headline fetching from Economic Times & Moneycontrol.
  2. FinBERT sentiment classification (Positive / Neutral / Negative).
  3. Aggregate market sentiment scoring (-1.0 to +1.0).

Usage:
  python test_sentiment.py
"""

from sentiment.headline_fetcher import fetch_headlines
from sentiment.agent import analyze_sentiment


def test_headline_fetcher():
    print("=" * 70)
    print("1. TESTING LIVE RSS HEADLINE RETRIEVAL (Economic Times & Moneycontrol)")
    print("=" * 70)
    
    topics = ["market", "mutual fund"]
    for topic in topics:
        print(f"\nSearching headlines for topic: '{topic}'...")
        headlines = fetch_headlines(topic=topic, max_results=3)
        print(f"-> Successfully fetched {len(headlines)} headlines:")
        for idx, h in enumerate(headlines, 1):
            print(f"  [{idx}] Source: {h['source']}")
            print(f"      Title:  {h['headline']}")
            print(f"      Time:   {h['timestamp']}\n")


def test_finbert_sentiment():
    print("=" * 70)
    print("2. TESTING FINBERT SENTIMENT SCORING (ProsusAI/finbert)")
    print("=" * 70)
    
    topic = "market"
    print(f"\nRunning FinBERT model on topic '{topic}'...")
    summary = analyze_sentiment(topic=topic, max_headlines=3)
    
    print("\n" + "-" * 70)
    print(f"AGGREGATED SENTIMENT: {summary.overall_sentiment.upper()} (Score: {summary.overall_score:+.4f})")
    print(f"Headlines Analyzed:   {summary.num_headlines}")
    print("-" * 70)
    
    print("\nIndividual Headline Breakdowns:")
    for idx, item in enumerate(summary.individual_results, 1):
        print(f"  [{idx}] [{item.sentiment.upper():<8} | Conf: {item.confidence*100:5.1f}%] {item.headline}")
    
    print("\n" + "=" * 70)
    print("TEST PASSED: Both headline retrieval and FinBERT sentiment work!")
    print("=" * 70)


if __name__ == "__main__":
    test_headline_fetcher()
    test_finbert_sentiment()
