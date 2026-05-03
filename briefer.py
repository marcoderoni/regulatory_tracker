"""
briefer.py — On-demand topic brief generator via Gemini Flash 2.0.

Usage:
    python briefer.py "AI Act enforcement actions 2025"
    python briefer.py --list-presets
    python briefer.py ai-act --email
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

PRESETS: dict[str, str] = {
    "ai-act": (
        "Current status of EU AI Act implementation: prohibited AI practices (Art. 5), "
        "high-risk systems (Annex III), GPAI model obligations, EU AI Office activities, "
        "and enforcement timeline."
    ),
    "dora": (
        "EU DORA implementation: published RTS/ITS, outstanding delegated acts, "
        "EBA/ESMA/EIOPA Q&As, ICT risk management framework, TLPT regime, "
        "and key compliance deadlines for financial entities."
    ),
    "data-act": (
        "EU Data Act status: entry into force, application dates by provision, "
        "B2B data sharing obligations, B2G data sharing, cloud switching rights, "
        "smart contract requirements, and implementing acts."
    ),
    "nis2": (
        "NIS2 Directive: transposition status by EU Member State, essential vs important "
        "entity classification, incident reporting obligations (24h/72h/final), "
        "supply chain security, and national competent authority designations."
    ),
}


def _load_relevant_items(topic: str, db_path: Path, limit: int = 20) -> list[dict]:
    words = [w.strip().lower() for w in topic.split() if len(w) > 3]
    if not words:
        return []
    conditions = " OR ".join(["lower(title) LIKE ?" for _ in words])
    params     = [f"%{w}%" for w in words]
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT title, url, source_name, first_seen FROM seen_items "
                f"WHERE {conditions} ORDER BY first_seen DESC LIMIT ?",
                params + [limit],
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def generate_brief(topic: str, api_key: str, db_path: Path, topic_focus: list[str]) -> str:
    relevant = _load_relevant_items(topic, db_path)
    context_block = ""
    if relevant:
        lines = "\n".join(
            f"• [{r['first_seen'][:10]}] {r['title']} ({r['source_name']})"
            for r in relevant
        )
        context_block = f"\n\nRelevant items from our monitoring database:\n{lines}"

    prompt = (
        f"You are a Senior Legal Counsel at KPMG Netherlands advising SaaS and "
        f"cloud clients on EU regulatory compliance. Primary frameworks: {', '.join(topic_focus)}.\n\n"
        f"Produce a professional legal briefing on: \"{topic}\"{context_block}\n\n"
        f"Structure as HTML (inner content only, no html/body tags):\n"
        f"1. <h2>Executive Summary</h2> — 3-4 sentences\n"
        f"2. <h2>Current Status</h2>\n"
        f"3. <h2>Key Obligations / Requirements</h2> — use <ul>\n"
        f"4. <h2>Timeline & Deadlines</h2> — use <table>\n"
        f"5. <h2>Action Points for Legal/Compliance Team</h2> — use <ol>\n"
        f"6. <h2>Watch Points</h2>\n\n"
        f"Tone: concise, authoritative, KPMG advisory quality. "
        f"Reference specific articles where possible."
    )

    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 3000},
    }
    resp = requests.post(_GEMINI_URL, params={"key": api_key}, json=body, timeout=60)
    resp.raise_for_status()
    inner_html = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    date_str = datetime.now(timezone.utc).strftime("%d %B %Y")
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Legal Brief: {topic}</title>
<style>
  body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
          margin: 0 auto; padding: 40px; max-width: 820px;
          background: #fff; color: #333; line-height: 1.7; }}
  h1 {{ color: #1a1a2e; border-bottom: 3px solid #2980b9; padding-bottom: 10px; }}
  h2 {{ color: #1a1a2e; margin-top: 32px; border-bottom: 1px solid #eee; padding-bottom: 6px; }}
  ul, ol {{ padding-left: 20px; }} li {{ margin-bottom: 6px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 10px 14px; text-align: left; }}
  th {{ background: #f8f9fa; font-weight: 600; }}
  .disclaimer {{ background: #f8f9fa; border-left: 4px solid #e67e22;
                 padding: 12px 16px; font-size: 12px; color: #777; margin-top: 40px; }}
  @media print {{ body {{ padding: 20px; }} }}
</style>
</head>
<body>
  <div style="background:#1a1a2e;color:#fff;padding:24px 32px;
              margin:-40px -40px 32px;border-radius:0;">
    <div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;
                color:#8899aa;margin-bottom:6px;">
      Regulatory Intelligence Brief
    </div>
    <h1 style="margin:0;color:#fff;border:none;font-size:22px;">{topic}</h1>
    <div style="font-size:13px;color:#8bb8e8;margin-top:4px;">{date_str}</div>
  </div>
  {inner_html}
  <div class="disclaimer">
    <strong>Disclaimer:</strong> Generated by an AI-assisted regulatory monitoring tool
    for internal use only. Does not constitute legal advice. Verify against primary sources
    before client-facing use.
  </div>
</body>
</html>"""


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

    parser = argparse.ArgumentParser(description="Generate on-demand regulatory brief")
    parser.add_argument("topic", nargs="?", help="Topic or preset key")
    parser.add_argument("--output", "-o", help="Output HTML file")
    parser.add_argument("--email",  action="store_true", help="Send via Resend")
    parser.add_argument("--list-presets", action="store_true")
    args = parser.parse_args()

    if args.list_presets:
        for key, desc in PRESETS.items():
            print(f"  {key:<15} {desc[:70]}...")
        sys.exit(0)

    if not args.topic:
        parser.print_help()
        sys.exit(1)

    import config
    topic = PRESETS.get(args.topic, args.topic)
    print(f"Generating brief: {topic[:80]}...")

    html = generate_brief(topic, config.GEMINI_API_KEY, config.DB_PATH, config.TOPIC_FOCUS)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    slug     = topic[:40].replace(" ", "_").replace("/", "-").lower()
    out_path = Path(args.output or f"brief_{slug}_{date_str}.html")
    out_path.write_text(html, encoding="utf-8")
    print(f"Brief saved: {out_path}")

    if args.email:
        from emailer import send_email
        send_email(
            html_body=html,
            subject=f"📋 Regulatory Brief: {topic[:60]}",
            email_from=config.EMAIL_FROM,
            email_to=config.EMAIL_TO,
            resend_api_key=config.RESEND_API_KEY,
        )
        print("Brief emailed.")
