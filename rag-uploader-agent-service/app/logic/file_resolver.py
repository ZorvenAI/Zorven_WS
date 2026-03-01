"""Extracts file references from pipeline context."""

import logging
from dataclasses import dataclass
from typing import Any

from app.logic.context_parser import extract_gcs_uris, infer_mime_type, parse_gcs_uri

logger = logging.getLogger(__name__)

# Upstream nodes known to produce GCS files or content
_CONTENT_NODE_KEYS = ["blog_author", "content_agent"]


@dataclass
class ResolvedFile:
    """A file resolved from the pipeline context."""

    gcs_uri: str
    bucket: str
    path: str
    file_name: str
    file_type: str
    file_size_bytes: int
    source: str  # e.g., "attachment", "blog_author"
    raw_content: str = ""  # Non-empty when content needs GCS upload first
    needs_upload: bool = False  # True when raw_content must be uploaded to GCS


class FileResolver:
    """Extracts file GCS URIs from input_context and previous_outputs."""

    def resolve(
        self,
        input_context: dict[str, Any],
        previous_outputs: dict[str, Any],
        tenant_context: dict[str, Any],
    ) -> list[ResolvedFile]:
        """Resolve all file references from pipeline context.

        Strategy:
        1. Extract from input_context["attachments"]
        2. Extract blog_author GCS URI from previous_outputs
        3. Extract content payloads when upstream nodes have content but no real GCS URI
        4. Discover any other GCS URIs in previous_outputs
        5. Deduplicate by GCS URI
        """
        files: list[ResolvedFile] = []
        seen_uris: set[str] = set()

        logger.debug(
            "Resolving files — input_context keys: %s, previous_outputs keys: %s",
            list(input_context.keys()),
            list(previous_outputs.keys()),
        )

        # 1. Attachments from input_context
        attachments = input_context.get("attachments", [])
        for att in attachments:
            bucket = att.get("gcs_bucket", "")
            path = att.get("gcs_path", "")
            if not bucket or not path:
                continue
            gcs_uri = f"gs://{bucket}/{path}"
            if gcs_uri in seen_uris:
                continue
            seen_uris.add(gcs_uri)

            file_name = att.get("file_name", path.rsplit("/", 1)[-1])
            file_type = att.get("file_type", infer_mime_type(file_name))
            files.append(
                ResolvedFile(
                    gcs_uri=gcs_uri,
                    bucket=bucket,
                    path=path,
                    file_name=file_name,
                    file_type=file_type,
                    file_size_bytes=att.get("file_size_bytes", 0),
                    source="attachment",
                )
            )

        # 2. Blog author GCS URI (real gs:// URI)
        blog_output = previous_outputs.get("blog_author", {})
        if isinstance(blog_output, dict):
            blog_uri = blog_output.get("gcs_uri", "")
            if blog_uri and blog_uri.startswith("gs://") and blog_uri not in seen_uris:
                seen_uris.add(blog_uri)
                try:
                    bucket, path = parse_gcs_uri(blog_uri)
                    file_name = path.rsplit("/", 1)[-1] if "/" in path else path
                    # Compute file size from blog_content if available
                    blog_content = blog_output.get("blog_content", "")
                    file_size = (
                        len(blog_content.encode("utf-8")) if blog_content else 0
                    )
                    files.append(
                        ResolvedFile(
                            gcs_uri=blog_uri,
                            bucket=bucket,
                            path=path,
                            file_name=file_name,
                            file_type=infer_mime_type(file_name),
                            file_size_bytes=file_size,
                            source="blog_author",
                        )
                    )
                except ValueError:
                    logger.warning("Invalid GCS URI from blog_author: %s", blog_uri)

        # 3. Content payloads — when upstream nodes have content but no real GCS URI
        for node_key in _CONTENT_NODE_KEYS:
            node_output = previous_outputs.get(node_key, {})
            if not isinstance(node_output, dict):
                continue

            # Skip if we already resolved a real GCS file from this node
            if any(f.source == node_key and not f.needs_upload for f in files):
                continue

            blog_content = node_output.get("blog_content", "")
            if not blog_content:
                continue

            node_uri = node_output.get("gcs_uri", "")
            seo_meta = node_output.get("seo_meta", {})
            slug = seo_meta.get("slug", "") if isinstance(seo_meta, dict) else ""
            file_name = f"{slug}.md" if slug else "blog-content.md"

            if node_uri and node_uri.startswith("gs://"):
                # Already handled in step 2
                continue

            # Non-GCS URI (stub:// or empty) — content needs upload
            logger.info(
                "Node '%s' has blog_content (%d chars) but non-GCS URI '%s' — "
                "marking for content upload",
                node_key,
                len(blog_content),
                node_uri[:60] if node_uri else "(empty)",
            )
            files.append(
                ResolvedFile(
                    gcs_uri="",  # Will be populated after GCS upload
                    bucket="",
                    path="",
                    file_name=file_name,
                    file_type="text/markdown",
                    file_size_bytes=len(blog_content.encode("utf-8")),
                    source=node_key,
                    raw_content=blog_content,
                    needs_upload=True,
                )
            )

        # 4. Discover other GCS URIs in previous_outputs
        all_uris = extract_gcs_uris(previous_outputs)
        for uri in all_uris:
            if uri in seen_uris:
                continue
            seen_uris.add(uri)
            try:
                bucket, path = parse_gcs_uri(uri)
                file_name = path.rsplit("/", 1)[-1] if "/" in path else path
                source_key = self._find_source_key(previous_outputs, uri)
                files.append(
                    ResolvedFile(
                        gcs_uri=uri,
                        bucket=bucket,
                        path=path,
                        file_name=file_name,
                        file_type=infer_mime_type(file_name),
                        file_size_bytes=0,
                        source=source_key,
                    )
                )
            except ValueError:
                logger.warning("Invalid GCS URI discovered: %s", uri)

        logger.info(
            "Resolved %d file(s) from pipeline context (%d need GCS upload)",
            len(files),
            sum(1 for f in files if f.needs_upload),
        )
        return files

    @staticmethod
    def _find_source_key(outputs: dict[str, Any], uri: str) -> str:
        """Find the top-level output key that contains a GCS URI."""
        for key, value in outputs.items():
            uris = extract_gcs_uris(value)
            if uri in uris:
                return key
        return "unknown"
