"""
Diagnostic script for deployment.
Runs before migrations to verify DATABASE_URL is readable and parseable.
"""

import os
import sys
import urllib.parse


def safe_summary(url):
    """Return only scheme + length for safe logging (no credentials or host)."""
    if not url:
        return "empty"
    try:
        parsed = urllib.parse.urlsplit(url)
        return f"scheme={parsed.scheme!r}, len={len(url)}"
    except Exception:
        return f"unparseable, len={len(url)}"


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
        # Show raw bytes to detect invisible characters
        if raw:
            print(f"[os.environ] Raw bytes: {raw.encode()!r}")
    else:
        print(f"[os.environ] DATABASE_URL: SET ({safe_summary(raw.strip())})")
        # Check for invisible chars that could break parsing
        stripped = raw.strip()
        cleaned = stripped.replace("\ufeff", "").replace("\x00", "")
        cleaned = "".join(ch for ch in cleaned if ch not in "\n\r\t")
        if len(cleaned) != len(stripped):
            print(
                f"[os.environ] WARNING: invisible chars detected! "
                f"raw_len={len(stripped)}, clean_len={len(cleaned)}"
            )
            print(f"[os.environ] First 30 raw bytes: {stripped[:30].encode()!r}")

    # 2. Check python-decouple
    decouple_url = ""
    try:
        from decouple import config as decouple_config

        value = decouple_config("DATABASE_URL", default="__NOT_SET__")
        if value == "__NOT_SET__":
            print("[decouple]   DATABASE_URL: NOT SET (got default)")
        elif not value.strip():
            print("[decouple]   DATABASE_URL: EMPTY")
        else:
            decouple_url = value.strip()
            print(f"[decouple]   DATABASE_URL: SET ({safe_summary(decouple_url)})")

        # Check if os.environ and decouple agree
        if raw is not None and value != "__NOT_SET__":
            if raw.strip() == value.strip():
                print("[match]      os.environ and decouple AGREE")
            else:
                print("[MISMATCH]   os.environ and decouple DISAGREE!")
    except Exception as exc:
        print(f"[decouple]   ERROR: {exc!r}")

    # 3. Check for .env files that decouple might read
    print("\n[files]      .env files in /app/:")
    app_dir = "/app" if os.path.isdir("/app") else os.getcwd()
    for f in sorted(os.listdir(app_dir)):
        if f.startswith(".env"):
            fpath = os.path.join(app_dir, f)
            print(f"  {f} ({os.path.getsize(fpath)} bytes)")

    # 4. Test dj_database_url.parse for BOTH sources
    try:
        import dj_database_url
    except Exception as exc:
        print(f"\n[dj_db_url]  ERROR: could not import dj_database_url: {exc}")
        dj_database_url = None

    if dj_database_url:
        env_url = (raw or "").strip()
        if env_url:
            try:
                result = dj_database_url.parse(env_url)
                print(
                    f"\n[dj_db_url]  os.environ parse: OK "
                    f"(engine={result.get('ENGINE')})"
                )
            except Exception as exc:
                print(f"\n[dj_db_url]  os.environ parse: FAILED ({exc})")
        else:
            print("\n[dj_db_url]  os.environ parse: skipped (not set)")

        if decouple_url:
            try:
                result = dj_database_url.parse(decouple_url)
                print(
                    f"[dj_db_url]  decouple parse: OK "
                    f"(engine={result.get('ENGINE')})"
                )
            except Exception as exc:
                print(f"[dj_db_url]  decouple parse: FAILED ({exc})")
        else:
            print("[dj_db_url]  decouple parse: skipped (not set)")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
