#!/usr/bin/env python
"""
Reset encrypted tokens to test tokens.

WARNING: This script is for development/testing only!
It will replace OAuth tokens with non-functional test values.
"""

import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

from django.conf import settings  # noqa: E402
from automation.models import GoogleBusinessProfile, SocialProfile  # noqa: E402


def main():
    # SAFETY: Require DEBUG=True to prevent accidental production runs
    if not settings.DEBUG:
        print("ERROR: This script can only run when DEBUG=True")
        print("This prevents accidental token reset in production.")
        sys.exit(1)

    # Require explicit confirmation
    print("WARNING: This will reset OAuth tokens to non-functional test values.")
    print("This should ONLY be run in development environments.")
    confirm = input("Type 'yes' to continue: ")
    if confirm.lower() != "yes":
        print("Aborted.")
        sys.exit(0)

    # Reset GBP ID 2 to mock token
    gbp2 = GoogleBusinessProfile.objects.filter(id=2).first()
    if gbp2:
        gbp2.access_token = "gbp_mock_access_token_12345"
        gbp2.refresh_token = "gbp_mock_refresh_token_12345"
        gbp2.save()
        print("Reset GBP ID 2 to mock tokens")

    # Reset all profiles with encrypted tokens
    for sp in SocialProfile.objects.all():
        needs_reset = False
        if sp.access_token and (
            sp.access_token.startswith("enc:") or sp.access_token.startswith("TThYZ")
        ):
            needs_reset = True

        if needs_reset:
            if sp.platform == "linkedin":
                sp.access_token = "test_access_token_not_real"
                sp.refresh_token = "test_refresh_token_not_real"
            elif sp.platform == "twitter":
                sp.access_token = "test_twitter_access_token_not_real"
                sp.access_token_secret = "test_secret"
            elif sp.platform == "facebook":
                sp.access_token = "test_facebook_access_token_not_real"
                sp.page_access_token = "test_facebook_page_token_not_real"
            elif sp.platform == "instagram":
                sp.access_token = "test_instagram_access_token_not_real"
                sp.instagram_access_token = "test_instagram_user_token_not_real"
            sp.save()
            print(f"Reset {sp.platform} profile ID {sp.id}")

    print("Done!")


if __name__ == "__main__":
    main()
