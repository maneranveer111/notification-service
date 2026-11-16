"""
Spec 1 guard: scan tracked text files for personal data.
Fails (printing only file:line, never the value) when it finds:
  (a) a real E.164 phone number outside the allowed fictional set
  (b) a Windows or macOS user path
  (c) an email whose domain is not in the allow-list
"""
import os
import re
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]  # repo root

# --- allow-lists -----------------------------------------------------------
# (a) Fictional phone prefixes: +1<xxx>5550100 through +1<xxx>5550199
# and Twilio documented test numbers.
_TWILIO_TEST = {
    "+15005550006",
    "+15005550001",
    "+15005550007",
    "+15005550008",
    "+15005550009",
}
_FICTION_RE = re.compile(r"^\+1\d{3}55501\d{2}$")

def _phone_allowed(match_str: str) -> bool:
    if match_str in _TWILIO_TEST:
        return True
    return bool(_FICTION_RE.match(match_str))

# (c) Allowed email domains
_ALLOWED_DOMAINS = {
    "example.com",
    "example.org",
    "example.test",
    "localhost",
    "users.noreply.github.com",
}
_PLACEHOLDER_EMAIL_RE = re.compile(r"^<[^>]+>$")  # e.g. <email@example.com>

# --- patterns to scan for --------------------------------------------------
_PHONE_RE = re.compile(r"\+[1-9]\d{9,14}")
_WIN_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE)
_FILE_URI_RE = re.compile(r"file:///[a-zA-Z]:/Users", re.IGNORECASE)
_MAC_PATH_RE = re.compile(r"/Users/[a-zA-Z][^/\s]{1,30}/")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# --- file exclusions -------------------------------------------------------
_EXCLUDED_DIRS = {
    "node_modules", ".git", "dist", "backups", "venv", ".venv",
    "__pycache__", ".agents", ".pytest_cache", ".gemini",
}
_EXCLUDED_EXT = {
    ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".map", ".pyc",
    ".db", ".sqlite", ".bin", ".exe", ".sql",
}
_EXCLUDED_FILENAMES = {".env", ".env.example", ".env.production.example", ".env.production"}


def _iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in _EXCLUDED_EXT:
            continue
        if path.name in _EXCLUDED_FILENAMES:
            continue
        if path.name.startswith(".env"):
            continue
        # Skip binary-ish files quickly
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        yield path, text


def test_no_real_personal_data():
    failures = []

    for path, text in _iter_text_files():
        rel = path.relative_to(ROOT)
        for lineno, line in enumerate(text.splitlines(), start=1):
            # (a) Real phone numbers
            for m in _PHONE_RE.finditer(line):
                phone = m.group()
                if not _phone_allowed(phone):
                    failures.append(f"{rel}:{lineno} — real E.164 phone found")

            # (b) Machine user paths
            if _WIN_PATH_RE.search(line) or _FILE_URI_RE.search(line):
                failures.append(f"{rel}:{lineno} — Windows user path found")
            if _MAC_PATH_RE.search(line):
                failures.append(f"{rel}:{lineno} — macOS user path found")

            # (c) Real email domains
            for m in _EMAIL_RE.finditer(line):
                email = m.group()
                domain = email.rsplit("@", 1)[-1].lower()
                if domain in _ALLOWED_DOMAINS:
                    continue
                if _PLACEHOLDER_EMAIL_RE.match(email):
                    continue
                # Ignore emails inside ignored dirs (venv etc.) — already filtered by _iter_text_files
                failures.append(f"{rel}:{lineno} — email with non-allowed domain found")

    if failures:
        # Print only file:line references, never the actual values.
        msg = "\n".join(failures)
        pytest.fail(f"Personal data found in tracked files:\n{msg}")
