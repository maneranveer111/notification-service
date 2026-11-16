"""
Guard test: no file in the repository may contain a bare :8000 port reference,
an EXPOSE 8000, --port 8000, or PORT=8000 / PORT: 8000 reference.

Lines containing the comment  # allow-8000  are explicitly excluded so that
doctor.py can keep its "warn on port 8000 as a stale dev process" check.
"""
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Repository root — resolved relative to this test file (backend/tests/)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SKIP_DIRS = {"node_modules", ".git", ".agents", "dist", "__pycache__", "backups", "venv", ".pytest_cache"}

EXTENSIONS = {
    ".yml", ".yaml", ".conf", ".md", ".py", ".js", ".jsx",
    ".json", ".sh", ".txt", ".example",
}
# Also include Dockerfile* and .env* files
NAME_PATTERNS = (re.compile(r"^Dockerfile"), re.compile(r"^\.env"))

# Regexes that must NOT appear (unless the line has # allow-8000)
FORBIDDEN_PATTERNS = [
    re.compile(r":8000\b"),
    re.compile(r"--port[ =]8000\b"),
    re.compile(r"EXPOSE 8000\b"),
    re.compile(r"PORT[=: ]+8000\b"),
]

# This test file itself — skip it to avoid a false positive
_THIS_FILE = Path(__file__).resolve()


def _should_scan(path: Path) -> bool:
    """Return True if path is a text file we want to scan."""
    if not path.is_file():
        return False
    if path.resolve() == _THIS_FILE:
        return False
    # Skip anything inside a forbidden directory at any level
    for part in path.parts:
        if part in SKIP_DIRS:
            return False
    # Accept by extension or by name pattern
    if path.suffix.lower() in EXTENSIONS:
        return True
    for pat in NAME_PATTERNS:
        if pat.match(path.name):
            return True
    return False


def _collect_violations() -> list[str]:
    violations: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not _should_scan(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for lineno, line in enumerate(lines, start=1):
            if "allow-8000" in line:
                continue
            for pat in FORBIDDEN_PATTERNS:
                if pat.search(line):
                    rel = path.relative_to(REPO_ROOT)
                    violations.append(f"{rel}:{lineno}: {line.strip()}")
                    break  # one violation per line is enough
    return violations


def test_no_port_8000_in_repo():
    """No file may reference port 8000 (unless the line contains # allow-8000)."""
    violations = _collect_violations()
    assert violations == [], (
        f"Found {len(violations)} forbidden port-8000 reference(s):\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def test_nginx_conf_uses_8001():
    """frontend/nginx.conf must proxy to api:8001."""
    nginx = REPO_ROOT / "frontend" / "nginx.conf"
    assert nginx.exists(), "frontend/nginx.conf not found"
    content = nginx.read_text(encoding="utf-8")
    assert "api:8001" in content, (
        "frontend/nginx.conf does not contain 'api:8001'; nginx will not reach the API container"
    )


def test_compose_uses_port_8001():
    """docker-compose.yml api service must use --port 8001."""
    compose = REPO_ROOT / "docker-compose.yml"
    assert compose.exists(), "docker-compose.yml not found"
    content = compose.read_text(encoding="utf-8")
    assert "--port 8001" in content, (
        "docker-compose.yml does not contain '--port 8001' for the api service"
    )
