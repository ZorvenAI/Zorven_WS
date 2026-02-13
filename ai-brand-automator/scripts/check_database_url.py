"""
Diagnostic script for Railway deployment.
Runs before migrations to verify DATABASE_URL is readable and parseable.
"""

import os
import sys
import urllib.parse


def mask_url(url):
    """Return URL with password masked for safe logging."""
    if not url:
        return repr(url)
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.password:
            masked = url.replace(parsed.password, "***")
            return masked
        return url
    except Exception:
        # Show first 20 chars + length if unparseable
        safe = url[:20].replace("\n", "\\n").replace("\r", "\\r")
        return f"{safe}... (len={len(url)})"


def main():
    print("=" * 60)
    print("DATABASE_URL Diagnostic")
    print("=" * 60)

    # 1. Check os.environ directly
    raw = os.environ.get("DATABASE_URL")
    if raw is None:
        print("[os.environ] DATABASE_URL: NOT SET")
    elif not raw.strip():
        print(f"[os.environ] DATABASE_URL: SET but EMPTY (len={len(raw)})")
    else:
        print(f"[os.environ] DATABASE_URL: SET (len={len(raw)})")
        print(f"[os.environ] Masked URL: {mask_url(raw.strip())}")
        # Parse scheme
        parsed = urllib.parse.urlsplit(raw.strip())
        print(f"[os.environ] Scheme: {parsed.scheme!r}")
        print(f"[os.environ] Host: {parsed.hostname!r}")

    # 2. Check python-decouple
    try:
        from decouple import config

        value = config("DATABASE_URL", default="__NOT_SET__")
        if value == "__NOT_SET__":
            print("[decouple]   DATABASE_URL: NOT SET (got default)")
        elif not value.strip():
            print(f"[decouple]   DATABASE_URL: EMPTY (len={len(value)})")
        else:
            print(f"[decouple]   DATABASE_URL: SET (len={len(value)})")
            print(f"[decouple]   Masked URL: {mask_url(value.strip())}")
            parsed = urllib.parse.urlsplit(value.strip())
            print(f"[decouple]   Scheme: {parsed.scheme!r}")

        # Check if os.environ and decouple agree
        if raw is not None and value != "__NOT_SET__":
            if raw.strip() == value.strip():
                print("[match]      os.environ and decouple AGREE")
            else:
                print("[MISMATCH]   os.environ and decouple DISAGREE!")
                print(f"  os.environ len={len(raw)}, decouple len={len(value)}")
    except Exception as exc:
        print(f"[decouple]   ERROR: {exc!r}")

    # 3. Check for .env files that decouple might read
    print("\n[files]      .env files in /app/:")
    app_dir = "/app" if os.path.isdir("/app") else os.getcwd()
    for f in sorted(os.listdir(app_dir)):
        if f.startswith(".env"):
            fpath = os.path.join(app_dir, f)
            print(f"  {f} ({os.path.getsize(fpath)} bytes)")

    # 4. Test dj_database_url.parse
    url_to_parse = (raw or "").strip() if raw else ""
    if url_to_parse:
        try:
            import dj_database_url

            result = dj_database_url.parse(url_to_parse)
            print(f"\n[dj_db_url]  Parse OK: engine={result.get('ENGINE')}")
        except Exception as exc:
            print(f"\n[dj_db_url]  Parse FAILED: {exc}")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
