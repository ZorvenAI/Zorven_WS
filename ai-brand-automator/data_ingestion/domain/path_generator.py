"""
Path Generator for Data Ingestion Pipeline.

Pure functions for transforming landing zone paths to structured raw storage paths.
No external dependencies - only standard library.
"""

import re
from datetime import datetime
from typing import Tuple
from urllib.parse import unquote

from .exceptions import PathGenerationError


def parse_gcs_uri(gcs_uri: str) -> Tuple[str, str]:
    """
    Parse a GCS URI into bucket and path components.

    Args:
        gcs_uri: Full GCS URI (e.g., 'gs://bucket-name/path/to/file.mp4')

    Returns:
        Tuple of (bucket_name, object_path)

    Raises:
        PathGenerationError: If URI is not a valid GCS URI
    """
    if not gcs_uri.startswith("gs://"):
        raise PathGenerationError(
            reason="Invalid GCS URI format - must start with 'gs://'",
            source_path=gcs_uri,
        )

    # Remove the gs:// prefix
    path_part = gcs_uri[5:]

    # Split on first slash to get bucket and path
    if "/" not in path_part:
        raise PathGenerationError(
            reason="Invalid GCS URI format - missing object path",
            source_path=gcs_uri,
        )

    bucket, object_path = path_part.split("/", 1)

    if not bucket:
        raise PathGenerationError(
            reason="Invalid GCS URI format - empty bucket name",
            source_path=gcs_uri,
        )

    if not object_path:
        raise PathGenerationError(
            reason="Invalid GCS URI format - empty object path",
            source_path=gcs_uri,
        )

    return bucket, object_path


def extract_filename(object_path: str) -> str:
    """
    Extract the filename from a GCS object path.

    Args:
        object_path: Path within bucket (e.g., '_landing/subdir/file.mp4')

    Returns:
        Filename (e.g., 'file.mp4')

    Raises:
        PathGenerationError: If filename cannot be extracted
    """
    # URL decode the path (handles %20, etc.)
    decoded_path = unquote(object_path)

    # Get the last component
    filename = decoded_path.rstrip("/").split("/")[-1]

    if not filename:
        raise PathGenerationError(
            reason="Could not extract filename from path",
            source_path=object_path,
        )

    # Validate filename doesn't contain path traversal
    if ".." in filename or filename.startswith("/"):
        raise PathGenerationError(
            reason="Invalid filename - contains path traversal characters",
            source_path=object_path,
        )

    return filename


def sanitize_tenant_id(tenant_id: str) -> str:
    """
    Sanitize tenant_id for use in file paths.

    Args:
        tenant_id: Raw tenant identifier

    Returns:
        Sanitized tenant_id safe for use in paths

    Raises:
        PathGenerationError: If tenant_id is invalid
    """
    if not tenant_id:
        raise PathGenerationError(
            reason="tenant_id cannot be empty",
            tenant_id=tenant_id,
        )

    # Normalize to lowercase
    sanitized = tenant_id.lower().strip()

    # Replace spaces with hyphens
    sanitized = sanitized.replace(" ", "-")

    # Remove any characters that aren't alphanumeric, hyphen, or underscore
    sanitized = re.sub(r"[^a-z0-9_-]", "", sanitized)

    if not sanitized:
        raise PathGenerationError(
            reason="tenant_id contains no valid characters after sanitization",
            tenant_id=tenant_id,
        )

    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:100]

    return sanitized


def generate_raw_path(
    tenant_id: str,
    source_path: str,
    timestamp: datetime,
    bucket: str | None = None,
) -> str:
    """
    Generate the destination raw storage path from a landing zone path.

    Transforms:
        gs://{bucket}/_landing/{filename}
    To:
        gs://{bucket}/{tenant_id}/raw/{YYYY}/{MM}/{DD}/{filename}

    Args:
        tenant_id: Tenant identifier (will be sanitized)
        source_path: Full GCS URI of source file in landing zone
        timestamp: Timestamp to use for date partitioning
        bucket: Optional bucket override (uses source bucket if not provided)

    Returns:
        Full GCS URI of destination path

    Raises:
        PathGenerationError: If path cannot be generated

    Examples:
        >>> generate_raw_path(
        ...     tenant_id="customer-1",
        ...     source_path="gs://onboarding-bucket1/_landing/video.mp4",
        ...     timestamp=datetime(2026, 1, 29, 10, 0, 0)
        ... )
        'gs://onboarding-bucket1/customer-1/raw/2026/01/29/video.mp4'
    """
    # Parse source URI
    source_bucket, object_path = parse_gcs_uri(source_path)

    # Use provided bucket or source bucket
    dest_bucket = bucket or source_bucket

    # Sanitize tenant ID
    safe_tenant_id = sanitize_tenant_id(tenant_id)

    # Extract filename
    filename = extract_filename(object_path)

    # Generate date components
    year = timestamp.strftime("%Y")
    month = timestamp.strftime("%m")
    day = timestamp.strftime("%d")

    # Build destination path
    dest_path = f"{safe_tenant_id}/raw/{year}/{month}/{day}/{filename}"

    # Return full URI
    return f"gs://{dest_bucket}/{dest_path}"


def generate_raw_object_path(
    tenant_id: str,
    filename: str,
    timestamp: datetime,
) -> str:
    """
    Generate just the object path (without gs://bucket/) for raw storage.

    Useful when working with bucket objects directly.

    Args:
        tenant_id: Tenant identifier (will be sanitized)
        filename: Filename to store
        timestamp: Timestamp for date partitioning

    Returns:
        Object path within bucket (e.g., 'customer-1/raw/2026/01/29/file.mp4')

    Raises:
        PathGenerationError: If path cannot be generated
    """
    # Sanitize tenant ID
    safe_tenant_id = sanitize_tenant_id(tenant_id)

    # Validate filename
    if not filename:
        raise PathGenerationError(
            reason="filename cannot be empty",
            tenant_id=tenant_id,
        )

    # Remove any directory components from filename
    safe_filename = filename.rstrip("/").split("/")[-1]

    if ".." in safe_filename:
        raise PathGenerationError(
            reason="filename contains path traversal characters",
            tenant_id=tenant_id,
        )

    # Generate date components
    year = timestamp.strftime("%Y")
    month = timestamp.strftime("%m")
    day = timestamp.strftime("%d")

    return f"{safe_tenant_id}/raw/{year}/{month}/{day}/{safe_filename}"


def is_landing_zone_path(object_path: str, landing_prefix: str = "_landing") -> bool:
    """
    Check if an object path is in the landing zone.

    Args:
        object_path: Path within bucket
        landing_prefix: Expected landing zone prefix

    Returns:
        True if path is in landing zone
    """
    # Normalize the path and prefix
    normalized_path = object_path.lstrip("/")
    normalized_prefix = landing_prefix.strip("/")

    return (
        normalized_path.startswith(f"{normalized_prefix}/") or normalized_path == normalized_prefix
    )


def validate_destination_path(dest_path: str, tenant_id: str) -> bool:
    """
    Validate that a destination path follows the expected format.

    Expected format: {tenant_id}/raw/{YYYY}/{MM}/{DD}/{filename}

    Args:
        dest_path: Object path to validate
        tenant_id: Expected tenant ID

    Returns:
        True if path is valid
    """
    pattern = rf"^{re.escape(tenant_id.lower())}/raw/\d{{4}}/\d{{2}}/\d{{2}}/[^/]+$"
    return bool(re.match(pattern, dest_path))
