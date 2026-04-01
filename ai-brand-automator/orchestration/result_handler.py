"""
Shared result handler for pipeline job updates.

Extracted from the HTTP callback view so both the HTTP callback endpoint
and the Kafka result consumer can reuse the same logic.

handle_pipeline_result() is the single entry-point:
  - Atomic row lock (select_for_update)
  - Updates job fields (progress, status, result_data, error, manifest)
  - Caches state in Redis for fast UI polling
  - On COMPLETED: auto-creates an assistant ChatMessage with the summary
"""

import logging

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import AnalysisJob, PipelineManifest

logger = logging.getLogger(__name__)


def handle_pipeline_result(
    job_id,
    *,
    status=None,
    progress=None,
    result_data=None,
    error_message=None,
    resolved_manifest_id=None,
):
    """Process a pipeline result update for the given job.

    Called by both the HTTP callback endpoint and the Kafka result consumer.
    Uses ``select_for_update()`` row locking for idempotent processing
    when both paths fire for the same event.

    Returns:
        True if the update was applied, False if the job was not found.
    """
    with transaction.atomic():
        try:
            job = AnalysisJob.objects.select_for_update().get(job_id=job_id)
        except AnalysisJob.DoesNotExist:
            logger.warning("handle_pipeline_result: job %s not found", job_id)
            return False

        # Skip if job already in terminal state (idempotent guard)
        if job.status in (
            AnalysisJob.Status.COMPLETED,
            AnalysisJob.Status.FAILED,
        ):
            logger.info(
                "Job %s already in terminal state %s, skipping update",
                job_id,
                job.status,
            )
            return True

        update_fields = ["updated_at"]

        # Update progress
        if progress is not None:
            job.progress = progress
            update_fields.append("progress")

        # Update status
        if status is not None:
            job.status = status
            update_fields.append("status")

            if status in (
                AnalysisJob.Status.COMPLETED,
                AnalysisJob.Status.FAILED,
            ):
                job.completed_at = timezone.now()
                update_fields.append("completed_at")

        # Update result_data — merge node_results progressively so that
        # per-level progress callbacks accumulate rather than overwrite
        # each other's data (each level only sends its own node_results).
        if result_data is not None:
            existing = job.result_data or {}
            incoming_nodes = result_data.get("node_results", {})
            existing_nodes = existing.get("node_results", {})

            if incoming_nodes and existing_nodes:
                # Deep-merge node_results: incoming overwrites per-key
                merged_nodes = {**existing_nodes, **incoming_nodes}
                merged = {**existing, **result_data, "node_results": merged_nodes}
                job.result_data = merged
            else:
                job.result_data = result_data
            update_fields.append("result_data")

        # Update error_message
        if error_message is not None:
            job.error_message = error_message
            update_fields.append("error_message")

        # Handle resolved_manifest_id (intent routing resolution)
        if resolved_manifest_id and job.manifest is None:
            try:
                resolved = PipelineManifest.objects.get(
                    pipeline_id=resolved_manifest_id,
                    is_active=True,
                )
                job.manifest = resolved
                update_fields.append("manifest")
                logger.info(
                    "Job %s: manifest resolved to %s via intent routing",
                    job.job_id,
                    resolved_manifest_id,
                )
            except PipelineManifest.DoesNotExist:
                logger.warning(
                    "Job %s: resolved_manifest_id '%s' not found",
                    job.job_id,
                    resolved_manifest_id,
                )

        job.save(update_fields=update_fields)

    # Cache job status in Redis for fast polling
    _update_redis_cache(job)

    # Broadcast to WebSocket clients via Channels
    _broadcast_to_workspace(job, status)

    # On terminal states: auto-create ChatMessage and release session lock
    if status in (AnalysisJob.Status.COMPLETED, AnalysisJob.Status.FAILED):
        _release_session_lock(job)
        if status == AnalysisJob.Status.COMPLETED:
            _save_final_chat_message(job)
            _update_workflow_snapshot(job)

            # Extract analytics metrics (async, non-blocking)
            try:
                from analytics.tasks import extract_metrics_task

                extract_metrics_task.delay(job.id)
            except Exception:
                logger.exception(
                    "Failed to dispatch analytics extraction for job %s",
                    job.job_id,
                )

    logger.info("Job %s result processed (status=%s)", job.job_id, status)
    return True


def _release_session_lock(job):
    """Clear the pipeline session lock so new chat messages can proceed."""
    session_id = (job.input_context or {}).get("session_id")
    if not session_id:
        return
    try:
        cache.delete(f"lock:chat:pipeline:{session_id}")
    except Exception:
        pass


def _update_redis_cache(job):
    """Push lightweight job state into Redis for quick-status polling."""
    try:
        cache_key = f"job:status:{job.job_id}"

        # Preserve last_thought from existing cache (set by Kafka TraceConsumer)
        existing = cache.get(cache_key) or {}

        cache_data = {
            "status": job.status,
            "progress": job.progress,
        }

        # Derive current_node and progress_percent from progress dict
        progress = job.progress or {}
        current_node = next(
            (
                nid
                for nid, info in progress.items()
                if isinstance(info, dict) and info.get("status") == "running"
            ),
            None,
        )
        total = len(progress)
        done = sum(
            1
            for v in progress.values()
            if isinstance(v, dict) and v.get("status") in ("done", "failed")
        )
        percent = int((done / total) * 100) if total else 0

        cache_data["current_node"] = current_node
        cache_data["progress_percent"] = percent
        cache_data["last_thought"] = existing.get("last_thought")

        if job.status == AnalysisJob.Status.COMPLETED:
            cache_data["result_data"] = job.result_data
            cache_data["manifest_name"] = job.manifest.name if job.manifest else None
        elif job.status == AnalysisJob.Status.FAILED:
            cache_data["error_message"] = job.error_message
        cache.set(cache_key, cache_data, timeout=3600)
        logger.info(
            "Redis cache updated for job %s: current_node=%s, "
            "progress_percent=%d%%, status=%s",
            job.job_id,
            current_node,
            percent,
            job.status,
        )
    except Exception as exc:
        logger.warning(
            "Redis cache update failed for job %s: %s",
            job.job_id,
            exc,
            exc_info=True,
        )


def _broadcast_to_workspace(job, status):
    """Broadcast job progress/completion to workspace WebSocket clients.

    Sends to the tenant's channel group so all connected workspace clients
    receive real-time updates. Guarded by try/except so polling fallback
    always works even if Channels is not configured.
    """
    tenant_id = getattr(job, "tenant_id", None)
    if not tenant_id:
        return

    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        group_name = f"workspace_{tenant_id}"

        # Derive progress metrics
        progress = job.progress or {}
        current_node = next(
            (
                nid
                for nid, info in progress.items()
                if isinstance(info, dict) and info.get("status") == "running"
            ),
            None,
        )
        total = len(progress)
        done = sum(
            1
            for v in progress.values()
            if isinstance(v, dict) and v.get("status") in ("done", "failed")
        )
        percent = int((done / total) * 100) if total else 0

        data = {
            "job_id": str(job.job_id),
            "status": job.status,
            "current_node": current_node,
            "progress_percent": percent,
            "progress": progress,
        }

        if status in (
            AnalysisJob.Status.COMPLETED,
            AnalysisJob.Status.FAILED,
        ):
            event_type = "job.completed"
            if status == AnalysisJob.Status.FAILED:
                data["error_message"] = job.error_message
        else:
            event_type = "job.progress"

        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": event_type, "data": data},
        )
    except Exception as exc:
        logger.debug(
            "WebSocket broadcast skipped for job %s: %s",
            job.job_id,
            exc,
        )


def _save_final_chat_message(job):
    """Create an assistant ChatMessage with the pipeline result summary.

    Looks up the originating ChatSession via ``input_context["session_id"]``
    and appends a summary message so the user sees the result in their
    chat history.
    """
    session_id = (job.input_context or {}).get("session_id")
    if not session_id:
        return

    try:
        from ai_services.models import ChatMessage, ChatSession

        session = ChatSession.objects.get(session_id=session_id)
    except ChatSession.DoesNotExist:
        logger.warning(
            "Job %s: session '%s' not found for final message",
            job.job_id,
            session_id,
        )
        return
    except Exception:
        logger.exception("Job %s: error looking up session", job.job_id)
        return

    # Build a human-readable summary from result_data
    summary = _build_result_summary(job)

    result_metadata = {
        "job_id": str(job.job_id),
        "source": "pipeline_result",
        "manifest_name": job.manifest.name if job.manifest else None,
    }

    # Try to update the existing assistant message (created by the chat view)
    # rather than creating a duplicate.
    existing = ChatMessage.objects.filter(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        metadata__job_id=str(job.job_id),
    ).first()

    if existing:
        existing.content = summary
        existing.metadata = result_metadata
        existing.save(update_fields=["content", "metadata"])
        logger.info(
            "Job %s: updated existing ChatMessage in session %s",
            job.job_id,
            session_id,
        )
    else:
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.Role.ASSISTANT,
            content=summary,
            metadata=result_metadata,
        )
        logger.info(
            "Job %s: final ChatMessage created in session %s",
            job.job_id,
            session_id,
        )

    # Update last_activity so the session stays at the top of the list
    session.last_activity = timezone.now()
    session.save(update_fields=["last_activity"])

    # Invalidate cached session list so sidebar picks up changes
    if session.tenant_id:
        try:
            cache.delete(
                f"chat:sessions:{session.tenant_id}:page=:page_size=:ordering="
            )
        except Exception:
            pass


def _build_result_summary(job):
    """Build a concise text summary from the pipeline result_data."""
    result = job.result_data or {}

    # If the orchestrator provides a ready-made summary, use it
    if "final_response" in result:
        return result["final_response"]

    # Check for social promotion results
    node_results = result.get("node_results", {})
    social_output = node_results.get("social_promoter", {})
    blog_output = node_results.get("blog_author", {})

    if social_output or blog_output:
        return _build_content_social_summary(blog_output, social_output)

    apa_output = node_results.get("audience_persona", {})
    if apa_output and (apa_output.get("personas") or apa_output.get("journey_maps")):
        return _build_audience_persona_summary(apa_output)

    cia_output = node_results.get("competitor_intelligence", {})
    if cia_output and (
        cia_output.get("competitors_analyzed")
        or cia_output.get("competitors")
        or cia_output.get("competitor_matrix")
    ):
        return _build_competitive_intelligence_summary(cia_output)

    tcia_output = node_results.get("trend_cultural", {})
    if not tcia_output:
        # Also check top-level fields promoted by ManagerNode
        if result.get("scored_trends") or result.get("trend_report"):
            tcia_output = result
    if tcia_output and (
        tcia_output.get("scored_trends") or tcia_output.get("trend_report")
    ):
        return _build_trend_cultural_summary(tcia_output)

    voca_output = node_results.get("voice_of_customer", {})
    if not voca_output:
        if result.get("voc_health_score") is not None or result.get("sentiment"):
            voca_output = result
    if voca_output and (
        voca_output.get("voc_health_score") is not None
        or voca_output.get("sentiment")
        or voca_output.get("themes")
    ):
        return _build_voice_of_customer_summary(voca_output)

    gap_output = node_results.get("gap_analyzer", {})
    if gap_output and gap_output.get("analysis_type") == "competitive_gap":
        return _build_gap_analysis_summary(gap_output)

    baa_output = node_results.get("brand_architecture", {})
    if not baa_output:
        if result.get("recommendation") and result.get("hierarchy"):
            baa_output = result
    if baa_output and (
        baa_output.get("recommendation", {}).get("recommended_model")
        or baa_output.get("hierarchy", {}).get("root")
    ):
        return _build_brand_architecture_summary(baa_output)

    if "summary" in result:
        return result["summary"]

    # Fallback: generic completion notice
    manifest_name = job.manifest.name if job.manifest else "Pipeline"
    return (
        f"{manifest_name} analysis completed successfully. "
        "View the full results in the pipeline card above."
    )


def _build_content_social_summary(blog_output, social_output):
    """Build a rich summary for blog authoring + social promotion pipelines."""
    parts = []

    # Blog section
    blog_content = blog_output.get("blog_content", "")
    if blog_content:
        # Extract title from first H1 line
        title = ""
        for line in blog_content.split("\n"):
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
                break
        if title:
            parts.append(f"**Blog authored:** {title}")
        word_count = blog_output.get("word_count", 0)
        if word_count:
            parts.append(f"Word count: {word_count}")
        gcs_uri = blog_output.get("gcs_uri", "")
        if gcs_uri:
            parts.append(f"Saved to: `{gcs_uri}`")
        parts.append("")  # blank line

    # Social section
    adapted_posts = social_output.get("adapted_posts", [])
    publish_results = social_output.get("publish_results", [])
    platforms_posted = social_output.get("platforms_posted", [])
    draft_stored = social_output.get("draft_stored", False)

    if adapted_posts:
        parts.append(
            f"**Social content adapted** for " f"{len(adapted_posts)} platform(s)."
        )

    if platforms_posted:
        parts.append(f"**Published to:** {', '.join(platforms_posted)}")
        for pr in publish_results:
            if pr.get("status") == "published" and pr.get("post_url"):
                parts.append(f"- {pr['platform']}: {pr['post_url']}")

    # Scheduled posts
    scheduled = [pr for pr in publish_results if pr.get("status") == "scheduled"]
    if scheduled:
        names = ", ".join(pr.get("platform", "?") for pr in scheduled)
        sched_msg = f"**Scheduled on:** {names}"
        first_date = scheduled[0].get("scheduled_date")
        if first_date:
            sched_msg += f" for {first_date}"
        parts.append(sched_msg)

    if draft_stored and not platforms_posted and not scheduled:
        parts.append("**Drafts saved** for admin approval.")

    # Failed platforms
    failed = [pr for pr in publish_results if pr.get("status") == "failed"]
    if failed:
        names = ", ".join(pr.get("platform", "?") for pr in failed)
        parts.append(f"Failed on: {names}")

    if not parts:
        return "Content pipeline completed successfully."

    return "\n".join(parts)


def _build_competitive_intelligence_summary(cia_output):
    """Build a summary for Competitor Intelligence Agent results."""
    parts = ["**Competitive Intelligence Report completed.**"]

    # Competitor names — support both "competitors_analyzed" (list of names)
    # and "competitors" (list of profile dicts)
    competitor_names = cia_output.get("competitors_analyzed", [])
    if not competitor_names:
        raw_competitors = cia_output.get("competitors", [])
        competitor_names = [
            c.get("name", "") for c in raw_competitors if isinstance(c, dict)
        ]
        competitor_names = [n for n in competitor_names if n]

    if competitor_names:
        parts.append(
            f"Analyzed {len(competitor_names)} competitor(s): "
            f"{', '.join(competitor_names[:5])}"
        )
        if len(competitor_names) > 5:
            parts.append(f"  ...and {len(competitor_names) - 5} more")

    executive_summary = cia_output.get("executive_summary", "")
    if executive_summary:
        parts.append("")
        parts.append(executive_summary[:500])

    # Competitor Matrix
    matrix = cia_output.get("competitor_matrix", {})
    if matrix and isinstance(matrix, dict):
        parts.append("")
        parts.append("**Competitor Matrix:**")
        for dimension, scores in list(matrix.items())[:5]:
            if isinstance(scores, dict):
                score_strs = [
                    f"{comp}: {score}" for comp, score in list(scores.items())[:5]
                ]
                parts.append(f"- {dimension}: {', '.join(score_strs)}")

    # SWOT Analyses
    swot_analyses = cia_output.get("swot_analyses", [])
    if swot_analyses:
        parts.append("")
        parts.append("**SWOT Analyses:**")
        for sw in swot_analyses[:3]:
            if not isinstance(sw, dict):
                continue
            name = sw.get("competitor", "Unknown")
            strengths = sw.get("strengths", [])
            weaknesses = sw.get("weaknesses", [])
            parts.append(f"\n*{name}*")
            if strengths:
                parts.append(f"  Strengths: {', '.join(str(s) for s in strengths[:3])}")
            if weaknesses:
                parts.append(
                    f"  Weaknesses: {', '.join(str(w) for w in weaknesses[:3])}"
                )
        if len(swot_analyses) > 3:
            parts.append(f"  ...and {len(swot_analyses) - 3} more")

    # Positioning Gaps
    positioning_gaps = cia_output.get("positioning_gaps", [])
    if positioning_gaps:
        parts.append("")
        parts.append("**Positioning Gaps:**")
        for gap in positioning_gaps[:5]:
            if not isinstance(gap, dict):
                continue
            dim = gap.get("dimension", "")
            desc = gap.get("gap_description", "")
            score = gap.get("opportunity_score", "")
            line = f"- {dim}"
            if desc:
                line += f": {desc[:100]}"
            if score:
                line += f" (opportunity: {score}/10)"
            parts.append(line)

    # Benchmarking Report
    benchmarking = cia_output.get("benchmarking_report", {})
    if benchmarking and isinstance(benchmarking, dict):
        bench_summary = benchmarking.get("summary", "")
        rankings = benchmarking.get("rankings", [])
        if bench_summary:
            parts.append("")
            parts.append("**Benchmarking:**")
            parts.append(bench_summary[:300])
        if rankings:
            parts.append("")
            for r in rankings[:5]:
                if isinstance(r, dict):
                    name = r.get("competitor", "")
                    score = r.get("overall_score", "")
                    tier = r.get("tier", "")
                    parts.append(f"- {name}: {score}/100 ({tier})")

    # Key Findings
    findings = cia_output.get("findings", [])
    if findings:
        parts.append("")
        parts.append("**Key findings:**")
        for f in findings[:5]:
            if isinstance(f, str):
                parts.append(f"- {f}")

    # Recommendations
    recommendations = cia_output.get("recommendations", [])
    if recommendations:
        parts.append("")
        parts.append("**Recommendations:**")
        for r in recommendations[:3]:
            if isinstance(r, str):
                parts.append(f"- {r}")

    confidence = cia_output.get("confidence_score", 0)
    if confidence:
        if isinstance(confidence, (int, float)):
            if confidence > 10:
                confidence = confidence / 100
            elif confidence > 1:
                confidence = confidence / 10
        parts.append(f"\nConfidence: {confidence:.0%}")

    parts.append("\nView the full results in the pipeline card above.")
    return "\n".join(parts)


def _build_audience_persona_summary(apa_output):
    """Build a summary for Audience Persona Agent results."""
    parts = ["**Audience Persona Research completed.**"]

    personas = apa_output.get("personas", [])
    if personas:
        parts.append(f"Generated {len(personas)} buyer persona(s):")
        for p in personas[:5]:
            if not isinstance(p, dict):
                continue
            label = p.get("segment_label", p.get("slug", "Unknown"))
            confidence = p.get("confidence_score", 0)
            # Normalize per-persona confidence to 0-1 range
            if isinstance(confidence, (int, float)):
                if confidence > 10:
                    confidence = confidence / 100
                elif confidence > 1:
                    confidence = confidence / 10
            data_source = p.get("data_source", "")
            source_tag = f" [{data_source}]" if data_source else ""
            parts.append(f"- **{label}**{source_tag} (confidence: {confidence:.0%})")
        if len(personas) > 5:
            parts.append(f"  ...and {len(personas) - 5} more")

    executive_summary = apa_output.get("executive_summary", "")
    if executive_summary:
        parts.append("")
        parts.append(executive_summary[:500])

    # Journey Maps
    journey_maps = apa_output.get("journey_maps", [])
    if journey_maps:
        parts.append("")
        parts.append(f"**Buying Journey Maps:** {len(journey_maps)} mapped")
        for jm in journey_maps[:3]:
            if not isinstance(jm, dict):
                continue
            slug = jm.get("persona_slug", "Unknown")
            stages = jm.get("stages", [])
            cycle = jm.get("total_estimated_cycle_days", 0)
            parts.append(
                f"- {slug}: {len(stages)} stages"
                + (f", ~{cycle} days" if cycle else "")
            )

    # Segment Matrix
    segment_matrix = apa_output.get("segment_matrix", {})
    if segment_matrix and isinstance(segment_matrix, dict):
        parts.append("")
        parts.append("**Segment Matrix:**")
        for dimension, values in list(segment_matrix.items())[:5]:
            if isinstance(values, dict):
                score_strs = [f"{seg}: {val}" for seg, val in list(values.items())[:4]]
                parts.append(f"- {dimension}: {', '.join(score_strs)}")

    # Key Findings
    findings = apa_output.get("findings", [])
    if findings:
        parts.append("")
        parts.append("**Key findings:**")
        for f in findings[:5]:
            if isinstance(f, str):
                parts.append(f"- {f}")

    # Recommendations
    recommendations = apa_output.get("recommendations", [])
    if recommendations:
        parts.append("")
        parts.append("**Recommendations:**")
        for r in recommendations[:3]:
            if isinstance(r, str):
                parts.append(f"- {r}")

    confidence = apa_output.get("confidence_score", 0)
    if confidence:
        # Normalize: if > 1 treat as already a percentage
        if isinstance(confidence, (int, float)):
            if confidence > 10:
                confidence = confidence / 100
            elif confidence > 1:
                confidence = confidence / 10
        parts.append(f"\nConfidence: {confidence:.0%}")

    parts.append("\nView the full results in the pipeline card above.")
    return "\n".join(parts)


def _build_trend_cultural_summary(tcia_output):
    """Build a summary for Trend & Cultural Insights Agent results."""
    parts = ["**Trend & Cultural Insights Report completed.**"]

    # Executive summary from trend_report
    report = tcia_output.get("trend_report", {})
    if isinstance(report, dict):
        exec_summary = report.get("executive_summary", "")
        if exec_summary:
            parts.append("")
            parts.append(exec_summary[:500])

    # Top scored trends
    scored = tcia_output.get("scored_trends", [])
    if scored:
        parts.append("")
        parts.append(f"**Scored {len(scored)} trend(s):**")
        for t in scored[:5]:
            if not isinstance(t, dict):
                continue
            topic = t.get("topic", t.get("trend_slug", "Unknown"))
            score = t.get("relevance_score", 0)
            rec = t.get("recommendation", "")
            line = f"- **{topic}**: {score}/100"
            if rec:
                line += f" ({rec})"
            parts.append(line)
        if len(scored) > 5:
            parts.append(f"  ...and {len(scored) - 5} more")

    # Opportunity alerts
    alerts = tcia_output.get("opportunity_alerts", [])
    if alerts:
        parts.append("")
        parts.append(f"**{len(alerts)} opportunity alert(s):**")
        for a in alerts[:3]:
            if not isinstance(a, dict):
                continue
            trend = a.get("trend_slug", "")
            urgency = a.get("urgency", "")
            rec = a.get("recommendation", "")
            line = f"- {trend}"
            if urgency:
                line += f" [{urgency}]"
            if rec:
                line += f": {rec[:100]}"
            parts.append(line)

    # New / Rising / Fading trends from report
    if isinstance(report, dict):
        new_trends = report.get("new_trends", [])
        rising = report.get("rising_trends", [])
        fading = report.get("fading_trends", [])
        if new_trends:
            parts.append(
                f"\n**New trends:** {', '.join(str(t) for t in new_trends[:5])}"
            )
        if rising:
            parts.append(f"**Rising:** {', '.join(str(t) for t in rising[:5])}")
        if fading:
            parts.append(f"**Fading:** {', '.join(str(t) for t in fading[:5])}")

        # Strategic recommendations
        recs = report.get("strategic_recommendations", [])
        if recs:
            parts.append("")
            parts.append("**Recommendations:**")
            for r in recs[:3]:
                if isinstance(r, str):
                    parts.append(f"- {r}")

    confidence = tcia_output.get("confidence_score", 0)
    if confidence:
        if isinstance(confidence, (int, float)):
            if confidence > 10:
                confidence = confidence / 100
            elif confidence > 1:
                confidence = confidence / 10
        parts.append(f"\nConfidence: {confidence:.0%}")

    parts.append("\nView the full results in the pipeline card above.")
    return "\n".join(parts)


def _build_voice_of_customer_summary(voca_output):
    """Build a summary for Voice of Customer Agent results."""
    parts = ["**Voice of Customer Analysis completed.**"]

    # VoC Health Score + operating mode
    health_score = voca_output.get("voc_health_score", 0)
    operating_mode = voca_output.get("operating_mode", "")
    if health_score:
        mode_tag = f" ({operating_mode})" if operating_mode else ""
        parts.append(f"VoC Health Score: **{health_score}/100**{mode_tag}")

    # Strategy bridge executive summary
    strategy_bridge = voca_output.get("strategy_bridge", {})
    if isinstance(strategy_bridge, dict):
        exec_summary = strategy_bridge.get("executive_summary", "")
        if exec_summary:
            parts.append("")
            parts.append(exec_summary[:500])

    # Sentiment summary
    sentiment = voca_output.get("sentiment", {})
    if isinstance(sentiment, dict):
        overall = sentiment.get("overall_sentiment", {})
        if isinstance(overall, dict) and any(overall.values()):
            pos = overall.get("positive", 0)
            neu = overall.get("neutral", 0)
            neg = overall.get("negative", 0)
            parts.append("")
            parts.append(
                f"**Sentiment:** {pos:.0%} positive, "
                f"{neu:.0%} neutral, {neg:.0%} negative"
            )

        channels = sentiment.get("channel_sentiments", [])
        if channels:
            parts.append(f"Analyzed {len(channels)} feedback channel(s)")

    # Theme clusters
    themes = voca_output.get("themes", {})
    if isinstance(themes, dict):
        clusters = themes.get("themes", [])
        total_feedback = themes.get("total_feedback_analyzed", 0)
        if clusters:
            parts.append("")
            parts.append(
                f"**Theme Clusters:** {len(clusters)} identified"
                + (f" ({total_feedback} feedback items)" if total_feedback else "")
            )
            for t in clusters[:5]:
                if not isinstance(t, dict):
                    continue
                name = t.get("theme_name", t.get("theme_slug", "Unknown"))
                count = t.get("feedback_count", 0)
                severity = t.get("severity_score", 0)
                line = f"- **{name}**: {count} mentions"
                if severity:
                    line += f" (severity: {severity:.1f}/10)"
                parts.append(line)
            if len(clusters) > 5:
                parts.append(f"  ...and {len(clusters) - 5} more")

    # NPS Analysis
    nps = voca_output.get("nps_analysis", {})
    if isinstance(nps, dict):
        if nps.get("nps_available"):
            current = nps.get("current_nps", {})
            if isinstance(current, dict):
                score = current.get("nps_score", 0)
                parts.append("")
                parts.append(f"**NPS Score:** {score:+.0f}")
                promoters = current.get("promoters", 0)
                passives = current.get("passives", 0)
                detractors = current.get("detractors", 0)
                parts.append(
                    f"  Promoters: {promoters} | "
                    f"Passives: {passives} | "
                    f"Detractors: {detractors}"
                )
        else:
            proxy = nps.get("proxy_nps", {})
            if isinstance(proxy, dict) and proxy.get("nps_score") is not None:
                parts.append("")
                parts.append(
                    f"**Proxy NPS:** {proxy['nps_score']:+.0f} "
                    "(estimated from external feedback)"
                )

    # Pain points
    pain_matrix = voca_output.get("pain_point_priority_matrix", {})
    if isinstance(pain_matrix, dict):
        pain_points = pain_matrix.get("pain_points", [])
        if pain_points:
            parts.append("")
            parts.append(f"**Pain Points:** {len(pain_points)} identified")
            for pp in pain_points[:5]:
                if not isinstance(pp, dict):
                    continue
                name = pp.get("name", "Unknown")
                severity = pp.get("severity", 0)
                frequency = pp.get("frequency", 0)
                line = f"- {name} (severity: {severity:.1f}/10"
                if frequency:
                    line += f", {frequency} mentions"
                line += ")"
                parts.append(line)
            if len(pain_points) > 5:
                parts.append(f"  ...and {len(pain_points) - 5} more")

    # Key Findings
    findings = voca_output.get("findings", [])
    if findings:
        parts.append("")
        parts.append("**Key findings:**")
        for f in findings[:5]:
            if isinstance(f, str):
                parts.append(f"- {f}")

    # Recommendations
    recommendations = voca_output.get("recommendations", [])
    if recommendations:
        parts.append("")
        parts.append("**Recommendations:**")
        for r in recommendations[:3]:
            if isinstance(r, str):
                parts.append(f"- {r}")

    confidence = voca_output.get("confidence_score", 0)
    if confidence:
        if isinstance(confidence, (int, float)):
            if confidence > 10:
                confidence = confidence / 100
            elif confidence > 1:
                confidence = confidence / 10
        parts.append(f"\nConfidence: {confidence:.0%}")

    parts.append("\nView the full results in the pipeline card above.")
    return "\n".join(parts)


def _update_workflow_snapshot(job):
    """Update WorkflowSnapshot summary and dashboard_data on job completion."""
    try:
        from workspace.models import WorkflowSnapshot
        from workspace.services import WorkflowService

        snapshot = WorkflowSnapshot.objects.filter(job=job).first()
        if not snapshot:
            return

        dashboard_data = WorkflowService.extract_dashboard_data(job.result_data)
        snapshot.dashboard_data = dashboard_data
        snapshot.summary = {
            "final_response": (job.result_data or {}).get("final_response", "")
        }
        snapshot.save(update_fields=["dashboard_data", "summary"])
        logger.info("Workflow snapshot updated for job %s", job.job_id)
    except Exception as exc:
        logger.warning(
            "Failed to update workflow snapshot for job %s: %s",
            job.job_id,
            exc,
        )


def _build_gap_analysis_summary(gap_output):
    """Build a summary for competitive gap analysis results."""
    gap_data = gap_output.get("gap_analysis", {})
    strengths = len(gap_data.get("strengths", []))
    gaps = len(gap_data.get("gaps", []))
    opps = len(gap_data.get("market_opportunities", []))

    parts = ["**Competitor Audit completed.**"]
    if strengths or gaps:
        parts.append(
            f"Identified {strengths} competitive "
            f"strength(s) and {gaps} market gap(s)."
        )
    if opps:
        parts.append(f"{opps} market opportunity(ies) recommended.")

    findings = gap_output.get("findings", [])
    if findings:
        parts.append("")
        for f in findings[:3]:
            parts.append(f"- {f}")

    parts.append("\nView the full results in the pipeline card above.")
    return "\n".join(parts)


def _build_brand_architecture_summary(baa_output):
    """Build a rich summary for brand architecture pipelines."""
    parts = []

    rec = baa_output.get("recommendation", {})
    model = rec.get("recommended_model", "")
    confidence = baa_output.get("confidence_score", 0)
    hierarchy = baa_output.get("hierarchy", {})
    root = hierarchy.get("root", {})
    depth = hierarchy.get("total_depth", 0)
    total_nodes = hierarchy.get("total_nodes", 0)
    naming = baa_output.get("naming_hierarchy", {})

    if model:
        model_label = model.replace("_", " ").title()
        parts.append("**Brand Architecture Strategy Generated**")
        parts.append(
            f"Recommended model: **{model_label}** " f"(confidence: {confidence:.0%})"
        )

    if root.get("name"):
        parts.append(f"\n**Brand Hierarchy**: {root['name']}")
        children = root.get("children", [])
        if children:
            parts.append(f"{total_nodes} brand entities across {depth} levels:")
            for child in children[:6]:
                child_name = child.get("name", "")
                child_type = (child.get("type", "") or "").replace("_", " ")
                if child_name:
                    parts.append(f"  - {child_name} ({child_type})")

    naming_pattern = naming.get("naming_pattern", "")
    if naming_pattern:
        consistency = naming.get("consistency_score", 0)
        parts.append(
            f"\n**Naming Convention**: {naming_pattern} "
            f"(consistency: {consistency}/100)"
        )

    scores = rec.get("model_scores", [])
    if scores:
        top = sorted(scores, key=lambda s: s.get("total", 0), reverse=True)
        parts.append("\n**Model Comparison**:")
        for s in top[:3]:
            m = (s.get("model", "") or "").replace("_", " ").title()
            parts.append(f"  - {m}: {s.get('total', 0)}/100")

    findings = baa_output.get("findings", [])
    if findings:
        parts.append("\n**Key Findings**:")
        for f in findings[:4]:
            if isinstance(f, str) and f.strip():
                parts.append(f"- {f}")

    parts.append("\nView the full results in the pipeline card above.")
    return "\n".join(parts)
