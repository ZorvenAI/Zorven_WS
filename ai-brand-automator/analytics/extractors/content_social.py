from analytics.extractors.base import BaseExtractor


class ContentSocialExtractor(BaseExtractor):
    """Extracts metrics from content and social publishing pipelines.

    Data lives under result_data["node_results"][<node_id>].
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        metrics = []

        # Content agent: word count — node_id: "blog_author"
        content = node_results.get("blog_author", {})
        if not content:
            content = result.get("content", {})
        if not content:
            content = result.get("blog_content", {})

        if content:
            # blog_content is a string, word_count may be a field
            body = ""
            if isinstance(content, str):
                body = content
            elif isinstance(content, dict):
                body = (
                    content.get("blog_content", "")
                    or content.get("body", "")
                    or content.get("content", "")
                )
                # Also check direct word_count field
                wc = content.get("word_count")
                if wc and isinstance(wc, (int, float)) and wc > 0:
                    metrics.append(
                        self._make_metric(
                            job,
                            "word_count",
                            float(wc),
                            "content",
                            unit="count",
                            agent_source="content-agent",
                        )
                    )
                    body = ""  # Skip manual count

            if isinstance(body, str) and body.strip():
                word_count = len(body.split())
                if word_count > 0:
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

        # Social agent: platforms posted — node_id: "social_promoter"
        social = node_results.get("social_promoter", {})
        if not social:
            social = result.get("social", {})
        if not social:
            social = result.get("social_promotion", {})

        if social and isinstance(social, dict):
            platforms = social.get("platforms_posted", [])
            if isinstance(platforms, list) and platforms:
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
            elif isinstance(platforms, int) and platforms > 0:
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
