#!/usr/bin/env python
"""Reset encrypted tokens to test tokens."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'brand_automator.settings')
django.setup()

from automation.models import GoogleBusinessProfile, SocialProfile

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
    if sp.access_token and (sp.access_token.startswith("enc:") or sp.access_token.startswith("TThYZ")):
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
