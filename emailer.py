"""
emailer.py — Resend-powered HTML digest builder and sender.

Resend (resend.com) replaces SMTP entirely:
  - Free tier: 3,000 emails/month
  - Setup: create account → get API key → done. No SMTP config.
  - Docs: https://resend.com/docs/send-with-python
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from sources.rss_source import FeedItem

log = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"

# ── Style helpers ─────────────────────────────────────────────────────────────

_RELEVANCE_COLOURS = {
    range(8, 11): "#c0392b",
    range(6, 8):  "#e67e22",
    range(4, 6):  "#2980b9",
    range(1, 4):  "#7f8c8d",
}

_TAG_COLOURS: dict[str, str] = {
    "GDPR": "#8e44ad", "AI Act": "#16a085", "DORA": "#2980b9",
    "NIS2": "#c0392b", "ePrivacy": "#d35400", "Data Act": "#27ae60",
    "Cyber Resilience Act": "#2c3e50", "FIDA": "#7d6608",
    "PSD3 / PSR": "#1a5276", "AML Package": "#922b21",
    "Digital Markets Act": "#145a32", "Digital Services Act": "#1b4f72",
    "Other": "#555555",
}

_CATEGORY_ORDER = [
    "EU Legislation", "AI Regulation", "Data Protection",
    "Financial Regulation", "Cybersecurity", "Legal News",
]


def _badge_colour(score: int) -> str:
    for rng, colour in _RELEVANCE_COLOURS.items():
        if score in rng:
            return colour
    return "#7f8c8d"


def _tag_pill(tag: str) -> str:
    colour = _TAG_COLOURS.get(tag, "#555")
    return (
        f'<span style="display:inline-block;margin:2px 2px 2px 0;'
        f'padding:2px 9px;border-radius:12px;font-size:11px;font-weight:600;'
        f'background:{colour};color:#fff;">{tag}</span>'
    )


def _deadline_box(deadlines: list[dict]) -> str:
    if not deadlines:
        return ""
    rows = "".join(
        f'<tr><td style="padding:3px 8px;font-size:12px;color:#7d6608;">'
        f'<strong>{d["date"]}</strong></td>'
        f'<td style="padding:3px 8px;font-size:12px;color:#555;">{d["description"]}</td></tr>'
        for d in deadlines
    )
    return f"""
    <tr>
      <td colspan="2" style="padding-top:8px;">
        <div style="background:#fdf2e9;border-left:3px solid #e67e22;
                    padding:8px 12px;border-radius:0 4px 4px 0;">
          <div style="font-size:11px;font-weight:700;color:#e67e22;
                      text-transform:uppercase;margin-bottom:4px;">
            📅 Consultation Deadlines
          </div>
          <table cellpadding="0" cellspacing="0" border="0">{rows}</table>
        </div>
      </td>
    </tr>"""


def _render_item(item: "FeedItem") -> str:
    badge_c   = _badge_colour(item.ai_relevance)
    tags_html = "".join(_tag_pill(t) for t in item.ai_tags)
    pub       = item.published.strftime("%d %b %Y")
    summary   = (item.ai_summary or item.raw_summary[:300]).replace("\n", "<br>")
    action    = item.ai_action or ""
    deadlines = getattr(item, "deadlines", [])

    action_row = ""
    if action and action.lower() != "no immediate action required.":
        action_row = f"""
        <tr>
          <td colspan="2" style="padding-top:8px;">
            <div style="background:#fef9e7;border-left:3px solid #f39c12;
                        padding:8px 12px;border-radius:0 4px 4px 0;
                        font-size:12px;color:#7d6608;">
              <strong>⚑ Action:</strong> {action}
            </div>
          </td>
        </tr>"""

    return f"""
    <tr>
      <td style="padding:16px 20px;border-bottom:1px solid #eee;vertical-align:top;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="vertical-align:top;">
              <a href="{item.url}"
                 style="font-size:14px;font-weight:600;color:#1a1a2e;text-decoration:none;">
                {item.title}
              </a>
            </td>
            <td align="right" style="white-space:nowrap;padding-left:12px;vertical-align:top;">
              <span style="display:inline-block;padding:3px 10px;border-radius:20px;
                           font-size:11px;font-weight:700;color:#fff;background:{badge_c};">
                {item.ai_relevance}/10
              </span>
            </td>
          </tr>
          <tr>
            <td colspan="2" style="padding-top:3px;font-size:11px;color:#999;">
              {item.source_name}&nbsp;&nbsp;·&nbsp;&nbsp;{item.jurisdiction}&nbsp;&nbsp;·&nbsp;&nbsp;{pub}
            </td>
          </tr>
          <tr>
            <td colspan="2" style="padding-top:10px;font-size:13px;color:#333;line-height:1.65;">
              {summary}
            </td>
          </tr>
          {action_row}
          {_deadline_box(deadlines)}
          {"<tr><td colspan='2' style='padding-top:8px;'>" + tags_html + "</td></tr>" if tags_html else ""}
          <tr>
            <td colspan="2" style="padding-top:8px;">
              <a href="{item.url}" style="font-size:12px;color:#2980b9;text-decoration:none;">
                Read full document →
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def build_html(items: list["FeedItem"], title: str = "EU Regulatory Digest") -> str:
    now       = datetime.now(timezone.utc)
    date_str  = now.strftime("%A, %d %B %Y")
    total     = len(items)
    critical  = sum(1 for i in items if i.ai_relevance >= 8)
    important = sum(1 for i in items if 6 <= i.ai_relevance < 8)

    by_cat: dict[str, list] = defaultdict(list)
    for item in sorted(items, key=lambda i: -i.ai_relevance):
        by_cat[item.category].append(item)

    sections = ""
    rendered: set[str] = set()
    for cat in _CATEGORY_ORDER:
        cat_items = by_cat.get(cat, [])
        if not cat_items:
            continue
        rendered.add(cat)
        sections += f"""
        <tr>
          <td style="background:#1a1a2e;color:#fff;padding:10px 20px;
                     font-size:12px;font-weight:700;letter-spacing:0.8px;
                     text-transform:uppercase;">
            {cat} <span style="font-weight:400;opacity:0.6;margin-left:6px;">({len(cat_items)})</span>
          </td>
        </tr>"""
        for item in cat_items:
            sections += _render_item(item)

    for cat, cat_items in by_cat.items():
        if cat not in rendered:
            sections += f"""
            <tr>
              <td style="background:#1a1a2e;color:#fff;padding:10px 20px;
                         font-size:12px;font-weight:700;letter-spacing:0.8px;
                         text-transform:uppercase;">
                {cat} <span style="font-weight:400;opacity:0.6;margin-left:6px;">({len(cat_items)})</span>
              </td>
            </tr>"""
            for item in cat_items:
                sections += _render_item(item)

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} — {date_str}</title></head>
<body style="margin:0;padding:0;background:#f0f2f5;
             font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f0f2f5">
  <tr><td align="center" style="padding:24px 12px;">
    <table width="660" cellpadding="0" cellspacing="0" border="0"
           style="max-width:660px;background:#fff;border-radius:10px;
                  overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.1);">
      <tr>
        <td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:28px 24px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td>
                <div style="font-size:10px;color:#8899aa;letter-spacing:1.2px;
                            text-transform:uppercase;margin-bottom:6px;">
                  Regulatory Change Tracker
                </div>
                <div style="font-size:22px;font-weight:700;color:#fff;">{title}</div>
                <div style="font-size:13px;color:#8bb8e8;margin-top:4px;">{date_str}</div>
              </td>
              <td align="right">
                <table cellpadding="0" cellspacing="4" border="0">
                  <tr>
                    <td align="center" style="background:rgba(255,255,255,0.1);
                        border-radius:8px;padding:10px 16px;min-width:52px;">
                      <div style="font-size:24px;font-weight:700;color:#fff;">{total}</div>
                      <div style="font-size:10px;color:#aaa;text-transform:uppercase;">New</div>
                    </td>
                    <td align="center" style="background:rgba(231,76,60,0.25);
                        border-radius:8px;padding:10px 16px;min-width:52px;">
                      <div style="font-size:24px;font-weight:700;color:#e74c3c;">{critical}</div>
                      <div style="font-size:10px;color:#aaa;text-transform:uppercase;">Critical</div>
                    </td>
                    <td align="center" style="background:rgba(230,126,34,0.2);
                        border-radius:8px;padding:10px 16px;min-width:52px;">
                      <div style="font-size:24px;font-weight:700;color:#e67e22;">{important}</div>
                      <div style="font-size:10px;color:#aaa;text-transform:uppercase;">Important</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <tr>
        <td style="background:#f8f9fa;padding:10px 20px;border-bottom:1px solid #eee;
                   font-size:11px;color:#777;">
          <strong>Relevance:</strong>&nbsp;
          <span style="color:#c0392b;">■</span> 8–10 Critical&nbsp;&nbsp;
          <span style="color:#e67e22;">■</span> 6–7 Important&nbsp;&nbsp;
          <span style="color:#2980b9;">■</span> 4–5 Informational&nbsp;&nbsp;
          <span style="color:#7f8c8d;">■</span> 1–3 Background
        </td>
      </tr>
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        {sections}
      </table>
      <tr>
        <td style="background:#f8f9fa;padding:16px 20px;border-top:1px solid #eee;
                   text-align:center;font-size:11px;color:#aaa;">
          Regulatory Change Tracker · {date_str}<br>
          AI Act · DORA · Data Act · NIS2 · GDPR · and more
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def send_email(
    html_body:    str,
    subject:      str,
    email_from:   str,
    email_to:     list[str],
    resend_api_key: str,
) -> None:
    """Send HTML email via Resend API (single HTTP POST, no SMTP config needed)."""
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
            "html":    html_body,
        },
        timeout=30,
    )
    resp.raise_for_status()
    log.info(f"Email sent via Resend → {email_to} | id: {resp.json().get('id')}")
