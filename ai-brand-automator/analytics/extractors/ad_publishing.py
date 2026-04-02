from analytics.extractors.base import BaseExtractor


class AdPublishingExtractor(BaseExtractor):
    """Extracts metrics from ad publishing pipelines.

    Data lives under result_data["node_results"]["ad_publishing"].
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        metrics = []

        # Ad publishing node output
        adpub = node_results.get("ad_publishing", {})
        if not adpub:
            adpub = result.get("ad_publishing", {})
        if not adpub:
            adpub = result

        if not adpub or not isinstance(adpub, dict):
            return metrics

        sandbox_mode = adpub.get("sandbox_mode", True)
        metadata = {"sandbox_mode": sandbox_mode}

        # Campaigns published
        published = adpub.get("published_campaign", {})
        if not published:
            published = adpub.get("published_entities", {})

        if published and isinstance(published, dict):
            # Campaign count
            campaign_id = published.get("campaign_id", "")
            if campaign_id:
                metrics.append(
                    self._make_metric(
                        job,
                        "campaigns_published",
                        1.0,
                        "ad_publishing",
                        unit="count",
                        agent_source="ad-publishing-agent",
                        metadata=metadata,
                    )
                )

            # Ad sets published
            ad_sets = published.get("ad_sets", [])
            if isinstance(ad_sets, list) and ad_sets:
                metrics.append(
                    self._make_metric(
                        job,
                        "ad_sets_published",
                        float(len(ad_sets)),
                        "ad_publishing",
                        unit="count",
                        agent_source="ad-publishing-agent",
                        metadata=metadata,
                    )
                )

            # Ads published
            ads = published.get("ads", [])
            if isinstance(ads, list) and ads:
                metrics.append(
                    self._make_metric(
                        job,
                        "ads_published",
                        float(len(ads)),
                        "ad_publishing",
                        unit="count",
                        agent_source="ad-publishing-agent",
                        metadata=metadata,
                    )
                )

        # Daily spend committed
        spend = adpub.get("daily_spend_committed_usd")
        if spend and isinstance(spend, (int, float)) and spend > 0:
            metrics.append(
                self._make_metric(
                    job,
                    "daily_spend_committed_usd",
                    float(spend),
                    "ad_publishing",
                    unit="usd",
                    agent_source="ad-publishing-agent",
                    metadata=metadata,
                )
            )

        # Targeting audience size
        audience_size = adpub.get("targeting_audience_size")
        if (
            audience_size
            and isinstance(audience_size, (int, float))
            and audience_size > 0
        ):
            metrics.append(
                self._make_metric(
                    job,
                    "targeting_audience_size",
                    float(audience_size),
                    "ad_publishing",
                    unit="count",
                    agent_source="ad-publishing-agent",
                    metadata=metadata,
                )
            )

        # Approval status (encode as 1=approved, 0.5=partial, 0=rejected)
        approval_status = adpub.get("approval_status", "")
        if approval_status:
            status_map = {
                "approved": 1.0,
                "partial": 0.5,
                "rejected": 0.0,
            }
            val = status_map.get(approval_status)
            if val is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "approval_status",
                        val,
                        "ad_publishing",
                        unit="score",
                        agent_source="ad-publishing-agent",
                        metadata={
                            **metadata,
                            "approval_status_label": approval_status,
                        },
                    )
                )

        return metrics
