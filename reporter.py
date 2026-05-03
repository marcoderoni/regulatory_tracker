"""
reporter.py — Weekly HTML report generator via Gemini Flash 2.0.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)


def _load_week_items(db_path: Path, days: int = 7) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT url, title, source_name, category, jurisdiction, first_seen "
                "FROM seen_items WHERE first_seen >= ? ORDER BY first_seen DESC",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _generate_narrative(items: list[dict], api_key: str, topic_focus: list[str]) -> str:
    if not items:
        return "<p>No new regulatory items were tracked this week.</p>"

    payload = [
        {"title": i["title"], "source": i["source_name"], "category": i["category"]}
        for i in items[:40]
    ]
    prompt = (
        f"You are a senior EU regulatory counsel writing a weekly briefing.\n"
        f"Primary focus: {', '.join(topic_focus)}.\n\n"
        f"Regulatory items tracked this week:\n{json.dumps(payload, indent=2)}\n\n"
        f"Write a structured week-in-review in HTML (inner content only).\n"
        f"Use <h3> for section headers (one per major regulation), <p> for narrative.\n"
        f"3-5 sentences per section. End with 'Key watch points for next week'.\n"
        f"Tone: professional, concise, Big 4 legal advisory quality."
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2000},
    }
    resp = requests.post(_GEMINI_URL, params={"key": api_key}, json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _load_deadlines(path: Path = Path("deadlines_calendar.json")) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_weekly_report(db_path: Path, api_key: str, topic_focus: list[str], days: int = 7) -> str:
    items     = _load_week_items(db_path, days)
    narrative = _generate_narrative(items, api_key, topic_focus)
    deadlines = _load_deadlines()

    date_str  = datetime.now(timezone.utc).strftime("%d %B %Y")
    week_of   = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d %b")
    week_end  = datetime.now(timezone.utc).strftime("%d %b %Y")

    dl_rows = ""
    for d in deadlines[:20]:
        tags = ", ".join(d.get("tags", [])[:3])
        dl_rows += (
            f"<tr>"
            f"<td style='padding:8px 12px;font-weight:600;color:#e67e22;"
            f"white-space:nowrap;border-bottom:1px solid #eee;'>{d['date']}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;'>"
            f"<a href='{d['url']}' style='color:#1a1a2e;text-decoration:none;'>"
            f"{d['description']}</a></td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#888;"
            f"border-bottom:1px solid #eee;'>{tags}</td></tr>"
        )
    if not dl_rows:
        dl_rows = "<tr><td colspan='3' style='padding:12px;color:#aaa;'>No deadlines extracted this week.</td></tr>"

    cat_counts = Counter(i["category"] for i in items)
    cat_bars   = ""
    total      = len(items) or 1
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        pct = int(count / total * 100)
        cat_bars += (
            f"<div style='margin-bottom:8px;'>"
            f"<div style='display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;'>"
            f"<span>{cat}</span><span style='color:#888;'>{count}</span></div>"
            f"<div style='background:#eee;border-radius:4px;height:6px;'>"
            f"<div style='background:#2980b9;width:{pct}%;height:6px;border-radius:4px;'></div>"
            f"</div></div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Weekly Regulatory Report — {date_str}</title>
<style>
  body {{ font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
          margin:0;padding:0;background:#f5f6fa;color:#333; }}
  .container {{ max-width:800px;margin:32px auto;background:#fff;
                border-radius:10px;overflow:hidden;
                box-shadow:0 2px 16px rgba(0,0,0,0.08); }}
  h2 {{ color:#1a1a2e;border-bottom:2px solid #eee;padding-bottom:8px; }}
  h3 {{ color:#1a1a2e; }} p {{ line-height:1.7;color:#444; }}
  @media print {{ body {{ background:#fff; }} .container {{ box-shadow:none;margin:0; }} }}
</style>
</head>
<body><div class="container">
  <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:32px;color:#fff;">
    <div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;
                color:#8899aa;margin-bottom:8px;">Regulatory Change Tracker — Weekly Report</div>
    <div style="font-size:26px;font-weight:700;">Week in Review: {week_of} – {week_end}</div>
    <div style="font-size:13px;color:#8bb8e8;margin-top:6px;">
      Focus: AI Act · DORA · Data Act · NIS2</div>
  </div>
  <div style="display:flex;border-bottom:1px solid #eee;">
    <div style="flex:1;text-align:center;padding:20px;border-right:1px solid #eee;">
      <div style="font-size:32px;font-weight:700;color:#2980b9;">{len(items)}</div>
      <div style="font-size:12px;color:#888;text-transform:uppercase;">Items tracked</div>
    </div>
    <div style="flex:1;text-align:center;padding:20px;border-right:1px solid #eee;">
      <div style="font-size:32px;font-weight:700;color:#c0392b;">{len(deadlines)}</div>
      <div style="font-size:12px;color:#888;text-transform:uppercase;">Deadlines found</div>
    </div>
    <div style="flex:1;text-align:center;padding:20px;">
      <div style="font-size:32px;font-weight:700;color:#27ae60;">{len(cat_counts)}</div>
      <div style="font-size:12px;color:#888;text-transform:uppercase;">Categories</div>
    </div>
  </div>
  <div style="padding:32px;">
    <h2>Week in Review</h2>{narrative}
  </div>
  <div style="padding:0 32px 32px;">
    <h2>📅 Consultation & Compliance Deadlines</h2>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #eee;border-radius:6px;overflow:hidden;">
      <tr style="background:#f8f9fa;">
        <th style="padding:10px 12px;font-size:12px;text-transform:uppercase;
                   color:#888;border-bottom:1px solid #eee;">Date</th>
        <th style="padding:10px 12px;font-size:12px;text-transform:uppercase;
                   color:#888;border-bottom:1px solid #eee;">Deadline</th>
        <th style="padding:10px 12px;font-size:12px;text-transform:uppercase;
                   color:#888;border-bottom:1px solid #eee;">Regulations</th>
      </tr>
      {dl_rows}
    </table>
  </div>
  <div style="padding:0 32px 32px;">
    <h2>Volume by Category</h2>{cat_bars}
  </div>
  <div style="background:#f8f9fa;padding:16px 32px;font-size:11px;color:#aaa;
              border-top:1px solid #eee;text-align:center;">
    Generated by Regulatory Change Tracker on {date_str} · For internal use only
  </div>
</div></body></html>"""


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

    parser = argparse.ArgumentParser(description="Generate weekly regulatory report")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--days",  type=int, default=7)
    args = parser.parse_args()

    import config
    html = build_weekly_report(config.DB_PATH, config.GEMINI_API_KEY, config.TOPIC_FOCUS, args.days)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out      = Path(f"weekly_report_{date_str}.html")
    out.write_text(html, encoding="utf-8")
    print(f"Report saved: {out}")

    if args.email:
        from emailer import send_email
        send_email(
            html_body=html,
            subject=f"📋 Weekly Regulatory Report — {datetime.now(timezone.utc).strftime('%d %b %Y')}",
            email_from=config.EMAIL_FROM,
            email_to=config.EMAIL_TO,
            resend_api_key=config.RESEND_API_KEY,
        )
        print("Report emailed.")
