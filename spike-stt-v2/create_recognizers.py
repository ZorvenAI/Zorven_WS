#!/usr/bin/env python3
"""One-time script to create STT v2 recognizer resources for the A-01 spike.

Usage:
    export OIA_SPIKE_PROJECT_ID=your-gcp-project-id
    python create_recognizers.py [--location us-central1]

Creates two recognizers:
  1. oia-spike-en-us  — fixed English, diarization enabled
  2. oia-spike-auto   — multi-language, diarization enabled
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from stt_client import STTConfig, create_recognizer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create STT v2 recognizer resources")
    parser.add_argument(
        "--location",
        default="us-central1",
        help="GCP location for recognizers (default: us-central1)",
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("OIA_SPIKE_PROJECT_ID", ""),
        help="GCP project ID (or set OIA_SPIKE_PROJECT_ID env var)",
    )
    parser.add_argument(
        "--credentials-json",
        default=os.environ.get("OIA_SPIKE_CREDENTIALS_JSON", ""),
        help="Service account JSON string (optional)",
    )
    args = parser.parse_args()

    if not args.project_id:
        logger.error(
            "Project ID required. Set OIA_SPIKE_PROJECT_ID or pass --project-id"
        )
        sys.exit(1)

    config = STTConfig(
        project_id=args.project_id,
        location=args.location,
        credentials_json=args.credentials_json,
    )

    # 1. Fixed English recognizer
    logger.info("Creating fixed-language recognizer (en-US)...")
    name_en = create_recognizer(
        config=config,
        recognizer_id="oia-spike-en-us",
        language_codes=["en-US"],
        enable_diarization=True,
    )
    logger.info("  -> %s", name_en)

    # 2. Multi-language recognizer
    logger.info("Creating multi-language recognizer...")
    name_auto = create_recognizer(
        config=config,
        recognizer_id="oia-spike-auto",
        language_codes=["en-US", "es-US", "fr-FR", "de-DE"],
        enable_diarization=True,
    )
    logger.info("  -> %s", name_auto)

    print()
    print("=" * 60)
    print("Recognizers ready. Use these in the spike relay:")
    print(f"  Fixed:  ?recognizer=oia-spike-en-us")
    print(f"  Auto:   ?recognizer=oia-spike-auto")
    print("=" * 60)


if __name__ == "__main__":
    main()
