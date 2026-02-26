"""Helper utilities for parsing pipeline context and GCS URIs."""

import re
from typing import Any

# Explicit MIME type map (Docker containers lack /etc/mime.types)
_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".xls": "application/vnd.ms-excel",
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
    ".xml": "application/xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".zip": "application/zip",
}

_GCS_URI_PATTERN = re.compile(r"gs://[a-zA-Z0-9._\-]+/\S+")


def extract_gcs_uris(data: Any) -> list[str]:
    """Recursively extract all GCS URIs (gs://...) from nested data structures.

    Walks dicts, lists, and strings to find any gs:// URIs.
    Returns deduplicated list in discovery order.
    """
    uris: list[str] = []
    seen: set[str] = set()

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            for match in _GCS_URI_PATTERN.findall(obj):
                if match not in seen:
                    uris.append(match)
                    seen.add(match)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)

    _walk(data)
    return uris


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    """Split a GCS URI into (bucket, object_path).

    Args:
        uri: A GCS URI like "gs://my-bucket/path/to/file.pdf"

    Returns:
        Tuple of (bucket_name, object_path)

    Raises:
        ValueError: If the URI does not start with gs://
    """
    if not uri.startswith("gs://"):
        raise ValueError(f"Not a GCS URI: {uri}")

    without_prefix = uri[5:]  # Remove "gs://"
    slash_idx = without_prefix.find("/")
    if slash_idx < 0:
        return (without_prefix, "")
    return (without_prefix[:slash_idx], without_prefix[slash_idx + 1 :])


def infer_mime_type(filename: str) -> str:
    """Infer MIME type from filename extension.

    Uses explicit MIME map (no /etc/mime.types dependency).
    Falls back to application/octet-stream for unknown extensions.
    """
    dot_idx = filename.rfind(".")
    if dot_idx < 0:
        return "application/octet-stream"

    ext = filename[dot_idx:].lower()
    return _MIME_MAP.get(ext, "application/octet-stream")
