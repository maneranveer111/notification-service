#!/usr/bin/env python3
"""Generate .env from .env.example or .env.production.example with random secrets.

Usage:
    python scripts/generate_env.py
    python scripts/generate_env.py --production --domain notify.example.com [--force]
"""
import argparse
import base64
import re
import secrets
import sys
from pathlib import Path

# Repo root is one level above this script.
ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_PROD_EXAMPLE = ROOT / ".env.production.example"
ENV_FILE = ROOT / ".env"

# Keys that need a random value generated.
SECRET_KEY_PATTERN = re.compile(r"SECRET|KEY|TOKEN|PASSWORD|SALT", re.IGNORECASE)

# Placeholder values that should be replaced.
PLACEHOLDER_PATTERN = re.compile(
    r"^$|replace|your-|changeme|xxxxxx|placeholder",
    re.IGNORECASE,
)


def is_secret_key(key: str) -> bool:
    return bool(SECRET_KEY_PATTERN.search(key))


def is_placeholder_value(value: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.search(value))


def generate_value(key: str) -> str:
    """Return a cryptographically random value appropriate for the given key."""
    k = key.upper()
    if k == "ENCRYPTION_KEY":
        # Fernet key: 32 random bytes, base64url-encoded with padding (44 chars).
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    if k == "JWT_SECRET":
        return secrets.token_urlsafe(40)
    if k == "POSTGRES_PASSWORD":
        return secrets.token_urlsafe(24)
    return secrets.token_urlsafe(32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate .env configuration file.")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Use .env.production.example and generate production configuration",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="localhost",
        help="Domain name for production deployment (e.g. notify.example.com)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .env file if it exists",
    )
    args = parser.parse_args()

    source_example = ENV_PROD_EXAMPLE if args.production else ENV_EXAMPLE

    if not source_example.exists():
        print(f"Error: {source_example} not found.", file=sys.stderr)
        sys.exit(1)

    if ENV_FILE.exists() and not args.force:
        print(
            f"Warning: {ENV_FILE} already exists. "
            "Use --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(0)

    domain = args.domain.strip()
    protocol = "http" if domain in ("localhost", "127.0.0.1") else "https"

    output_lines: list[str] = []
    generated: list[str] = []

    for raw_line in source_example.read_text(encoding="utf-8").splitlines(keepends=True):
        line = raw_line.rstrip("\n")

        # Pass through blank lines and comments unchanged.
        if not line or line.lstrip().startswith("#"):
            output_lines.append(raw_line)
            continue

        if "=" not in line:
            output_lines.append(raw_line)
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        # Handle domain-derived variables in production mode
        if args.production:
            if key == "DOMAIN":
                output_lines.append(f"DOMAIN={domain}\n")
                continue
            if key == "PUBLIC_BASE_URL":
                output_lines.append(f"PUBLIC_BASE_URL={protocol}://{domain}/api\n")
                continue
            if key in ("FRONTEND_URL", "FRONTEND_PUBLIC_URL"):
                output_lines.append(f"{key}={protocol}://{domain}\n")
                continue

        # Skip CAPTCHA keys if left empty
        if key in ("TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY") and not value:
            output_lines.append(raw_line)
            continue

        # Generate secrets
        if is_secret_key(key) and (is_placeholder_value(value) or not value):
            new_value = generate_value(key)
            output_lines.append(f"{key}={new_value}\n")
            generated.append(key)
        else:
            output_lines.append(raw_line)

    ENV_FILE.write_text("".join(output_lines), encoding="utf-8")
    print(f"Created {ENV_FILE} from {source_example.name}")
    if generated:
        print(f"Generated random secrets for: {', '.join(generated)}")

    if args.production:
        print("\nNext steps:")
        print(f"1. DNS: Configure an A/AAAA record pointing '{domain}' to your server IP.")
        print("2. Firewall: Open inbound ports 80 (HTTP) and 443 (HTTPS).")
        print("3. Deploy: Start all containers with:")
        print("       docker compose -f docker-compose.prod.yml up -d --build")
        print(f"4. Initial Setup: Visit {protocol}://{domain} to create the first admin through the setup screen.")
        print("   (The first registered user automatically becomes the superadmin.)")


if __name__ == "__main__":
    main()
