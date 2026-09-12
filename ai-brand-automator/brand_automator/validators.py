"""
Input validation and sanitization utilities
Prevents injection attacks and ensures data integrity
"""

import html
import re
import bleach
from typing import Any, Dict, List
import logging


# ── Canonical allowed MIME types and extensions for file uploads ──
# Single source of truth — used by serializer, view, and validator.
# NOTE: image/svg+xml is NOT included because SVG can embed scripts.
# SVG uploads require dedicated sanitization before being allowed.

ALLOWED_IMAGE_TYPES = [
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "image/heic",
    "image/heif",
]

ALLOWED_VIDEO_TYPES = [
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
]

ALLOWED_DOCUMENT_TYPES = [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
]

ALLOWED_UPLOAD_TYPES = (
    ALLOWED_IMAGE_TYPES + ALLOWED_VIDEO_TYPES + ALLOWED_DOCUMENT_TYPES
)

EXPECTED_EXTENSIONS = {
    "image/jpeg": ["jpg", "jpeg", "jfif"],
    "image/png": ["png"],
    "image/gif": ["gif"],
    "image/webp": ["webp"],
    "image/bmp": ["bmp"],
    "image/tiff": ["tif", "tiff"],
    "image/heic": ["heic"],
    "image/heif": ["heif"],
    "video/mp4": ["mp4"],
    "video/quicktime": ["mov"],
    "video/x-msvideo": ["avi"],
    "video/webm": ["webm"],
    "application/pdf": ["pdf"],
    "application/msword": ["doc"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ["docx"],
    "text/plain": ["txt"],
}

logger = logging.getLogger(__name__)


def sanitize_text_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitize text input to prevent XSS and injection attacks

    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    if not isinstance(text, str):
        return str(text)

    # Truncate to max length
    text = text[:max_length]

    # Remove dangerous HTML/script tags while preserving safe formatting
    allowed_tags = ["b", "i", "u", "em", "strong", "p", "br"]
    allowed_attributes = {}

    cleaned = bleach.clean(
        text, tags=allowed_tags, attributes=allowed_attributes, strip=True
    )

    return cleaned


def sanitize_plain_text(text: str, max_length: int = 200) -> str:
    """Sanitize a plain-text field (names, titles).

    Strips all HTML tags but does NOT entity-encode characters like & or <.
    Use this for fields rendered as React text content where HTML entities
    would display literally (e.g. ``&amp;`` instead of ``&``).
    """
    if not isinstance(text, str):
        text = str(text)

    text = text[:max_length]

    # Strip all HTML tags
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True)

    # bleach.clean entity-encodes &, <, > — undo that for plain-text fields
    return html.unescape(cleaned)


def sanitize_ai_prompt(prompt: str) -> str:
    """
    Sanitize AI prompts to prevent prompt injection attacks

    Removes attempts to:
    - Override system instructions
    - Inject malicious commands
    - Extract sensitive information
    """
    if not isinstance(prompt, str):
        prompt = str(prompt)

    # Patterns indicating prompt injection attempts
    injection_patterns = [
        r"ignore\s+(previous|above|prior)\s+instructions?",
        r"disregard\s+(previous|above|prior)\s+instructions?",
        r"system\s*:",
        r"admin\s*:",
        r"root\s*:",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"\[SYSTEM\]",
        r"\[ADMIN\]",
        r"forget\s+everything",
        r"new\s+instructions?",
        r"reveal\s+(your|the)\s+(prompt|instructions|system)",
    ]

    # Check for injection attempts
    for pattern in injection_patterns:
        if re.search(pattern, prompt, re.IGNORECASE):
            logger.warning(f"Potential prompt injection detected: {pattern}")
            # Remove the suspicious part
            prompt = re.sub(pattern, "", prompt, flags=re.IGNORECASE)

    # Limit prompt length
    max_prompt_length = 5000
    if len(prompt) > max_prompt_length:
        logger.info(
            f"Prompt truncated from {len(prompt)} to {max_prompt_length} characters"
        )
        prompt = prompt[:max_prompt_length]

    # Remove control characters
    prompt = "".join(char for char in prompt if ord(char) >= 32 or char in "\n\r\t")

    return prompt.strip()


def validate_file_upload(
    file, allowed_types: List[str], max_size_mb: int = 50
) -> Dict[str, Any]:
    """
    Validate uploaded file for security

    Args:
        file: Uploaded file object
        allowed_types: List of allowed MIME types
        max_size_mb: Maximum file size in MB

    Returns:
        Dict with validation result and error message
    """
    result = {"valid": True, "error": None}

    # Check file size
    max_size_bytes = max_size_mb * 1024 * 1024
    if file.size > max_size_bytes:
        result["valid"] = False
        result["error"] = f"File size exceeds {max_size_mb}MB limit"
        return result

    # Check file type — fall back to extension-based guess when browser
    # reports a generic content type (e.g. application/octet-stream)
    import mimetypes as _mimetypes

    file_type = file.content_type
    if file_type not in allowed_types and file_type in (
        "application/octet-stream",
        "application/x-unknown",
        "",
        None,
    ):
        guessed, _ = _mimetypes.guess_type(file.name)
        if guessed and guessed in allowed_types:
            file_type = guessed
    if file_type not in allowed_types:
        result["valid"] = False
        result["error"] = f"File type {file_type} not allowed"
        return result

    # Check file extension matches content type
    extension = file.name.split(".")[-1].lower() if "." in file.name else ""

    if file_type in EXPECTED_EXTENSIONS:
        if extension not in EXPECTED_EXTENSIONS[file_type]:
            result["valid"] = False
            result[
                "error"
            ] = f"File extension {extension} does not match content type {file_type}"
            return result

    # Check for suspicious file names
    suspicious_patterns = [
        r"\.\./",  # Path traversal
        r'[<>:"|?*]',  # Invalid characters
        r"^\.",  # Hidden files
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, file.name):
            result["valid"] = False
            result["error"] = "Suspicious file name detected"
            return result

    return result


def validate_password_strength(password: str) -> Dict[str, Any]:
    """
    Validate password strength

    Requirements:
    - At least 8 characters
    - Contains uppercase and lowercase
    - Contains at least one digit
    - Contains at least one special character
    """
    result = {"valid": True, "errors": []}

    if len(password) < 8:
        result["errors"].append("Password must be at least 8 characters long")

    if not re.search(r"[A-Z]", password):
        result["errors"].append("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        result["errors"].append("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        result["errors"].append("Password must contain at least one digit")

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        result["errors"].append("Password must contain at least one special character")

    # Check for common passwords
    common_passwords = [
        "password",
        "12345678",
        "qwerty",
        "abc123",
        "password123",
        "admin",
        "letmein",
        "welcome",
        "monkey",
        "1234567890",
    ]
    if password.lower() in common_passwords:
        result["errors"].append("Password is too common")

    result["valid"] = len(result["errors"]) == 0
    return result


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other attacks
    """
    # Remove path components
    filename = filename.split("/")[-1].split("\\")[-1]

    # Remove dangerous characters
    filename = re.sub(r'[<>:"|?*]', "", filename)

    # Remove leading dots
    filename = filename.lstrip(".")

    # Limit length
    max_length = 255
    if len(filename) > max_length:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = (
            name[: max_length - len(ext) - 1] + "." + ext if ext else name[:max_length]
        )

    return filename or "unnamed_file"
