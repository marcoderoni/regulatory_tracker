"""
sources/rss_source.py — Generic RSS/Atom feed fetcher.

Fetches all configured sources concurrently, normalises each entry
into a FeedItem dataclass, and filters out items older than the
lookback window.
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import requests

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "RegulatoryChangeTracker/1.0 (EU compliance monitoring; legal tool)"
}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class FeedItem:
    # Raw fields from the feed
    url:          str
    title:        str
    raw_summary:  str
    published:    datetime
    source_name:  str
    category:     str
    jurisdiction: str
    tags_hint:    list[str] = field(default_factory=list)

    # Filled in later by processor.py
    ai_summary:   str       = ""
    ai_tags:      list[str] = field(default_factory=list)
    ai_relevance: int       = 5    # 1–10
    ai_action:    str       = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(entry: Any) -> datetime:
    """Extract a timezone-aware datetime from a feedparser entry."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
            except (OverflowError, OSError):
                pass
    return datetime.now(timezone.utc)


def _clean_html(text: str, max_chars: int = 1000) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)   # basic HTML entities
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


# ── Fetcher ───────────────────────────────────────────────────────────────────

def fetch_source(source: dict, lookback_days: int = 7) -> list[FeedItem]:
    """
    Fetch a single RSS source and return items published within
    the lookback window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    items: list[FeedItem] = []

    try:
        resp = requests.get(
            source["rss_url"],
            headers=_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

        if feed.bozo and not feed.entries:
            log.warning(f"[{source['name']}] Feed parse error: {feed.bozo_exception}")
            return items

        for entry in feed.entries:
            pub = _parse_date(entry)
            if pub < cutoff:
                continue

            url = getattr(entry, "link", "") or getattr(entry, "id", "")
            if not url:
                continue

            raw_summary = (
                getattr(entry, "summary", "")
                or getattr(entry, "description", "")
                or getattr(entry, "content", [{}])[0].get("value", "")
                or ""
            )

            items.append(FeedItem(
                url          = url.strip(),
                title        = _clean_html(getattr(entry, "title", "No title"), 200),
                raw_summary  = _clean_html(raw_summary, 1000),
                published    = pub,
                source_name  = source["name"],
                category     = source["category"],
                jurisdiction = source["jurisdiction"],
                tags_hint    = source.get("tags_hint", []),
            ))

    except requests.RequestException as e:
        log.warning(f"[{source['name']}] HTTP error: {e}")
    except Exception as e:
        log.warning(f"[{source['name']}] Unexpected error: {e}", exc_info=True)

    log.info(f"[{source['name']}] {len(items)} item(s) within window")
    return items


def fetch_all_sources(
    sources: list[dict],
    lookback_days: int = 7,
    max_workers: int = 10,
) -> list[FeedItem]:
    """
    Fetch all sources concurrently and return a merged, deduplicated list
    sorted newest-first.
    """
    all_items: list[FeedItem] = []
    seen_urls: set[str] = set()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(fetch_source, s, lookback_days): s["name"]
            for s in sources
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                for item in future.result():
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        all_items.append(item)
            except Exception as e:
                log.error(f"[{name}] future raised: {e}", exc_info=True)

    all_items.sort(key=lambda i: i.published, reverse=True)
    log.info(f"Total items after cross-source dedup: {len(all_items)}")
    return all_items
