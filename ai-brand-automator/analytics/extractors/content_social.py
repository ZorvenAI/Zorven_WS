from analytics.extractors.base import BaseExtractor


class ContentSocialExtractor(BaseExtractor):
    """Extracts metrics from content and social publishing pipelines."""

    def extract(self, job) -> list:
        result = job.result_data or {}
        metrics = []

        # Content agent: word count
        content = result.get("content", {})
        if not content:
            content = result.get("blog_content", {})

        if content:
            body = content.get("body", "") or content.get("content", "")
            if isinstance(body, str) and body.strip():
                word_count = len(body.split())
                metrics.append(
                    self._make_metric(
                        job,
                        "word_count",
                        float(word_count),
                        "content",
                        unit="count",
                        agent_source="content-agent",
                    )
                )

        # Social agent: platforms posted
        social = result.get("social", {})
        if not social:
            social = result.get("social_promotion", {})

        if social:
            platforms = social.get("platforms_posted", [])
            if isinstance(platforms, list):
                metrics.append(
                    self._make_metric(
                        job,
                        "platforms_posted",
                        float(len(platforms)),
                        "social",
                        unit="count",
                        agent_source="social-agent",
                    )
                )
            elif isinstance(platforms, int):
                metrics.append(
                    self._make_metric(
                        job,
                        "platforms_posted",
                        float(platforms),
                        "social",
                        unit="count",
                        agent_source="social-agent",
                    )
                )

        return metrics
