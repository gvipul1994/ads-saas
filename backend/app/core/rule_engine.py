"""
Same decision logic as the Windsor-based prototype, ported to query Google
Ads directly via GAQL and emit PlannedAction objects that map onto
GoogleAdsAccountClient's narrow write methods.

Thresholds are intentionally kept as plain module constants (overridable
per-account in a later version via GoogleAdsAccount columns) rather than
buried in a config file, so they're easy to find and tune.
"""
from dataclasses import dataclass, field

from app.core.google_ads_client import GoogleAdsAccountClient

LOOKBACK_DAYS = 30

NEG_KEYWORD_MIN_CLICKS = 10
NEG_KEYWORD_MIN_COST_MICROS = 5_000_000       # $5

PAUSE_KEYWORD_MIN_CLICKS = 15
PAUSE_KEYWORD_MIN_COST_MICROS = 10_000_000    # $10

PAUSE_AD_MIN_CLICKS = 20
PAUSE_AD_MIN_COST_MICROS = 10_000_000         # $10
MIN_ENABLED_ADS_TO_KEEP_PER_GROUP = 2

BUDGET_LOST_IS_THRESHOLD = 0.10
RANK_LOST_IS_THRESHOLD = 0.20
MIN_CONV_FOR_BID_RECOMMENDATION = 1


@dataclass
class PlannedAction:
    method: str          # method name on GoogleAdsAccountClient, e.g. "pause_ad"
    kwargs: dict
    reason: str
    # Human-readable action label stored in the audit log
    label: str = ""


@dataclass
class Recommendation:
    kind: str  # "budget" or "bid"
    campaign_id: str
    campaign_name: str
    detail: str
    metrics: dict = field(default_factory=dict)


def _during(days: int) -> str:
    return f"DURING LAST_{days}_DAYS" if days in (7, 14, 30) else f"segments.date DURING LAST_30_DAYS"


def find_negative_keyword_candidates(client: GoogleAdsAccountClient) -> list[PlannedAction]:
    query = f"""
        SELECT search_term_view.search_term, search_term_view.ad_group,
               campaign.id, metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM search_term_view
        WHERE segments.date {_during(LOOKBACK_DAYS)}
    """
    rows = client.search(query)

    agg: dict[tuple, dict] = {}
    for r in rows:
        term = r.search_term_view.search_term
        ad_group_resource = r.search_term_view.ad_group
        ad_group_id = ad_group_resource.split("/")[-1] if ad_group_resource else None
        if not term or not ad_group_id:
            continue
        key = (ad_group_id, term.lower())
        bucket = agg.setdefault(key, {"clicks": 0, "cost_micros": 0, "conversions": 0.0,
                                       "ad_group_id": ad_group_id, "term": term})
        bucket["clicks"] += r.metrics.clicks
        bucket["cost_micros"] += r.metrics.cost_micros
        bucket["conversions"] += r.metrics.conversions

    by_ad_group: dict[str, list[dict]] = {}
    for bucket in agg.values():
        if (bucket["clicks"] >= NEG_KEYWORD_MIN_CLICKS
                and bucket["cost_micros"] >= NEG_KEYWORD_MIN_COST_MICROS
                and bucket["conversions"] == 0):
            by_ad_group.setdefault(bucket["ad_group_id"], []).append(bucket)

    actions = []
    for ad_group_id, candidates in by_ad_group.items():
        keywords = [{"text": c["term"], "match_type": "EXACT"} for c in candidates]
        reason = (f"{len(candidates)} search term(s), >= {NEG_KEYWORD_MIN_CLICKS} clicks, "
                  f">= ${NEG_KEYWORD_MIN_COST_MICROS/1_000_000:.2f} spend, 0 conversions "
                  f"over {LOOKBACK_DAYS}d: " + ", ".join(f'"{c["term"]}"' for c in candidates[:10]))
        actions.append(PlannedAction(
            method="add_negative_keywords_ad_group",
            kwargs={"ad_group_id": ad_group_id, "keywords": keywords},
            reason=reason,
            label="add_negative_keywords",
        ))
    return actions


def find_keyword_pause_candidates(client: GoogleAdsAccountClient) -> list[PlannedAction]:
    query = f"""
        SELECT ad_group_criterion.criterion_id, ad_group_criterion.keyword.text,
               ad_group_criterion.ad_group, ad_group_criterion.status,
               metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM keyword_view
        WHERE segments.date {_during(LOOKBACK_DAYS)}
          AND ad_group_criterion.status = 'ENABLED'
    """
    rows = client.search(query)

    agg: dict[str, dict] = {}
    for r in rows:
        crit_id = str(r.ad_group_criterion.criterion_id)
        ad_group_id = r.ad_group_criterion.ad_group.split("/")[-1]
        bucket = agg.setdefault(crit_id, {"clicks": 0, "cost_micros": 0, "conversions": 0.0,
                                           "ad_group_id": ad_group_id, "text": r.ad_group_criterion.keyword.text})
        bucket["clicks"] += r.metrics.clicks
        bucket["cost_micros"] += r.metrics.cost_micros
        bucket["conversions"] += r.metrics.conversions

    by_ad_group: dict[str, list[tuple[str, dict]]] = {}
    for crit_id, bucket in agg.items():
        if (bucket["clicks"] >= PAUSE_KEYWORD_MIN_CLICKS
                and bucket["cost_micros"] >= PAUSE_KEYWORD_MIN_COST_MICROS
                and bucket["conversions"] == 0):
            by_ad_group.setdefault(bucket["ad_group_id"], []).append((crit_id, bucket))

    actions = []
    for ad_group_id, candidates in by_ad_group.items():
        crit_ids = [c for c, _ in candidates]
        reason = (f"{len(candidates)} keyword(s), >= {PAUSE_KEYWORD_MIN_CLICKS} clicks, "
                  f">= ${PAUSE_KEYWORD_MIN_COST_MICROS/1_000_000:.2f} spend, 0 conversions "
                  f"over {LOOKBACK_DAYS}d: " + ", ".join(f'"{b["text"]}"' for _, b in candidates[:10]))
        actions.append(PlannedAction(
            method="pause_keywords",
            kwargs={"ad_group_id": ad_group_id, "criterion_ids": crit_ids},
            reason=reason,
            label="pause_keywords",
        ))
    return actions


def find_ad_pause_candidates(client: GoogleAdsAccountClient) -> list[PlannedAction]:
    query = f"""
        SELECT ad_group_ad.ad.id, ad_group_ad.ad_group, ad_group_ad.status,
               metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM ad_group_ad
        WHERE segments.date {_during(LOOKBACK_DAYS)}
    """
    rows = client.search(query)

    agg: dict[tuple, dict] = {}
    enabled_count: dict[str, int] = {}
    seen_enabled: set[tuple] = set()
    for r in rows:
        ad_id = str(r.ad_group_ad.ad.id)
        ad_group_id = r.ad_group_ad.ad_group.split("/")[-1]
        status = r.ad_group_ad.status.name
        key = (ad_group_id, ad_id)
        if status == "ENABLED" and key not in seen_enabled:
            seen_enabled.add(key)
            enabled_count[ad_group_id] = enabled_count.get(ad_group_id, 0) + 1
        if status != "ENABLED":
            continue
        bucket = agg.setdefault(key, {"clicks": 0, "cost_micros": 0, "conversions": 0.0,
                                       "ad_group_id": ad_group_id, "ad_id": ad_id})
        bucket["clicks"] += r.metrics.clicks
        bucket["cost_micros"] += r.metrics.cost_micros
        bucket["conversions"] += r.metrics.conversions

    actions = []
    for (ad_group_id, ad_id), bucket in agg.items():
        if not (bucket["clicks"] >= PAUSE_AD_MIN_CLICKS
                and bucket["cost_micros"] >= PAUSE_AD_MIN_COST_MICROS
                and bucket["conversions"] == 0):
            continue
        if enabled_count.get(ad_group_id, 0) <= MIN_ENABLED_ADS_TO_KEEP_PER_GROUP:
            continue
        reason = (f"Ad {ad_id}: {bucket['clicks']} clicks, ${bucket['cost_micros']/1_000_000:.2f} spend, "
                  f"0 conversions over {LOOKBACK_DAYS}d (ad group has {enabled_count[ad_group_id]} other enabled ads)")
        actions.append(PlannedAction(
            method="pause_ad",
            kwargs={"ad_group_id": ad_group_id, "ad_id": ad_id},
            reason=reason,
            label="pause_ad",
        ))
        enabled_count[ad_group_id] -= 1
    return actions


def find_budget_and_bid_recommendations(client: GoogleAdsAccountClient) -> list[Recommendation]:
    """Never executed — only ever surfaced to the UI/email for a human to act on."""
    query = f"""
        SELECT campaign.id, campaign.name, campaign.status,
               metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value,
               metrics.search_budget_lost_impression_share, metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE segments.date {_during(LOOKBACK_DAYS)}
          AND campaign.status = 'ENABLED'
    """
    rows = client.search(query)

    agg: dict[str, dict] = {}
    for r in rows:
        cid = str(r.campaign.id)
        b = agg.setdefault(cid, {"name": r.campaign.name, "clicks": 0, "cost_micros": 0,
                                  "conversions": 0.0, "conversion_value": 0.0,
                                  "budget_lost_is": [], "rank_lost_is": []})
        b["clicks"] += r.metrics.clicks
        b["cost_micros"] += r.metrics.cost_micros
        b["conversions"] += r.metrics.conversions
        b["conversion_value"] += r.metrics.conversions_value
        if r.metrics.search_budget_lost_impression_share >= 0:
            b["budget_lost_is"].append(r.metrics.search_budget_lost_impression_share)
        if r.metrics.search_rank_lost_impression_share >= 0:
            b["rank_lost_is"].append(r.metrics.search_rank_lost_impression_share)

    recs = []
    for cid, b in agg.items():
        avg_budget_lost = sum(b["budget_lost_is"]) / len(b["budget_lost_is"]) if b["budget_lost_is"] else 0
        avg_rank_lost = sum(b["rank_lost_is"]) / len(b["rank_lost_is"]) if b["rank_lost_is"] else 0
        cost = b["cost_micros"] / 1_000_000

        if avg_budget_lost >= BUDGET_LOST_IS_THRESHOLD and b["conversions"] > 0:
            recs.append(Recommendation(
                kind="budget", campaign_id=cid, campaign_name=b["name"],
                detail=(f"Losing ~{avg_budget_lost*100:.0f}% of possible search impressions to budget "
                        f"limits over {LOOKBACK_DAYS}d. Converted {b['conversions']:.1f} times from "
                        f"${cost:.2f} spend — a higher budget would likely capture more of that demand."),
                metrics={"cost": cost, "conversions": b["conversions"],
                         "conversion_value": b["conversion_value"], "budget_lost_is": avg_budget_lost},
            ))
        if avg_rank_lost >= RANK_LOST_IS_THRESHOLD and b["conversions"] >= MIN_CONV_FOR_BID_RECOMMENDATION:
            recs.append(Recommendation(
                kind="bid", campaign_id=cid, campaign_name=b["name"],
                detail=(f"Losing ~{avg_rank_lost*100:.0f}% of possible search impressions to ad rank "
                        f"(bids/quality) over {LOOKBACK_DAYS}d, converting {b['conversions']:.1f} times. "
                        f"A higher bid or target CPA/ROAS could win more of that traffic."),
                metrics={"cost": cost, "conversions": b["conversions"],
                         "conversion_value": b["conversion_value"], "rank_lost_is": avg_rank_lost},
            ))
    return recs


def run_all_rules(client: GoogleAdsAccountClient) -> tuple[list[PlannedAction], list[Recommendation]]:
    actions: list[PlannedAction] = []
    actions += find_negative_keyword_candidates(client)
    actions += find_keyword_pause_candidates(client)
    actions += find_ad_pause_candidates(client)
    recommendations = find_budget_and_bid_recommendations(client)
    return actions, recommendations
