---
name: social-media-integration
description: Add or debug social media platform integrations (OAuth, posting, analytics)
triggers:
  - "add social platform"
  - "OAuth callback failing"
  - "posting not working"
  - "analytics not loading"
  - "token expired"
  - "social profile disconnected"
---

# Skill: Social Media Integration

## When to Use

Use this skill when the user needs to add a new social platform, debug OAuth flows, fix posting issues, or resolve analytics loading problems.

## Platform Architecture

Each platform follows the same pattern in `automation/`:

```
automation/
├── models.py          → SocialProfile (encrypted tokens), ContentCalendar
├── views.py           → Connect/callback/disconnect/post/analytics endpoints
├── serializers.py     → Platform-specific serialization
└── tests/             → 149+ tests covering all platforms
```

### Supported Platforms

| Platform | OAuth | Posting | Analytics | Model Field |
|----------|-------|---------|-----------|-------------|
| LinkedIn | ✅ | ✅ | ✅ | `platform="linkedin"` |
| Twitter/X | ✅ | ✅ | ✅ | `platform="twitter"` |
| Facebook | ✅ | ✅ | ✅ | `platform="facebook"` |
| Instagram | ✅ | ✅ | ✅ | `platform="instagram"` |
| Google Business | ✅ | ✅ | ✅ | `platform="google_business"` |

## OAuth Flow

```
1. Frontend: GET /api/v1/automation/{platform}/connect/
2. Backend: Generate OAuth URL with state parameter
3. Redirect: User approves on platform's OAuth page
4. Callback: Platform redirects to /api/v1/automation/{platform}/callback/
5. Backend: Exchange auth code for tokens
6. Encryption: Tokens encrypted with Fernet (via SECRET_KEY)
7. Storage: SocialProfile created with encrypted tokens
```

## Token Encryption

```python
# automation/encryption.py
from cryptography.fernet import Fernet

# Tokens stored in _access_token, _refresh_token columns
# Exposed via @property that calls decrypt_token()
# encrypt_token() / decrypt_token() use Fernet derived from SECRET_KEY via SHA-256

# ⚠️ CRITICAL: If SECRET_KEY changes, all encrypted tokens become invalid
# Users must reconnect their social accounts after a SECRET_KEY rotation
```

## Common Issues

### "Token decryption failed"

**Cause**: `SECRET_KEY` changed between when tokens were encrypted and now.
**Fix**: Users must reconnect their social accounts (disconnect + reconnect flow).

### "Failed to load analytics"

**Cause**: Multiple possible — JWT refresh URL mismatch, silent error swallowing, or token decryption.
**Debug Checklist**:
1. Check browser console for 401 errors
2. Verify JWT refresh URL matches in `api.ts` and backend `urls.py`
3. Check if social profile tokens can be decrypted
4. Verify platform API credentials haven't expired

### "Posting fails silently"

**Cause**: Platform API error not surfaced to user.
**Debug**:
```python
# Check content calendar entry status
from automation.models import ContentCalendar
entry = ContentCalendar.objects.get(id=<id>)
print(entry.status, entry.error_message)
```

### "OAuth callback returns error"

**Cause**: Redirect URI mismatch or expired auth code.
**Fix**: Verify `OAUTH_REDIRECT_URI` matches exactly what's registered with the platform.

## Adding a New Platform

1. **Models**: Add platform choice to `SocialProfile.PLATFORM_CHOICES`
2. **Views**: Create `{Platform}ConnectView`, `{Platform}CallbackView`, `{Platform}PostView`
3. **Serializers**: Add platform-specific fields if needed
4. **URLs**: Register new endpoints under `/api/v1/automation/`
5. **Tests**: Add test class following existing platform test patterns
6. **MCP Server**: Register new tools in `automation/mcp_server.py`
7. **Frontend**: Add platform card in social connections page
