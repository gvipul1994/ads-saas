"""
APScheduler-based daily job: iterates every active GoogleAdsAccount and runs
the optimizer for each. Started from main.py on app startup.

For production scale (hundreds of accounts), swap this for Celery Beat +
workers so accounts run in parallel and a crash in one doesn't block the
rest mid-batch; APScheduler in-process is fine for the first cohort of
clients and keeps the stack simpler to run.
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.models import GoogleAdsAccount, PendingOAuthToken
from app.core.run_account import run_account

logger = logging.getLogger("ads_optimizer")

scheduler = BackgroundScheduler()


def run_all_accounts_job():
    db = SessionLocal()
    try:
        accounts = db.query(GoogleAdsAccount).filter(GoogleAdsAccount.is_active == True).all()  # noqa: E712
        logger.info(f"Daily job: running optimizer for {len(accounts)} active account(s)")
        for account in accounts:
            try:
                result = run_account(db, account)
                logger.info(f"[account={account.id}] {result}")
            except Exception as e:
                # One account's unexpected failure must never stop the others.
                logger.exception(f"[account={account.id}] unhandled error during daily run: {e}")
    finally:
        db.close()


def cleanup_pending_oauth_job():
    """Pending OAuth connections older than 1 hour were abandoned mid-flow; drop them."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        stale = db.query(PendingOAuthToken).filter(PendingOAuthToken.created_at < cutoff).all()
        for p in stale:
            db.delete(p)
        db.commit()
        if stale:
            logger.info(f"Cleaned up {len(stale)} abandoned pending OAuth connection(s)")
    finally:
        db.close()


def start_scheduler():
    # Daily at 06:00 UTC - adjust per your / your clients' timezone needs,
    # or make this per-account later.
    scheduler.add_job(run_all_accounts_job, CronTrigger(hour=6, minute=0), id="daily_optimizer_run",
                       replace_existing=True)
    scheduler.add_job(cleanup_pending_oauth_job, CronTrigger(hour="*", minute=0), id="cleanup_pending_oauth",
                       replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started: daily optimizer run at 06:00 UTC")
