"""
scheduler.py — Daily + weekly schedule runner.

Runs the full tracker pipeline daily at DAILY_RUN_TIME,
and the weekly report generator on WEEKLY_REPORT_DAY.

Usage:
    python scheduler.py

Background (Mac):
    nohup python scheduler.py > scheduler.log 2>&1 &
"""
from __future__ import annotations

import logging
import os
import sys
import time

import schedule
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scheduler.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

DAILY_RUN_TIME    = os.getenv("DAILY_RUN_TIME", "07:30")
WEEKLY_REPORT_DAY = os.getenv("WEEKLY_REPORT_DAY", "friday").lower()


def daily_job() -> None:
    log.info("=== Daily tracker job triggered ===")
    try:
        from main import run
        run()
    except Exception as e:
        log.error(f"Daily run failed: {e}", exc_info=True)


def weekly_report_job() -> None:
    log.info("=== Weekly report job triggered ===")
    try:
        import config
        from reporter import build_weekly_report
        from emailer import send_email
        from datetime import datetime, timezone
        from pathlib import Path

        html     = build_weekly_report(
            db_path     = config.DB_PATH,
            api_key     = config.ANTHROPIC_API_KEY,
            topic_focus = config.TOPIC_FOCUS,
        )
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path     = Path(f"weekly_report_{date_str}.html")
        path.write_text(html, encoding="utf-8")
        log.info(f"Weekly report saved: {path}")

        send_email(
            html_body      = html,
            subject        = f"📋 Weekly Regulatory Report — {datetime.now(timezone.utc).strftime('%d %b %Y')}",
            email_from     = config.EMAIL_FROM,
            email_to       = config.EMAIL_TO,
            resend_api_key = config.RESEND_API_KEY,
        )
        log.info("Weekly report emailed.")
    except Exception as e:
        log.error(f"Weekly report failed: {e}", exc_info=True)


if __name__ == "__main__":
    log.info("Regulatory Change Tracker scheduler started.")
    log.info(f"  Daily digest : {DAILY_RUN_TIME} every day")
    log.info(f"  Weekly report: {WEEKLY_REPORT_DAY.capitalize()} at {DAILY_RUN_TIME}")

    # Daily job
    schedule.every().day.at(DAILY_RUN_TIME).do(daily_job)

    # Weekly report (same time, specific day)
    day_fn = getattr(schedule.every(), WEEKLY_REPORT_DAY, None)
    if day_fn:
        day_fn.at(DAILY_RUN_TIME).do(weekly_report_job)
    else:
        log.warning(f"Invalid WEEKLY_REPORT_DAY '{WEEKLY_REPORT_DAY}', defaulting to Friday")
        schedule.every().friday.at(DAILY_RUN_TIME).do(weekly_report_job)

    # Run daily job on startup
    log.info("Running initial fetch on startup …")
    daily_job()

    log.info("Entering schedule loop. Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)
