"""
Domain layer - Pure business logic with no external dependencies.

This module exports the core domain models, exceptions, and path generation utilities.
"""

from .models import (
    EventSource,
    FileType,
    ProcessingStatus,
    IngestionEvent,
    FileMetadata,
    ProcessedEvent,
)

from .exceptions import (
    DataIngestionError,
    DuplicateEventError,
    FileNotFoundInLandingError,
    StorageOperationError,
    CacheOperationError,
    EventPublishError,
    InvalidEventError,
    PathGenerationError,
    RetryableError,
    NonRetryableError,
)

from .path_generator import (
    parse_gcs_uri,
    extract_filename,
    sanitize_tenant_id,
    generate_raw_path,
    generate_raw_object_path,
    is_landing_zone_path,
    validate_destination_path,
)

__all__ = [
    # Models
    "EventSource",
    "FileType",
    "ProcessingStatus",
    "IngestionEvent",
    "FileMetadata",
    "ProcessedEvent",
    # Exceptions
    "DataIngestionError",
    "DuplicateEventError",
    "FileNotFoundInLandingError",
    "StorageOperationError",
    "CacheOperationError",
    "EventPublishError",
    "InvalidEventError",
    "PathGenerationError",
    "RetryableError",
    "NonRetryableError",
    # Path utilities
    "parse_gcs_uri",
    "extract_filename",
    "sanitize_tenant_id",
    "generate_raw_path",
    "generate_raw_object_path",
    "is_landing_zone_path",
    "validate_destination_path",
]
