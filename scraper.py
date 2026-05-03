"""
scraper.py — Direct web scraper for sites without RSS feeds.

Scrapes the page, extracts headline links, fetches each page's
<title> and first meaningful paragraph, and converts them into
FeedItem objects compatible with the rest of the pipeline.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from sources.rss_source import FeedItem

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "RegulatoryChangeTracker/1.0 (EU compliance monitoring; legal tool)"
}
_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)


def _clean(text: str, max_chars: int = 800) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _fetch_page_details(url: str) -> tuple[str, str]:
    """
    Fetch a URL and return (title, first_paragraph).
    Returns ("", "") on any error.
    """
    try:
        resp = _SESSION.get(url, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        title = _clean(soup.title.get_text() if soup.title else "", 200)

        # Try structured content first, then fall back to any <p>
        para = ""
        for selector in [
            "article p", ".content p", ".main-content p",
            "#content p", ".body-text p", "main p", "p",
        ]:
            candidates = soup.select(selector)
            for p in candidates:
                text = _clean(p.get_text())
                if len(text) > 80:
                    para = text
                    break
            if para:
                break

        return title, para
    except Exception as e:
        log.debug(f"Could not fetch {url}: {e}")
        return "", ""


def _extract_links(target: dict) -> list[str]:
    """
    Fetch the target page and return a list of absolute URLs
    matching the configured CSS selector.
    """
    try:
        resp = _SESSION.get(target["url"], timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        links: list[str] = []
        seen:  set[str]  = set()

        for a in soup.select(target["link_selector"]):
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "javascript")):
                continue

            # Make absolute
            if href.startswith("http"):
                full = href
            else:
                full = urljoin(target.get("base_url", target["url"]), href)

            # Basic sanity: must share domain with base_url
            base_domain = urlparse(target.get("base_url", target["url"])).netloc
            if base_domain and base_domain not in urlparse(full).netloc:
                continue

            if full not in seen:
                seen.add(full)
                links.append(full)

        log.info(f"[{target['name']}] {len(links)} links found")
        return links[:20]   # cap per source

    except Exception as e:
        log.warning(f"[{target['name']}] scrape error: {e}")
        return []


def scrape_target(target: dict, known_urls: set[str]) -> list[FeedItem]:
    """
    Scrape one target and return FeedItem objects for new URLs.
    """
    links  = _extract_links(target)
    new    = [u for u in links if u not in known_urls]
    items: list[FeedItem] = []

    def _make_item(url: str) -> FeedItem | None:
        title, summary = _fetch_page_details(url)
        if not title and not summary:
            return None
        return FeedItem(
            url          = url,
            title        = title or url,
            raw_summary  = summary,
            published    = datetime.now(timezone.utc),
            source_name  = target["name"],
            category     = target["category"],
            jurisdiction = target["jurisdiction"],
            tags_hint    = target.get("tags_hint", []),
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_make_item, u): u for u in new}
        for future in as_completed(futures):
            result = future.result()
            if result:
                items.append(result)

    log.info(f"[{target['name']}] {len(items)} new scraped items")
    return items


def scrape_all_targets(
    targets: list[dict],
    known_urls: set[str],
    max_workers: int = 5,
) -> list[FeedItem]:
    """
    Scrape all configured targets concurrently.
    known_urls: set of URLs already in the database (to avoid reprocessing).
    """
    all_items: list[FeedItem] = []
    seen:      set[str]       = set(known_urls)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(scrape_target, t, seen): t["name"]
            for t in targets
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                for item in future.result():
                    if item.url not in seen:
                        seen.add(item.url)
                        all_items.append(item)
            except Exception as e:
                log.error(f"[{name}] scraper future error: {e}")

    log.info(f"Total scraped items: {len(all_items)}")
    return all_items
