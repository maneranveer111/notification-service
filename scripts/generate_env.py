#!/usr/bin/env python3
"""Generate .env from .env.example with random secrets filled in.

Usage:
    python scripts/generate_env.py

If .env already exists the script prints a warning and exits without overwriting.
"""
import base64
import re
import secrets
import sys
from pathlib import Path

# Repo root is one level above this script.
ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
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
    if key.upper() == "ENCRYPTION_KEY":
        # Fernet key: 32 random bytes, base64url-encoded with padding (44 chars).
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    return secrets.token_urlsafe(32)


def main() -> None:
    if not ENV_EXAMPLE.exists():
        print(f"Error: {ENV_EXAMPLE} not found.", file=sys.stderr)
        sys.exit(1)

    if ENV_FILE.exists():
        print(
            f"Warning: {ENV_FILE} already exists. "
            "Remove it first if you want to regenerate.",
            file=sys.stderr,
        )
        sys.exit(0)

    output_lines: list[str] = []
    generated: list[str] = []

    for raw_line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines(keepends=True):
        line = raw_line.rstrip("\n")

        # Pass through blank lines and comments unchanged.
        if not line or line.lstrip().startswith("#"):
            output_lines.append(raw_line)
            continue

        # Parse KEY=VALUE (inline comments are not supported in .env).
        if "=" not in line:
            output_lines.append(raw_line)
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if is_secret_key(key) and is_placeholder_value(value):
            new_value = generate_value(key)
            output_lines.append(f"{key}={new_value}\n")
            generated.append(key)
        else:
            output_lines.append(raw_line)

    ENV_FILE.write_text("".join(output_lines), encoding="utf-8")
    print(f"Created {ENV_FILE}")
    if generated:
        print(f"Generated random values for: {', '.join(generated)}")


if __name__ == "__main__":
    main()
