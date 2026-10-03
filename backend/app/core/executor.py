"""
Dispatches a PlannedAction to the matching GoogleAdsAccountClient method.

This is a second, independent safety layer on top of google_ads_client.py
structurally lacking any budget/bid-capable method: ALLOWED_METHODS is an
explicit allowlist, so even a typo'd or newly-added client method is not
reachable from here unless someone deliberately adds it to this set.
"""
from app.core.google_ads_client import GoogleAdsAccountClient
from app.core.rule_engine import PlannedAction

ALLOWED_METHODS = {
    "pause_campaign",
    "enable_campaign",
    "pause_ad_group",
    "enable_ad_group",
    "pause_ad",
    "enable_ad",
    "pause_keywords",
    "add_negative_keywords_ad_group",
    "add_negative_keywords_campaign",
}


class ForbiddenActionError(Exception):
    pass


def execute(client: GoogleAdsAccountClient, planned: PlannedAction, dry_run: bool) -> dict:
    if planned.method not in ALLOWED_METHODS:
        raise ForbiddenActionError(f"'{planned.method}' is not in ALLOWED_METHODS")

    if dry_run:
        return {"dry_run": True, "method": planned.method, "kwargs": planned.kwargs}

    func = getattr(client, planned.method)
    return func(**planned.kwargs)
