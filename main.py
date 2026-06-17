"""
main.py — Regulatory Change Tracker — Full Orchestrator (v2).

Pipeline:
  1. Fetch all RSS sources (concurrent)
  2. Scrape non-RSS targets (concurrent)
  3. Deduplicate against SQLite
  4. AI enrichment: summary, tags, relevance, action (Claude)
  5. Deadline extraction (Claude)
  6. Keyword / topic relevance filter
  7. Instant alert → email + Slack for score >= INSTANT_ALERT_MIN
  8. Build and send daily digest email (Resend)
  9. Post daily summary to Slack digest channel
  10. Push all new items to Notion
  11. Save deadlines calendar

Usage:
    python main.py                  # normal run
    python main.py --backfill       # 30-day lookback (first run)
    python main.py --dry-run        # fetch + enrich, no email/DB writes
    python main.py --no-scrape      # skip scraping (RSS only)
    python main.py --no-notion      # skip Notion export
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
from database import init_db, is_new, mark_seen, mark_emailed, log_run
from sources import fetch_all_sources
from scraper import scrape_all_targets
from processor import process_items
from deadlines import extract_deadlines, save_calendar
from alerter import send_instant_email_alert, send_slack_alert, send_slack_digest_summary
from emailer import build_html, send_email
from notion_export import push_to_notion

logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s  %(levelname)-8s  %(name)-22s  %(message)s",
    datefmt  = "%Y-%m-%d %H:%M:%S",
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tracker.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def _known_urls(db_path: Path) -> set[str]:
    """Load all URLs already in the DB (for scraper dedup)."""
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT url FROM seen_items").fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _keyword_relevant(item, keywords: list[str]) -> bool:
    """Return True if the item text contains at least one keyword."""
    if not keywords:
        return True
    text = (item.title + " " + item.raw_summary + " " + " ".join(item.ai_tags)).lower()
    return any(kw.lower() in text for kw in keywords)


def run(lookback_days: int | None = None,
        dry_run: bool = False,
        no_scrape: bool = False,
        no_notion: bool = False) -> None:

    lookback = lookback_days or config.LOOKBACK_DAYS
    log.info(
        f"{'[DRY RUN] ' if dry_run else ''}"
        f"=== Regulatory Tracker v2 started "
        f"(lookback={lookback}d | sources={len(config.SOURCES)} RSS + "
        f"{0 if no_scrape else len(config.SCRAPE_TARGETS)} scrape) ==="
    )

    # ── 1. Init DB ────────────────────────────────────────────────────────────
    if not dry_run:
        init_db(config.DB_PATH)

    # ── 2. Fetch RSS ──────────────────────────────────────────────────────────
    rss_items = fetch_all_sources(config.SOURCES, lookback_days=lookback)
    log.info(f"RSS items: {len(rss_items)}")

    # ── 3. Scrape non-RSS ─────────────────────────────────────────────────────
    scraped_items = []
    if not no_scrape and config.SCRAPE_TARGETS:
        known = set() if dry_run else _known_urls(config.DB_PATH)
        scraped_items = scrape_all_targets(config.SCRAPE_TARGETS, known_urls=known)
        log.info(f"Scraped items: {len(scraped_items)}")

    all_items = rss_items + scraped_items
    log.info(f"Total raw items: {len(all_items)}")

    # ── 4. Deduplicate ────────────────────────────────────────────────────────
    if dry_run:
        new_items = all_items
    else:
        new_items = [i for i in all_items if is_new(config.DB_PATH, i.url)]

    log.info(f"New items: {len(new_items)}")

    if not new_items:
        log.info("Nothing new — exiting.")
        if not dry_run:
            log_run(config.DB_PATH, 0, 0)
        return

    # Mark seen immediately
    if not dry_run:
        for item in new_items:
            mark_seen(config.DB_PATH, item.url, item.title,
                      item.source_name, item.category, item.jurisdiction)

    # ── 5. AI enrichment ──────────────────────────────────────────────────────
    log.info(f"AI enrichment: {len(new_items)} items …")
    enriched = process_items(new_items, api_key=config.GEMINI_API_KEY)

    # ── 6. Deadline extraction ────────────────────────────────────────────────
    log.info("Extracting consultation deadlines …")
    enriched = extract_deadlines(enriched, api_key=config.ANTHROPIC_API_KEY)
    if not dry_run:
        save_calendar(enriched)

    # ── 7. Keyword filter ─────────────────────────────────────────────────────
    relevant = [i for i in enriched if _keyword_relevant(i, config.KEYWORD_FILTER)]
    low_rel  = [i for i in relevant if i.ai_relevance < config.MIN_RELEVANCE]
    filtered = [i for i in relevant if i.ai_relevance >= config.MIN_RELEVANCE]
    log.info(
        f"After keyword + relevance filter (≥{config.MIN_RELEVANCE}): "
        f"{len(filtered)}/{len(enriched)} items "
        f"({len(enriched) - len(relevant)} off-topic, {len(low_rel)} below threshold)"
    )

    if not filtered:
        log.info("All items filtered out — no output generated.")
        if not dry_run:
            log_run(config.DB_PATH, len(new_items), 0)
        return

    # ── 8. Instant alerts (score >= INSTANT_ALERT_MIN) ────────────────────────
    critical = [i for i in filtered if i.ai_relevance >= config.INSTANT_ALERT_MIN]
    if critical:
        log.info(f"Critical items for instant alert: {len(critical)}")
        if not dry_run:
            send_instant_email_alert(
                critical,
                email_from    = config.EMAIL_FROM,
                email_to      = config.EMAIL_TO,
                resend_api_key= config.RESEND_API_KEY,
            )
            send_slack_alert(critical, webhook_url=config.SLACK_WEBHOOK_URL)

    # ── 9. Build & send daily digest ─────────────────────────────────────────
    n        = len(filtered)
    n_crit   = len(critical)
    date_str = datetime.now(timezone.utc).strftime("%d %b %Y")
    subject  = (
        f"🚨 {date_str} — {n_crit} critical + {n - n_crit} more"
        if n_crit
        else f"⚖️ Regulatory Digest {date_str} — {n} new items"
    )

    html = build_html(filtered)

    if dry_run:
        preview = Path("digest_preview.html")
        preview.write_text(html, encoding="utf-8")
        log.info(f"[DRY RUN] Preview → {preview}")
        _print_summary(filtered)
        return

    send_email(
        html_body      = html,
        subject        = subject,
        email_from     = config.EMAIL_FROM,
        email_to       = config.EMAIL_TO,
        resend_api_key = config.RESEND_API_KEY,
    )
    mark_emailed(config.DB_PATH, [i.url for i in filtered])

    # ── 10. Slack digest summary ──────────────────────────────────────────────
    send_slack_digest_summary(filtered, config.SLACK_DIGEST_URL, date_str)

    # ── 11. Notion export ─────────────────────────────────────────────────────
    if not no_notion:
        push_to_notion(filtered, config.NOTION_API_KEY, config.NOTION_DB_ID)

    # ── 12. Log run ───────────────────────────────────────────────────────────
    log_run(config.DB_PATH, len(new_items), len(filtered))
    log.info(f"=== Run complete — {len(filtered)} items sent ===")


def _print_summary(items: list) -> None:
    w = 80
    print(f"\n{'─'*w}")
    print(f"{'SCORE':>5}  {'TAGS':<30}  {'SRC':<12}  TITLE")
    print(f"{'─'*w}")
    for item in sorted(items, key=lambda i: -i.ai_relevance):
        tags  = ", ".join(item.ai_tags[:2]) if item.ai_tags else "—"
        src   = item.jurisdiction[:12]
        title = item.title[:48] + ("…" if len(item.title) > 48 else "")
        print(f"{item.ai_relevance:>5}  {tags:<30}  {src:<12}  {title}")
        if getattr(item, "deadlines", []):
            for dl in item.deadlines:
                print(f"       📅 {dl['date']:15s}  {dl['description'][:55]}")
    print(f"{'─'*w}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="EU Regulatory Change Tracker — Full pipeline"
    )
    parser.add_argument("--backfill",   action="store_true",
                        help="30-day lookback (use on first run)")
    parser.add_argument("--dry-run",    action="store_true", dest="dry_run",
                        help="Enrich items but do NOT send or write to DB")
    parser.add_argument("--no-scrape",  action="store_true", dest="no_scrape",
                        help="Skip direct scraping (RSS only)")
    parser.add_argument("--no-notion",  action="store_true", dest="no_notion",
                        help="Skip Notion export")
    args = parser.parse_args()

    try:
        run(
            lookback_days = 30 if args.backfill else None,
            dry_run       = args.dry_run,
            no_scrape     = args.no_scrape,
            no_notion     = args.no_notion,
        )
    except KeyboardInterrupt:
        log.info("Interrupted.")
        sys.exit(0)
    except Exception as e:
        log.critical(f"Unhandled error: {e}", exc_info=True)
        sys.exit(1)
