#!/usr/bin/env python3
"""Doctor script: stack hygiene and health validation.

Usage:
    python scripts/doctor.py [--base http://localhost:8080] [--direct http://localhost:8001 ...]
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


def check_line_endings():
    patterns = ["*.sh", "Dockerfile*", "*.conf", "*.yml", "*.yaml", "Caddyfile"]
    crlf_files = []
    checked = 0

    ignore_dirs = {".git", "node_modules", "venv", ".pytest_cache", "dist", "build"}

    files_to_check = set()
    for pat in patterns:
        for p in ROOT.rglob(pat):
            if not any(part in ignore_dirs for part in p.parts):
                files_to_check.add(p)

    entrypoint = ROOT / "frontend" / "docker-entrypoint.d" / "10-config.sh"
    if entrypoint.exists():
        files_to_check.add(entrypoint)

    for p in sorted(files_to_check):
        if p.is_file():
            checked += 1
            try:
                data = p.read_bytes()
                if b"\r\n" in data:
                    crlf_files.append(str(p.relative_to(ROOT)))
            except Exception:
                pass

    if crlf_files:
        print(f"[FAIL] Line endings: Found CRLF in {len(crlf_files)} file(s): {', '.join(crlf_files[:5])}")
        print("       Fix: Run 'git add --renormalize .' or convert line endings to LF with dos2unix/sed.")
        return False
    else:
        print(f"[OK]   Line endings: All {checked} scanned files use LF line endings.")
        return True


def parse_env_keys(path: Path) -> dict[str, str]:
    keys = {}
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        keys[k.strip()] = v.strip()
    return keys


def check_env_file():
    if not ENV_FILE.exists():
        print("[FAIL] Environment: .env file missing at repository root.")
        print("       Fix: Run 'python scripts/generate_env.py' to generate a .env file.")
        return False, {}

    current_keys = parse_env_keys(ENV_FILE)
    example_keys = parse_env_keys(ENV_EXAMPLE)

    missing = [k for k in example_keys if k not in current_keys]
    if missing:
        print(f"[WARN] Environment: .env is missing {len(missing)} key(s) from .env.example: {', '.join(missing[:5])}")
        print("       Fix: Copy missing keys from .env.example into your .env file.")
        return False, current_keys
    else:
        print(f"[OK]   Environment: .env is present with all {len(example_keys)} keys from .env.example.")
        return True, current_keys


def is_port_open(port: int, host="127.0.0.1") -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        res = s.connect_ex((host, port))
        return res == 0
    except Exception:
        return False
    finally:
        s.close()


def check_ports(env_keys: dict[str, str]):
    web_port = int(env_keys.get("WEB_PORT", 8080))
    http_port = int(env_keys.get("HTTP_PORT", 80))
    https_port = int(env_keys.get("HTTPS_PORT", 443))

    ports_to_check = [
        (8000, "API dev default"),
        (8001, "API alt / test default"),
        (5173, "Vite frontend dev default"),
        (web_port, f"WEB_PORT ({web_port})"),
        (http_port, f"HTTP_PORT ({http_port})"),
        (https_port, f"HTTPS_PORT ({https_port})"),
    ]

    for port, label in ports_to_check:
        open_status = is_port_open(port)
        if port in (8000, 5173) and open_status:
            print(f"[WARN] Port {port} ({label}): accepting connections.")
            print("       Fix: A listener on 8000 or 5173 is probably an old local dev process. Terminate it if using Docker.")
        elif open_status:
            print(f"[OK]   Port {port} ({label}): accepting connections.")
        else:
            print(f"[INFO] Port {port} ({label}): not currently listening.")


def check_docker():
    docker_bin = shutil.which("docker")
    if not docker_bin:
        print("[WARN] Docker: docker CLI is not installed or not found on PATH.")
        print("       Fix: Install Docker if running the service in containers.")
        return

    try:
        res_info = subprocess.run([docker_bin, "info"], capture_output=True, text=True, timeout=5)
        if res_info.returncode != 0:
            print("[WARN] Docker: docker CLI found but Docker daemon is not responding.")
            print("       Fix: Start Docker Desktop or daemon.")
            return
    except Exception:
        print("[WARN] Docker: Failed to connect to Docker daemon.")
        print("       Fix: Start Docker Desktop or daemon.")
        return

    # Check compose ls
    try:
        proc_ls = subprocess.run([docker_bin, "compose", "ls", "--format", "json"], capture_output=True, text=True, timeout=5)
        if proc_ls.returncode == 0 and proc_ls.stdout.strip():
            try:
                projects = json.loads(proc_ls.stdout)
                names = [p.get("Name", "") for p in projects if isinstance(p, dict)]
                if "notification-dev" in names and "notification-prod" in names:
                    print("[WARN] Docker: Both notification-dev and notification-prod stacks appear active.")
                    print("       Fix: Stop one with 'docker compose down --remove-orphans'.")
            except Exception:
                pass
    except Exception:
        pass

    # Check containers
    try:
        proc_ps = subprocess.run(
            [docker_bin, "ps", "-a", "--filter", "name=notification", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc_ps.returncode == 0:
            lines = proc_ps.stdout.strip().splitlines()
            exited = [line for line in lines if "Exited" in line]
            if exited:
                print(f"[WARN] Docker: {len(exited)} notification container(s) are in Exited state.")
                print("       Fix: Check logs with 'docker compose logs <service>' and restart.")
            else:
                print(f"[OK]   Docker: {len(lines)} notification container(s) detected with no exited containers.")
    except Exception:
        pass


def get_ssl_context(url: str):
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname in ("localhost", "127.0.0.1"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def fetch_json(url: str):
    ctx = get_ssl_context(url)
    req = urllib.request.Request(url, headers={"User-Agent": "notification-doctor/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url: str):
    ctx = get_ssl_context(url)
    req = urllib.request.Request(url, headers={"User-Agent": "notification-doctor/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
        return resp.read().decode("utf-8")


def check_endpoints(base_url: str, direct_urls: list[str]):
    base = base_url.rstrip("/")
    print(f"\nProbing Base URL: {base}")
    base_config = None
    try:
        base_config = fetch_json(f"{base}/api/public/config")
        print(f"[OK]   {base}/api/public/config fetched successfully.")
        print(f"       signup_mode: {base_config.get('signup_mode')} | needs_setup: {base_config.get('needs_setup')}")
        print(f"       environment: {base_config.get('environment')} | version: {base_config.get('version')}")
    except Exception as e:
        print(f"[FAIL] Failed to fetch {base}/api/public/config: {e}")
        print("       Fix: Ensure web proxy and backend api containers are healthy.")
        return

    try:
        config_js = fetch_text(f"{base}/config.js")
        print(f"[OK]   {base}/config.js fetched ({len(config_js)} bytes).")
    except Exception as e:
        print(f"[WARN] Failed to fetch {base}/config.js: {e}")
        print("       Fix: Check frontend container startup script.")

    try:
        health = fetch_json(f"{base}/api/health")
        print(f"[OK]   {base}/api/health: {health.get('status')}")
    except Exception as e:
        print(f"[WARN] Failed to fetch {base}/api/health: {e}")
        print("       Fix: Check api service logs.")

    if direct_urls:
        print("\nComparing with Direct Backend URLs:")
        for direct in direct_urls:
            d = direct.rstrip("/")
            try:
                direct_cfg = fetch_json(f"{d}/public/config")
                mismatches = []
                for k in ["signup_mode", "needs_setup", "environment", "version"]:
                    if base_config.get(k) != direct_cfg.get(k):
                        mismatches.append(f"{k} (base={base_config.get(k)}, direct={direct_cfg.get(k)})")

                if mismatches:
                    print(f"[FAIL] Direct backend ({d}) disagrees with base ({base}): {', '.join(mismatches)}")
                    print("       Fix: Ensure frontend and backend are reading the same database and environment config.")
                else:
                    print(f"[OK]   Direct backend ({d}) matches base configuration.")
            except Exception as e:
                print(f"[FAIL] Failed to fetch {d}/public/config: {e}")
                print(f"       Fix: Check direct backend listener on {d}.")


def main():
    parser = argparse.ArgumentParser(description="Notification Service System Doctor")
    parser.add_argument("--base", type=str, default="", help="Base URL of web service, e.g. http://localhost:8080")
    parser.add_argument("--direct", type=str, action="append", default=[], help="Direct backend URL(s) to verify against base")
    args = parser.parse_args()

    print("=== Notification Service System Doctor ===")
    check_line_endings()
    _, env_keys = check_env_file()
    check_ports(env_keys)
    check_docker()

    if args.base:
        check_endpoints(args.base, args.direct)
    print("\nDoctor check completed.")


if __name__ == "__main__":
    main()
