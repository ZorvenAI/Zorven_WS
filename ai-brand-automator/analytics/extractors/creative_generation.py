from analytics.extractors.base import BaseExtractor


class CreativeGenerationExtractor(BaseExtractor):
    """Extracts metrics from creative generation (CGA) results.

    Data lives under result_data["node_results"]["creative_generation"].
    Extracts ~8 metrics covering image generation, copy variants,
    compliance, quality, and overall confidence.
    """

    def extract(self, job) -> list:
        result = job.result_data or {}
        node_results = result.get("node_results", {})
        cga = node_results.get("creative_generation", {})
        if not cga:
            cga = result  # fallback for direct result_data
        metrics = []

        # Images generated count
        pkg = cga.get("creative_package", {})
        if isinstance(pkg, dict):
            total_images = pkg.get("total_images_generated")
            if total_images is None:
                total_images = cga.get("total_images_generated")
            if total_images is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "images_generated_count",
                        float(total_images),
                        "creative_generation",
                        unit="count",
                        agent_source="creative-generation-agent",
                    )
                )

            # Image generation cost
            cost = pkg.get("image_gen_cost_usd")
            if cost is None:
                cost = cga.get("image_gen_cost_usd")
            if cost is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "image_generation_cost_usd",
                        float(cost),
                        "creative_generation",
                        unit="currency",
                        agent_source="creative-generation-agent",
                    )
                )

            # Creative quality score
            quality = pkg.get("creative_quality_score")
            if quality is None:
                quality = cga.get("creative_quality_score")
            if quality is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "creative_quality_score",
                        (
                            float(quality) * 100
                            if float(quality) <= 1
                            else float(quality)
                        ),
                        "creative_generation",
                        agent_source="creative-generation-agent",
                    )
                )

            # Compliance pass rate
            compliance_rate = pkg.get("compliance_pass_rate")
            if compliance_rate is None:
                compliance_rate = cga.get("compliance_pass_rate")
            if compliance_rate is not None:
                metrics.append(
                    self._make_metric(
                        job,
                        "compliance_pass_rate",
                        (
                            float(compliance_rate) * 100
                            if float(compliance_rate) <= 1
                            else float(compliance_rate)
                        ),
                        "creative_generation",
                        unit="percent",
                        agent_source="creative-generation-agent",
                    )
                )

            # Creative packages produced (ad set packages count)
            ad_set_packages = pkg.get("ad_set_packages", [])
            if isinstance(ad_set_packages, list) and ad_set_packages:
                metrics.append(
                    self._make_metric(
                        job,
                        "creative_packages_produced",
                        float(len(ad_set_packages)),
                        "creative_generation",
                        unit="count",
                        agent_source="creative-generation-agent",
                    )
                )

        # Copy variants generated (count from ad_units or copy_variants)
        ad_units = cga.get("ad_units", [])
        if isinstance(ad_units, list) and ad_units:
            metrics.append(
                self._make_metric(
                    job,
                    "copy_variants_generated",
                    float(len(ad_units)),
                    "creative_generation",
                    unit="count",
                    agent_source="creative-generation-agent",
                )
            )

        # Overall confidence
        confidence = cga.get("confidence_score")
        if confidence is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "creative_confidence",
                    (
                        float(confidence) * 100
                        if float(confidence) <= 1
                        else float(confidence)
                    ),
                    "creative_generation",
                    agent_source="creative-generation-agent",
                )
            )

        # Execution time
        exec_time = cga.get("execution_time_ms")
        if exec_time is not None:
            metrics.append(
                self._make_metric(
                    job,
                    "creative_generation_execution_time",
                    float(exec_time),
                    "creative_generation",
                    unit="milliseconds",
                    agent_source="creative-generation-agent",
                )
            )

        return [m for m in metrics if m.metric_value is not None]
