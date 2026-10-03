"""
The actual "run the optimizer for one account" logic, shared by:
  - the daily APScheduler job (core/scheduler.py), run unattended for every
    active account
  - a manual "Run now" button in the dashboard (routers/accounts.py), for
    testing without waiting for the schedule

Writes to AuditLogEntry and Recommendation tables; sends email via
core/email_notifier.py. Never raises on a per-action failure — logs it
and continues, so one bad action doesn't stop the rest of the run.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import GoogleAdsAccount, AuditLogEntry, Recommendation, RecommendationStatus
from app.core.crypto import decrypt_token
from app.core.google_ads_client import GoogleAdsAccountClient, GoogleAdsException
from app.core.rule_engine import run_all_rules
from app.core.executor import execute, ForbiddenActionError
from app.core.email_notifier import send_recommendation_email, send_weekly_report
from app.config import settings

logger = logging.getLogger("ads_optimizer")

WEEKLY_REPORT_WEEKDAY = 0  # Monday


def run_account(db: Session, account: GoogleAdsAccount, force_weekly_report: bool = False) -> dict:
    if not account.is_active:
        return {"skipped": "account is paused (is_active=false)"}

    refresh_token = decrypt_token(account.encrypted_refresh_token)
    client = GoogleAdsAccountClient(
        refresh_token=refresh_token,
        customer_id=account.customer_id,
        login_customer_id=settings.google_ads_login_customer_id,
    )

    try:
        actions, recommendations = run_all_rules(client)
    except GoogleAdsException as e:
        logger.error(f"[account={account.id}] Google Ads API error during read: {e}")
        return {"error": str(e)}

    applied = 0
    for planned in actions:
        if applied >= account.max_actions_per_run:
            logger.info(f"[account={account.id}] hit max_actions_per_run "
                        f"({account.max_actions_per_run}), stopping early this run")
            break
        entry = AuditLogEntry(
            account_id=account.id, action=planned.label, params=planned.kwargs,
            reason=planned.reason, dry_run=account.dry_run,
        )
        try:
            result = execute(client, planned, account.dry_run)
            entry.result = result
            entry.success = True
            applied += 1
        except (ForbiddenActionError, GoogleAdsException) as e:
            entry.success = False
            entry.error = str(e)
            logger.error(f"[account={account.id}] action {planned.method} failed: {e}")
        db.add(entry)

    # Sync recommendations: close ones that no longer apply, add new ones.
    # Simpler v1 approach: mark all currently-open recs as superseded if
    # not re-found this run, then upsert what the rule engine found.
    open_recs = db.query(Recommendation).filter(
        Recommendation.account_id == account.id, Recommendation.status == RecommendationStatus.open
    ).all()
    still_open_keys = {(r.kind, r.campaign_id) for r in recommendations}
    for existing in open_recs:
        if (existing.kind, existing.campaign_id) not in still_open_keys:
            existing.status = RecommendationStatus.applied  # assume resolved; dismiss manually otherwise
            existing.resolved_at = datetime.now(timezone.utc)

    existing_keys = {(r.kind, r.campaign_id) for r in open_recs}
    new_recs_for_email = []
    for rec in recommendations:
        if (rec.kind, rec.campaign_id) not in existing_keys:
            row = Recommendation(
                account_id=account.id, kind=rec.kind, campaign_id=rec.campaign_id,
                campaign_name=rec.campaign_name, detail=rec.detail, metrics=rec.metrics,
            )
            db.add(row)
            new_recs_for_email.append(rec)

    account.last_run_at = datetime.now(timezone.utc)
    db.commit()

    if new_recs_for_email:
        try:
            send_recommendation_email(account.notify_email, account.descriptive_name or account.customer_id,
                                       new_recs_for_email)
        except Exception as e:
            logger.error(f"[account={account.id}] failed to send recommendation email: {e}")

    today = datetime.now(timezone.utc).weekday()
    if force_weekly_report or today == WEEKLY_REPORT_WEEKDAY:
        since = datetime.now(timezone.utc) - timedelta(days=7)
        week_entries = (db.query(AuditLogEntry)
                        .filter(AuditLogEntry.account_id == account.id, AuditLogEntry.timestamp >= since)
                        .all())
        open_now = db.query(Recommendation).filter(
            Recommendation.account_id == account.id, Recommendation.status == RecommendationStatus.open
        ).all()
        try:
            send_weekly_report(account.notify_email, account.descriptive_name or account.customer_id,
                                week_entries, open_now)
        except Exception as e:
            logger.error(f"[account={account.id}] failed to send weekly report: {e}")

    return {"actions_found": len(actions), "actions_applied": applied,
            "recommendations_found": len(recommendations)}
