"""
deadlines.py — Consultation deadline extractor via Gemini Flash 2.0.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from sources.rss_source import FeedItem

log = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

_SYSTEM = """You are an expert EU regulatory paralegal.
You receive a list of regulatory items (JSON array).
For each item, extract ALL dates and deadlines mentioned: consultation deadlines,
transposition deadlines, application dates, compliance deadlines, response windows.

Return a JSON array. Each element:
  {
    "id": <same integer id as input>,
    "deadlines": [
      {"date": "<human-readable date, e.g. '30 June 2025'>",
       "description": "<brief description of what the deadline is for>"}
    ]
  }

If no deadlines are found, return "deadlines": [].
Return ONLY valid JSON. No markdown fences, no preamble."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        inner = parts[1] if len(parts) > 1 else text
        if inner.startswith("json"):
            inner = inner[4:]
        return inner.strip()
    return text


def extract_deadlines(
    items: list["FeedItem"],
    api_key: str,
    batch_size: int = 15,
) -> list["FeedItem"]:
    indexed = [(i, item) for i, item in enumerate(items)
               if item.ai_summary or item.raw_summary]

    for batch_start in range(0, len(indexed), batch_size):
        batch = indexed[batch_start : batch_start + batch_size]

        payload = [
            {
                "id":   idx,
                "title": item.title,
                "text":  (item.ai_summary or item.raw_summary)[:600],
            }
            for idx, item in batch
        ]

        try:
            body = {
                "contents": [{
                    "role": "user",
                    "parts": [{"text": _SYSTEM + "\n\n" + json.dumps(payload)}],
                }],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
            }
            resp = requests.post(
                _GEMINI_URL,
                params={"key": api_key},
                json=body,
                timeout=60,
            )
            resp.raise_for_status()
            raw     = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            results = json.loads(_strip_fences(raw))
            result_map = {r["id"]: r for r in results}

            for idx, item in batch:
                item.deadlines = result_map.get(idx, {}).get("deadlines", [])

        except Exception as e:
            log.warning(f"Deadline extraction error (batch {batch_start}): {e}")
            for _, item in batch:
                item.deadlines = []

    return items


def save_calendar(items: list["FeedItem"], path: Path = Path("deadlines_calendar.json")) -> None:
    calendar: list[dict] = []
    for item in items:
        for dl in getattr(item, "deadlines", []):
            calendar.append({
                "date":         dl["date"],
                "description":  dl["description"],
                "source":       item.title,
                "url":          item.url,
                "tags":         item.ai_tags,
                "jurisdiction": item.jurisdiction,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            })

    calendar.sort(key=lambda x: x["date"])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(calendar, f, indent=2, ensure_ascii=False)

    log.info(f"Deadlines calendar saved: {len(calendar)} entries → {path}")
    if calendar:
        print(f"\n📅 {len(calendar)} consultation deadline(s) extracted:")
        for d in calendar[:10]:
            print(f"   {d['date']:20s}  {d['description'][:70]}")
        if len(calendar) > 10:
            print(f"   ... and {len(calendar) - 10} more. See {path}")
