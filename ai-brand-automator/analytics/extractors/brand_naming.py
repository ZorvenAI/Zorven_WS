from analytics.extractors.base import BaseExtractor


class BrandNamingExtractor(BaseExtractor):
    """Extracts metrics from brand naming & tagline (NTA) results.

    Data lives under result_data["node_results"]["brand_naming"].
    Extracts 11 metrics covering name scoring, availability,
    tagline quality, and overall confidence.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        nta = node_results.get("brand_naming", {})
        if not nta:
            nta = result  # fallback for direct result_data
        metrics = []

        # Name candidates count
        candidates = nta.get("name_candidates", [])
        if isinstance(candidates, list) and candidates:
            metrics.append(
                self._make_metric(
                    job,
                    "naming_candidates_count",
                    float(len(candidates)),
                    "brand_naming",
                    unit="count",
                    agent_source="brand-naming-agent",
                )
            )

            # Top candidate overall score
            top = candidates[0] if candidates else {}
            if isinstance(top, dict):
                top_scores = top.get("scores", {})
                if isinstance(top_scores, dict):
                    overall = top_scores.get("overall")
                    if overall is not None:
                        metrics.append(
                            self._make_metric(
                                job,
                                "naming_top_score",
                                float(overall),
                                "brand_naming",
                                agent_source="brand-naming-agent",
                            )
                        )

            # Average scores across candidates
            for dim in ("linguistic", "memorability", "availability", "strategy_alignment"):
                scores = []
                for c in candidates:
                    if isinstance(c, dict):
                        s = (c.get("scores") or {}).get(dim)
                        if s is not None:
                            scores.append(float(s))
                if scores:
                    avg = sum(scores) / len(scores)
                    metrics.append(
                        self._make_metric(
                            job,
                            f"naming_{dim}_avg",
                            round(avg, 1),
                            "brand_naming",
                            agent_source="brand-naming-agent",
                        )
                    )

        # Domain availability percentage
        avail_results = nta.get("availability_results", {})
        if isinstance(avail_results, dict) and avail_results:
            total = 0
            domain_available = 0
            trademark_clear = 0
            trademark_total = 0
            for name, avail in avail_results.items():
                if not isinstance(avail, dict):
                    continue
                domain = avail.get("domain", {})
                if isinstance(domain, dict):
                    com = domain.get(".com")
                    if com is not None:
                        total += 1
                        if com:
                            domain_available += 1
                tm = avail.get("trademark", {})
                if isinstance(tm, dict):
                    clear = tm.get("clear")
                    if clear is not None:
                        trademark_total += 1
                        if clear:
                            trademark_clear += 1

            if total > 0:
                metrics.append(
                    self._make_metric(
                        job,
                        "naming_domain_available_pct",
                        round((domain_available / total) * 100, 1),
                        "brand_naming",
                        unit="percentage",
                        agent_source="brand-naming-agent",
                    )
                )
            if trademark_total > 0:
                metrics.append(
                    self._make_metric(
                        job,
                        "naming_trademark_clear_pct",
                        round((trademark_clear / trademark_total) * 100, 1),
                        "brand_naming",
                        unit="percentage",
                        agent_source="brand-naming-agent",
                    )
                )

        # Taglines count
        taglines = nta.get("taglines", [])
        if isinstance(taglines, list):
            metrics.append(
                self._make_metric(
                    job,
                    "naming_taglines_count",
                    float(len(taglines)),
                    "brand_naming",
                    unit="count",
                    agent_source="brand-naming-agent",
                )
            )

        # Overall naming confidence
        confidence = nta.get("confidence_score")
        if confidence is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "naming_confidence",
                    float(confidence) * 100,  # normalize 0-1 to 0-100
                    "brand_naming",
                    agent_source="brand-naming-agent",
                )
            )

        # Execution time
        exec_time = nta.get("execution_time_ms")
        if exec_time is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "naming_execution_time",
                    float(exec_time),
                    "brand_naming",
                    unit="milliseconds",
                    agent_source="brand-naming-agent",
                )
            )

        return [m for m in metrics if m.metric_value is not None]
