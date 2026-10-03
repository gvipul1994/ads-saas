"""Same two email types as the prototype, now parameterized per-account
(each GoogleAdsAccount has its own notify_email)."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings
from app.models import AuditLogEntry, Recommendation


def _send(to_email: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.from_name} <{settings.smtp_username}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_username, [to_email], msg.as_string())


def send_recommendation_email(to_email: str, account_name: str, recommendations: list[Recommendation]):
    if not recommendations:
        return
    rows = ""
    for r in recommendations:
        label = "Increase budget" if r.kind == "budget" else "Increase bid / adjust bidding strategy"
        rows += f"""<tr><td style="padding:10px;border-bottom:1px solid #eee;"><b>{r.campaign_name}</b></td>
            <td style="padding:10px;border-bottom:1px solid #eee;">{label}</td>
            <td style="padding:10px;border-bottom:1px solid #eee;">{r.detail}</td></tr>"""
    html = f"""<html><body style="font-family:Arial,sans-serif;color:#222;">
      <h2>Budget / Bidding Recommendations — {account_name}</h2>
      <p>These are changes the optimizer <b>will not make automatically</b>. Review in the
         dashboard or apply them directly in Google Ads if you agree.</p>
      <table style="border-collapse:collapse;width:100%;">
        <tr style="background:#f5f5f5;text-align:left;"><th style="padding:10px;">Campaign</th>
          <th style="padding:10px;">Suggested change</th><th style="padding:10px;">Why</th></tr>
        {rows}
      </table></body></html>"""
    _send(to_email, f"[Ads Optimizer] {len(recommendations)} recommendation(s) for {account_name}", html)


def send_weekly_report(to_email: str, account_name: str, audit_entries: list[AuditLogEntry],
                        recommendations: list[Recommendation]):
    executed = [e for e in audit_entries if not e.dry_run]
    dry_run = [e for e in audit_entries if e.dry_run]

    def action_rows(entries):
        rows = ""
        for e in entries:
            rows += f"""<tr><td style="padding:8px;border-bottom:1px solid #eee;font-size:12px;">
                {e.timestamp.strftime('%Y-%m-%d %H:%M')}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;"><code>{e.action}</code></td>
                <td style="padding:8px;border-bottom:1px solid #eee;">{e.reason}</td></tr>"""
        return rows or '<tr><td style="padding:8px;color:#888;" colspan="3">None this week.</td></tr>'

    rec_rows = ""
    for r in recommendations:
        rec_rows += f"""<tr><td style="padding:8px;border-bottom:1px solid #eee;">{r.campaign_name}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{r.kind}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{r.detail}</td></tr>"""
    rec_rows = rec_rows or '<tr><td style="padding:8px;color:#888;" colspan="3">None open right now.</td></tr>'

    html = f"""<html><body style="font-family:Arial,sans-serif;color:#222;">
      <h2>Weekly Report — {account_name}</h2>
      <h3>Changes made automatically ({len(executed)})</h3>
      <table style="border-collapse:collapse;width:100%;">
        <tr style="background:#f5f5f5;text-align:left;"><th style="padding:8px;">When</th>
            <th style="padding:8px;">Action</th><th style="padding:8px;">Reason</th></tr>
        {action_rows(executed)}
      </table>
      <h3 style="margin-top:24px;">Open budget/bid recommendations ({len(recommendations)})</h3>
      <table style="border-collapse:collapse;width:100%;">
        <tr style="background:#f5f5f5;text-align:left;"><th style="padding:8px;">Campaign</th>
            <th style="padding:8px;">Type</th><th style="padding:8px;">Why</th></tr>
        {rec_rows}
      </table>
      {f'''<h3 style="margin-top:24px;color:#888;">Dry-run only ({len(dry_run)})</h3>
      <table style="border-collapse:collapse;width:100%;">
        <tr style="background:#f5f5f5;text-align:left;"><th style="padding:8px;">When</th>
            <th style="padding:8px;">Action</th><th style="padding:8px;">Reason</th></tr>
        {action_rows(dry_run)}
      </table>''' if dry_run else ''}
    </body></html>"""
    _send(to_email, f"[Ads Optimizer] Weekly Report — {account_name}", html)
