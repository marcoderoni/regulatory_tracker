"""
notion_export.py — Push regulatory items to a Notion database.

Each FeedItem becomes a Notion page with:
  - Title (page title)
  - URL (external link)
  - Source (text)
  - Jurisdiction (select)
  - Category (select)
  - Regulations (multi-select, from ai_tags)
  - Relevance (number)
  - Published (date)
  - Action (text)
  - Summary (rich text in page body)
  - Deadlines (rich text in page body)

Setup:
  1. Create a Notion integration at https://www.notion.so/my-integrations
  2. Create a full-page database in Notion
  3. Share the database with your integration
  4. Copy the database ID (32-char string from the URL) → NOTION_DB_ID in .env
  5. Copy the integration secret → NOTION_API_KEY in .env
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from sources.rss_source import FeedItem

log = logging.getLogger(__name__)

_NOTION_URL = "https://api.notion.com/v1/pages"
_NOTION_VER = "2022-06-28"


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": _NOTION_VER,
    }


def _rich_text(text: str) -> list[dict]:
    """Helper: wrap plain text in Notion rich_text format (max 2000 chars)."""
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _build_page(item: "FeedItem", db_id: str) -> dict:
    deadlines_text = ""
    for dl in getattr(item, "deadlines", []):
        deadlines_text += f"• {dl['date']}: {dl['description']}\n"

    page: dict = {
        "parent": {"database_id": db_id},
        "icon":   {"type": "emoji", "emoji": "⚖️"},
        "properties": {
            "Name": {
                "title": _rich_text(item.title[:255])
            },
            "URL": {
                "url": item.url
            },
            "Source": {
                "rich_text": _rich_text(item.source_name)
            },
            "Jurisdiction": {
                "select": {"name": item.jurisdiction[:100]}
            },
            "Category": {
                "select": {"name": item.category[:100]}
            },
            "Regulations": {
                "multi_select": [{"name": t[:100]} for t in item.ai_tags[:10]]
            },
            "Relevance": {
                "number": item.ai_relevance
            },
            "Published": {
                "date": {"start": item.published.strftime("%Y-%m-%d")}
            },
            "Action": {
                "rich_text": _rich_text(item.ai_action or "")
            },
        },
        "children": [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": _rich_text("Summary")
                },
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": _rich_text(item.ai_summary or item.raw_summary[:2000])
                },
            },
        ],
    }

    if deadlines_text:
        page["children"] += [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": _rich_text("📅 Deadlines")},
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": _rich_text(deadlines_text)},
            },
        ]

    return page


def push_to_notion(
    items: list["FeedItem"],
    api_key: str,
    db_id: str,
) -> None:
    """Push a list of FeedItems to a Notion database. Each item = one page."""
    if not api_key or not db_id:
        log.debug("Notion export skipped: NOTION_API_KEY or NOTION_DB_ID not set.")
        return
    if not items:
        return

    headers = _headers(api_key)
    ok, failed = 0, 0

    for item in items:
        try:
            page = _build_page(item, db_id)
            resp = requests.post(_NOTION_URL, headers=headers, json=page, timeout=20)
            resp.raise_for_status()
            ok += 1
        except requests.HTTPError as e:
            log.warning(f"Notion push failed for '{item.title[:60]}': {e}")
            failed += 1
        except Exception as e:
            log.error(f"Notion unexpected error: {e}")
            failed += 1

    log.info(f"Notion export: {ok} pushed, {failed} failed")
