"""SKL-CGA-05: Image Generator.

Orchestrates async image generation for all prompts from Claude call 1.
Calls image_gen_client for 3 aspect ratios per prompt, uploads to GCS,
tracks costs and failures. Generates thumbnails for callback responses.
"""

import asyncio
import base64
import io
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Standard Meta ad aspect ratios
ASPECT_RATIOS = ["1:1", "9:16", "16:9"]

# Max concurrent image generation requests
_DEFAULT_CONCURRENCY = 5


class ImageGenerator:
    """Orchestrate async image generation across all prompts."""

    async def generate_all(
        self,
        image_prompts: list[dict[str, Any]],
        image_gen_client: Any,
        gcs_client: Any,
        tenant_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        """Generate images for all prompts across 3 aspect ratios.

        For each prompt, generates images in 1:1, 9:16, and 16:9
        aspect ratios using the image_gen_client, then uploads each
        to GCS. Uses asyncio.Semaphore to limit concurrency.

        Args:
            image_prompts: List of image prompt dicts from Claude call 1.
                Each has: ad_set_name, variant_id, prompt_text,
                negative_prompt, style, mood, color_guidance.
            image_gen_client: Adapter with async generate() method.
            gcs_client: GCS client with async upload_image() method.
            tenant_id: Tenant identifier for GCS path.
            job_id: Job identifier for GCS path and tracking.

        Returns:
            Dict with generated_images list, total_images, total_cost_usd,
            and failed_count.
        """
        generated_images: list[dict[str, Any]] = []
        failed_count = 0
        total_cost = 0.0

        semaphore = asyncio.Semaphore(_DEFAULT_CONCURRENCY)

        # Build task list: one task per prompt x aspect_ratio
        tasks = []
        for prompt_spec in image_prompts:
            for aspect_ratio in ASPECT_RATIOS:
                tasks.append(
                    self._generate_single(
                        prompt_spec=prompt_spec,
                        aspect_ratio=aspect_ratio,
                        image_gen_client=image_gen_client,
                        gcs_client=gcs_client,
                        tenant_id=tenant_id,
                        job_id=job_id,
                        semaphore=semaphore,
                    )
                )

        logger.info(
            "Starting image generation: %d prompts x %d ratios = %d images",
            len(image_prompts),
            len(ASPECT_RATIOS),
            len(tasks),
        )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        failure_reasons: list[str] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "Image generation task failed: %s: %s",
                    type(result).__name__,
                    result,
                    exc_info=result,
                )
                failure_reasons.append(f"{type(result).__name__}: {result}")
                failed_count += 1
            elif result is None:
                failure_reasons.append("returned None (no image data)")
                failed_count += 1
            else:
                generated_images.append(result)
                total_cost += result.get("cost_usd", 0.0)

        logger.info(
            "Image generation complete: %d succeeded, %d failed, "
            "total cost $%.4f",
            len(generated_images),
            failed_count,
            total_cost,
        )

        return {
            "generated_images": generated_images,
            "total_images": len(generated_images),
            "total_cost_usd": round(total_cost, 4),
            "failed_count": failed_count,
            "failure_reasons": failure_reasons[:10],
        }

    async def _generate_single(
        self,
        prompt_spec: dict[str, Any],
        aspect_ratio: str,
        image_gen_client: Any,
        gcs_client: Any,
        tenant_id: str,
        job_id: str,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any] | None:
        """Generate a single image and upload to GCS.

        Args:
            prompt_spec: Image prompt specification from Claude.
            aspect_ratio: Target aspect ratio (1:1, 9:16, 16:9).
            image_gen_client: Image generation adapter.
            gcs_client: GCS upload client.
            tenant_id: Tenant ID.
            job_id: Job ID.
            semaphore: Concurrency limiter.

        Returns:
            Generated image metadata dict, or None on failure.
        """
        ad_set_name = prompt_spec.get("ad_set_name", "unknown")
        variant_id = prompt_spec.get("variant_id", "v1")
        prompt_text = prompt_spec.get("prompt_text", "")

        if not prompt_text:
            logger.warning(
                "Empty prompt for %s/%s, skipping", ad_set_name, variant_id
            )
            return None

        async with semaphore:
            start_ms = time.monotonic()
            try:
                # Build enriched prompt with negative prompt and style
                enriched_prompt = prompt_text
                negative = prompt_spec.get("negative_prompt", "")
                style = prompt_spec.get("style", "")
                if style:
                    enriched_prompt = f"[Style: {style}] {enriched_prompt}"
                if negative:
                    enriched_prompt += f" [Avoid: {negative}]"

                # Generate image via adapter (returns GeneratedImage dataclass)
                gen_result = await image_gen_client.generate(
                    prompt=enriched_prompt,
                    aspect_ratio=aspect_ratio,
                )

                generation_time_ms = int(
                    (time.monotonic() - start_ms) * 1000
                )

                if not gen_result or not gen_result.image_data:
                    logger.warning(
                        "No image data returned for %s/%s/%s",
                        ad_set_name,
                        variant_id,
                        aspect_ratio,
                    )
                    return None

                # Upload to GCS
                ratio_slug = aspect_ratio.replace(":", "x")
                filename = f"{ad_set_name}_{variant_id}_{ratio_slug}.png"
                gcs_url = await gcs_client.upload_image(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    image_data=gen_result.image_data,
                    filename=filename,
                    content_type="image/png",
                )

                # Generate thumbnail for callback response (~10-20KB)
                thumbnail_uri = _make_thumbnail(gen_result.image_data)

                cost = gen_result.cost_usd
                provider = gen_result.provider

                return {
                    "ad_set_name": ad_set_name,
                    "variant_id": variant_id,
                    "aspect_ratio": aspect_ratio,
                    "gcs_url": gcs_url or "",
                    "thumbnail_url": thumbnail_uri,
                    "prompt_used": prompt_text,
                    "provider": provider,
                    "cost_usd": cost,
                    "generation_time_ms": generation_time_ms,
                }

            except Exception as exc:
                generation_time_ms = int(
                    (time.monotonic() - start_ms) * 1000
                )
                logger.error(
                    "Image generation failed for %s/%s/%s after %dms: %s",
                    ad_set_name,
                    variant_id,
                    aspect_ratio,
                    generation_time_ms,
                    exc,
                )
                return None


def _make_thumbnail(image_data: bytes, max_size: int = 200) -> str:
    """Resize image to thumbnail and return as data URI (~10-20KB JPEG)."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_data))
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        if img.mode == "RGBA":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as exc:
        logger.warning("Thumbnail generation failed: %s", exc)
        return ""
