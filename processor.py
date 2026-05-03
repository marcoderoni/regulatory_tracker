"""
processor.py — AI enrichment via Google Gemini Flash 2.0 (free tier).

Free tier: 1,500 requests/day — more than enough for daily regulatory monitoring.
Get your API key at: https://aistudio.google.com/apikey (free, Google account required)

For each new FeedItem, Gemini will:
  1. Write a concise 2-3 sentence plain-English summary
  2. Classify it against the EU regulation taxonomy
  3. Score relevance 1-10 for a Senior Commercial Legal Counsel
  4. Suggest one concrete action for the legal team
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from sources.rss_source import FeedItem

log = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

SYSTEM_PROMPT = """You are a senior EU regulatory intelligence analyst embedded in a Big 4 legal advisory team.
Your specialty is EU digital & financial regulation: GDPR, AI Act, DORA, NIS2, ePrivacy Directive,
Data Act, Cyber Resilience Act, FIDA, PSD3/PSR, AML Package, Digital Markets Act, Digital Services Act.

You receive a JSON array of regulatory items (news, publications, official documents).
For EACH item return a JSON object with these fields:

  "id"        : integer — same id as in the input
  "summary"   : string — 2-3 sentences in plain English explaining what was published,
                what changed, and why it matters for SaaS/cloud operators in the EU.
  "tags"      : array of strings — pick ALL applicable labels from this exact list:
                [GDPR, AI Act, DORA, NIS2, ePrivacy, Data Act, Cyber Resilience Act,
                 FIDA, PSD3 / PSR, AML Package, Digital Markets Act, Digital Services Act, Other]
  "relevance" : integer 1-10 — how critical for a Senior Commercial Legal Counsel
                at KPMG Netherlands advising SaaS and cloud clients on EU compliance?
                10 = must-act (new RTS, enforcement decision, consultation deadline),
                1  = tangentially related background piece.
  "action"    : string — one specific action sentence for the legal team.
                Use "No immediate action required." if nothing to do.

Return ONLY a valid JSON array — no markdown fences, no preamble, no commentary."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        inner = parts[1] if len(parts) > 1 else text
        if inner.startswith("json"):
            inner = inner[4:]
        return inner.strip()
    return text


def _call_gemini(payload: list[dict], api_key: str) -> list[dict]:
    """Single Gemini API call. Returns parsed list of result dicts."""
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": SYSTEM_PROMPT + "\n\n" + json.dumps(payload, ensure_ascii=False)}
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
        },
    }

    resp = requests.post(
        _GEMINI_URL,
        params={"key": api_key},
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    raw  = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(_strip_fences(raw))


def process_items(
    items: list["FeedItem"],
    api_key: str,
    batch_size: int = 10,
) -> list["FeedItem"]:
    """
    Enrich every FeedItem with AI-generated summary, tags,
    relevance score, and recommended action.
    Items are modified in place and also returned.
    """
    if not items:
        return items

    indexed = list(enumerate(items))

    for batch_start in range(0, len(indexed), batch_size):
        batch = indexed[batch_start : batch_start + batch_size]

        payload = [
            {
                "id":       idx,
                "title":    item.title,
                "source":   item.source_name,
                "category": item.category,
                "hints":    item.tags_hint,
                "text":     item.raw_summary[:800],
            }
            for idx, item in batch
        ]

        try:
            results    = _call_gemini(payload, api_key)
            result_map = {r["id"]: r for r in results}

            for idx, item in batch:
                r = result_map.get(idx, {})
                item.ai_summary   = r.get("summary", item.raw_summary[:250])
                item.ai_tags      = r.get("tags", item.tags_hint or ["Other"])
                item.ai_relevance = max(1, min(10, int(r.get("relevance", 5))))
                item.ai_action    = r.get("action", "")

            log.info(f"Batch {batch_start}–{batch_start + len(batch) - 1} enriched OK")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            log.error(f"Gemini response parse error (batch {batch_start}): {e}")
        except requests.HTTPError as e:
            log.error(f"Gemini API HTTP error (batch {batch_start}): {e}")
        except Exception as e:
            log.error(f"Unexpected error (batch {batch_start}): {e}", exc_info=True)

    return items
