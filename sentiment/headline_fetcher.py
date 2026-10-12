"""
Live Financial Headline Scraper (RSS Feeds)
=============================================
This module fetches live, real-time financial news headlines from leading Indian
financial publications (The Economic Times & Moneycontrol) using their public RSS feeds.

It feeds these headlines to the FinBERT Sentiment Agent so the advisor understands
current market sentiment before recommending equity, debt, or gold.

Features:
  - Connects to Economic Times (ET Markets) and Moneycontrol top news feeds.
  - Performs keyword matching on titles and article summaries for the requested topic.
  - Automatically falls back to broader market news if no topic-specific headlines are found.
"""

import feedparser
from datetime import datetime


def fetch_headlines(
    topic: str,
    max_results: int = 10,
    sources: list[str] | None = None,
) -> list[dict]:
    """
    Retrieves recent financial news headlines relevant to a specified investment topic.

    Parameters:
      topic: Keyword to filter headlines (e.g. "mutual fund", "gold", "Nifty").
             If blank, returns general market headlines.
      max_results: Maximum number of headline items to return (default: 10).
      sources: Optional custom RSS feed URLs.

    Returns:
      List of dictionaries, each containing:
        - "headline": Title of the news article
        - "source": Name of the publication (e.g. "ET Markets", "Moneycontrol")
        - "url": Hyperlink to the full article
        - "timestamp": Date and time published
    """
    # Authoritative RSS endpoints for Indian financial market news
    default_feeds = {
        "ET Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "Moneycontrol": "https://www.moneycontrol.com/rss/MCtopnews.xml"
    }

    feed_urls = sources if sources else list(default_feeds.values())

    all_headlines = []      # Headlines specifically matching the searched topic
    general_headlines = []  # All parsed headlines across the feeds (for fallback)

    # Iterate through all configured RSS feeds
    for url in feed_urls:
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue

        # Identify human-readable publisher name
        source_name = "Unknown RSS"
        for name, feed_url in default_feeds.items():
            if url == feed_url:
                source_name = name
                break

        # Process each individual article entry in the RSS XML feed
        for entry in feed.entries:
            title = getattr(entry, 'title', '')
            desc = entry.get('description', '')
            published = entry.get('published', datetime.now().isoformat())
            link = entry.get('link', '')

            headline_data = {
                "headline": title,
                "source": source_name,
                "url": link,
                "timestamp": published
            }

            general_headlines.append(headline_data)

            # Filter headlines: Check if the user's investment topic appears in headline or summary
            if topic:
                if topic.lower() in title.lower() or topic.lower() in desc.lower():
                    all_headlines.append(headline_data)
            else:
                all_headlines.append(headline_data)

            # Stop early once we reach the requested limit
            if len(all_headlines) >= max_results:
                return all_headlines

    # Fallback Mechanism:
    # If the user searched for a niche term that had zero matching headlines today,
    # return the overall top Indian market headlines so FinBERT can still gauge general market mood.
    if topic and not all_headlines:
        return general_headlines[:max_results]

    return all_headlines[:max_results]

