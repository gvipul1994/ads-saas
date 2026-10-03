"""
Thin wrapper around Google's official google-ads Python library.

SAFETY DESIGN: unlike a generic "run any mutate operation" client, this
module exposes ONLY narrow, single-purpose functions, each of which can
touch exactly one field (usually `.status`) or create exactly one kind of
new resource. There is no function here capable of writing `budget_micros`,
`cpc_bid_micros`, `target_cpa`, `target_roas`, or any bidding_strategy
field — those fields simply never appear in any Operation built by this
file. This is a stronger guarantee than a runtime allowlist check: the
capability does not exist in the code, so there's nothing to bypass.

Budget/bid changes are ALWAYS surfaced as Recommendation rows (see
rule_engine.py) for a human to apply manually in Google Ads.
"""
from google.ads.googleads.client import GoogleAdsClient as _GAClient
from google.ads.googleads.errors import GoogleAdsException

from app.config import settings


def _build_client(refresh_token: str, login_customer_id: str) -> _GAClient:
    config = {
        "developer_token": settings.google_ads_developer_token,
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "refresh_token": refresh_token,
        "login_customer_id": login_customer_id,
        "use_proto_plus": True,
    }
    return _GAClient.load_from_dict(config)


class GoogleAdsAccountClient:
    """One instance per connected customer account. Holds no mutation
    capability beyond the explicit methods defined below."""

    def __init__(self, refresh_token: str, customer_id: str, login_customer_id: str):
        self.customer_id = customer_id.replace("-", "")
        self.client = _build_client(refresh_token, login_customer_id.replace("-", ""))

    # ---------- Reads (always safe) ----------

    def search(self, gaql_query: str) -> list[dict]:
        """Run a GAQL query, return rows as plain dicts (resource-name-free,
        flattened to dotted field names for easy access)."""
        service = self.client.get_service("GoogleAdsService")
        rows = []
        response = service.search_stream(customer_id=self.customer_id, query=gaql_query)
        for batch in response:
            for row in batch.results:
                rows.append(row)
        return rows

    @staticmethod
    def list_accessible_customers(refresh_token: str) -> list[str]:
        client = _build_client(refresh_token, login_customer_id="")
        service = client.get_service("CustomerService")
        response = service.list_accessible_customers()
        return [rn.split("/")[-1] for rn in response.resource_names]

    # ---------- Writes: campaign status only ----------

    def pause_campaign(self, campaign_id: str) -> dict:
        return self._set_campaign_status(campaign_id, "PAUSED")

    def enable_campaign(self, campaign_id: str) -> dict:
        return self._set_campaign_status(campaign_id, "ENABLED")

    def _set_campaign_status(self, campaign_id: str, status: str) -> dict:
        service = self.client.get_service("CampaignService")
        operation = self.client.get_type("CampaignOperation")
        campaign = operation.update
        campaign.resource_name = service.campaign_path(self.customer_id, campaign_id)
        campaign.status = self.client.enums.CampaignStatusEnum[status]
        self.client.copy_from(
            operation.update_mask,
            self.client.get_type("FieldMask")(paths=["status"]),
        )
        response = service.mutate_campaigns(customer_id=self.customer_id, operations=[operation])
        return {"resource_name": response.results[0].resource_name}

    # ---------- Writes: ad group status only ----------

    def pause_ad_group(self, ad_group_id: str) -> dict:
        return self._set_ad_group_status(ad_group_id, "PAUSED")

    def enable_ad_group(self, ad_group_id: str) -> dict:
        return self._set_ad_group_status(ad_group_id, "ENABLED")

    def _set_ad_group_status(self, ad_group_id: str, status: str) -> dict:
        service = self.client.get_service("AdGroupService")
        operation = self.client.get_type("AdGroupOperation")
        ad_group = operation.update
        ad_group.resource_name = service.ad_group_path(self.customer_id, ad_group_id)
        ad_group.status = self.client.enums.AdGroupStatusEnum[status]
        self.client.copy_from(
            operation.update_mask,
            self.client.get_type("FieldMask")(paths=["status"]),
        )
        response = service.mutate_ad_groups(customer_id=self.customer_id, operations=[operation])
        return {"resource_name": response.results[0].resource_name}

    # ---------- Writes: ad status only ----------

    def pause_ad(self, ad_group_id: str, ad_id: str) -> dict:
        return self._set_ad_status(ad_group_id, ad_id, "PAUSED")

    def enable_ad(self, ad_group_id: str, ad_id: str) -> dict:
        return self._set_ad_status(ad_group_id, ad_id, "ENABLED")

    def _set_ad_status(self, ad_group_id: str, ad_id: str, status: str) -> dict:
        service = self.client.get_service("AdGroupAdService")
        operation = self.client.get_type("AdGroupAdOperation")
        ad_group_ad = operation.update
        ad_group_ad.resource_name = service.ad_group_ad_path(self.customer_id, f"{ad_group_id}~{ad_id}")
        ad_group_ad.status = self.client.enums.AdGroupAdStatusEnum[status]
        self.client.copy_from(
            operation.update_mask,
            self.client.get_type("FieldMask")(paths=["status"]),
        )
        response = service.mutate_ad_group_ads(customer_id=self.customer_id, operations=[operation])
        return {"resource_name": response.results[0].resource_name}

    # ---------- Writes: keyword status only (pause, never bid) ----------

    def pause_keywords(self, ad_group_id: str, criterion_ids: list[str]) -> dict:
        service = self.client.get_service("AdGroupCriterionService")
        operations = []
        for crit_id in criterion_ids:
            op = self.client.get_type("AdGroupCriterionOperation")
            crit = op.update
            crit.resource_name = service.ad_group_criterion_path(self.customer_id, ad_group_id, crit_id)
            crit.status = self.client.enums.AdGroupCriterionStatusEnum.PAUSED
            self.client.copy_from(op.update_mask, self.client.get_type("FieldMask")(paths=["status"]))
            operations.append(op)
        response = service.mutate_ad_group_criteria(customer_id=self.customer_id, operations=operations)
        return {"count": len(response.results)}

    # ---------- Writes: new negative keywords only (never positive bids) ----------

    def add_negative_keywords_ad_group(self, ad_group_id: str, keywords: list[dict]) -> dict:
        """keywords: [{"text": "...", "match_type": "EXACT"|"PHRASE"|"BROAD"}]"""
        service = self.client.get_service("AdGroupCriterionService")
        operations = []
        for kw in keywords:
            op = self.client.get_type("AdGroupCriterionOperation")
            crit = op.create
            crit.ad_group = self.client.get_service("AdGroupService").ad_group_path(self.customer_id, ad_group_id)
            crit.negative = True
            crit.keyword.text = kw["text"]
            crit.keyword.match_type = self.client.enums.KeywordMatchTypeEnum[kw.get("match_type", "EXACT")]
            operations.append(op)
        response = service.mutate_ad_group_criteria(customer_id=self.customer_id, operations=operations)
        return {"count": len(response.results)}

    def add_negative_keywords_campaign(self, campaign_id: str, keywords: list[dict]) -> dict:
        service = self.client.get_service("CampaignCriterionService")
        operations = []
        for kw in keywords:
            op = self.client.get_type("CampaignCriterionOperation")
            crit = op.create
            crit.campaign = self.client.get_service("CampaignService").campaign_path(self.customer_id, campaign_id)
            crit.negative = True
            crit.keyword.text = kw["text"]
            crit.keyword.match_type = self.client.enums.KeywordMatchTypeEnum[kw.get("match_type", "EXACT")]
            operations.append(op)
        response = service.mutate_campaign_criteria(customer_id=self.customer_id, operations=operations)
        return {"count": len(response.results)}


__all__ = ["GoogleAdsAccountClient", "GoogleAdsException"]
