"""
alerter.py — Instant alerts for critical items (score >= INSTANT_ALERT_MIN).

Two channels:
  1. Email via Resend — a minimal "flash alert" email (not the full digest)
  2. Slack webhook — rich block message with colour-coded severity

Both channels are independent; either can be disabled by leaving the
corresponding env var empty.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from sources.rss_source import FeedItem

log = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"

# ── Tag colours (shared with emailer) ────────────────────────────────────────
_TAG_COLOURS: dict[str, str] = {
    "GDPR": "#8e44ad", "AI Act": "#16a085", "DORA": "#2980b9",
    "NIS2": "#c0392b", "ePrivacy": "#d35400", "Data Act": "#27ae60",
    "Cyber Resilience Act": "#2c3e50", "Other": "#555555",
}


# ── Instant email alert ───────────────────────────────────────────────────────

def _alert_html(items: list["FeedItem"]) -> str:
    """Minimal red-header flash alert for critical items."""
    rows = ""
    for item in items:
        tags  = " ".join(
            f'<span style="background:{_TAG_COLOURS.get(t,"#555")};color:#fff;'
            f'padding:1px 7px;border-radius:10px;font-size:11px;">{t}</span>'
            for t in item.ai_tags
        )
        rows += f"""
        <tr style="border-bottom:1px solid #eee;">
          <td style="padding:14px 16px;">
            <div style="font-size:13px;font-weight:700;color:#c0392b;margin-bottom:4px;">
              ⚠ Score {item.ai_relevance}/10 — {item.source_name} ({item.jurisdiction})
            </div>
            <a href="{item.url}" style="font-size:14px;font-weight:600;color:#1a1a2e;
               text-decoration:none;">{item.title}</a>
            <div style="font-size:13px;color:#444;margin-top:6px;line-height:1.6;">
              {item.ai_summary or item.raw_summary[:250]}
            </div>
            {"<div style='margin-top:6px;background:#fef9e7;border-left:3px solid #f39c12;"
             "padding:6px 10px;font-size:12px;color:#7d6608;'>"
             "<strong>⚑ Action:</strong> " + item.ai_action + "</div>"
             if item.ai_action and item.ai_action.lower() != "no immediate action required." else ""}
            <div style="margin-top:8px;">{tags}</div>
          </td>
        </tr>"""

    n    = len(items)
    date = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    return f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f8f8f8;
             font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f8f8f8">
  <tr><td align="center" style="padding:20px 12px;">
    <table width="600" cellpadding="0" cellspacing="0" border="0"
           style="max-width:600px;background:#fff;border-radius:8px;
                  overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
      <tr>
        <td style="background:#c0392b;padding:18px 20px;">
          <div style="font-size:11px;color:rgba(255,255,255,0.7);
                      letter-spacing:1px;text-transform:uppercase;">
            🚨 Regulatory Change Tracker — Critical Alert
          </div>
          <div style="font-size:18px;font-weight:700;color:#fff;margin-top:4px;">
            {n} Critical Update{"s" if n > 1 else ""} Detected
          </div>
          <div style="font-size:12px;color:rgba(255,255,255,0.7);margin-top:2px;">
            {date}
          </div>
        </td>
      </tr>
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        {rows}
      </table>
      <tr>
        <td style="background:#f8f9fa;padding:12px 16px;text-align:center;
                   font-size:11px;color:#aaa;border-top:1px solid #eee;">
          You will also receive this in your daily digest.
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def send_instant_email_alert(
    items: list["FeedItem"],
    email_from: str,
    email_to: list[str],
    resend_api_key: str,
) -> None:
    """Send a flash alert email for critical items via Resend."""
    if not resend_api_key or not email_to:
        log.debug("Instant email alert skipped: missing Resend key or recipients.")
        return
    if not items:
        return

    n       = len(items)
    subject = f"🚨 Critical Regulatory Alert — {n} item{'s' if n > 1 else ''} require attention"

    resp = requests.post(
        _RESEND_URL,
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from":    email_from,
            "to":      email_to,
            "subject": subject,
            "html":    _alert_html(items),
        },
        timeout=30,
    )
    resp.raise_for_status()
    log.info(f"Instant alert sent → {email_to} ({n} critical items)")


# ── Slack alert ───────────────────────────────────────────────────────────────

def _score_emoji(score: int) -> str:
    if score >= 8:
        return "🚨"
    if score >= 6:
        return "⚠️"
    return "ℹ️"


def _slack_blocks(items: list["FeedItem"]) -> list[dict]:
    date = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    n    = len(items)

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 Critical Regulatory Update{'s' if n > 1 else ''} — {date}",
            },
        },
        {"type": "divider"},
    ]

    for item in items:
        tags_str = "  ".join(f"`{t}`" for t in item.ai_tags[:4])
        action   = item.ai_action or ""

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{_score_emoji(item.ai_relevance)} *Score {item.ai_relevance}/10*  "
                    f"_{item.source_name}_ · {item.jurisdiction}\n"
                    f"*<{item.url}|{item.title}>*\n"
                    f"{item.ai_summary or item.raw_summary[:200]}"
                    + (f"\n\n⚑ *Action:* {action}"
                       if action and action.lower() != "no immediate action required." else "")
                    + (f"\n{tags_str}" if tags_str else "")
                ),
            },
        })
        blocks.append({"type": "divider"})

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "These items will also appear in your daily digest email.",
            }
        ],
    })
    return blocks


def send_slack_alert(
    items: list["FeedItem"],
    webhook_url: str,
) -> None:
    """Post critical items to Slack via incoming webhook."""
    if not webhook_url:
        log.debug("Slack alert skipped: SLACK_WEBHOOK_URL not set.")
        return
    if not items:
        return

    payload = {
        "text": f"🚨 {len(items)} critical regulatory update(s) detected",
        "blocks": _slack_blocks(items),
    }
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    log.info(f"Slack alert sent ({len(items)} critical items)")


def send_slack_digest_summary(
    items: list["FeedItem"],
    webhook_url: str,
    date_str: str,
) -> None:
    """Post a brief daily digest summary to a Slack channel."""
    if not webhook_url or not items:
        return

    critical  = sum(1 for i in items if i.ai_relevance >= 8)
    important = sum(1 for i in items if 6 <= i.ai_relevance < 8)
    top3      = sorted(items, key=lambda i: -i.ai_relevance)[:3]

    top3_lines = "\n".join(
        f"• {_score_emoji(i.ai_relevance)} *<{i.url}|{i.title}>* ({i.jurisdiction})"
        for i in top3
    )

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"⚖️ *Regulatory Digest — {date_str}*\n"
                    f"*{len(items)}* new items — "
                    f"*{critical}* critical · *{important}* important\n\n"
                    f"*Top items:*\n{top3_lines}"
                ),
            },
        }
    ]

    resp = requests.post(webhook_url, json={"blocks": blocks}, timeout=15)
    resp.raise_for_status()
    log.info(f"Slack digest summary sent ({len(items)} items)")
