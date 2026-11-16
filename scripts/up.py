#!/usr/bin/env python3
"""Start the Notification Service Docker Compose stack deterministically.

Usage:
    python scripts/up.py [--prod] [--build] [--fresh] [--project NAME]
                         [--web-port N] [--api-host-port N] [--down-after]
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd: list[str], env: dict[str, str] | None = None, check: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess command safely."""
    return subprocess.run(cmd, cwd=str(ROOT), env=env or os.environ.copy(), text=True, check=check)


def get_docker_cmd() -> list[str]:
    docker = shutil.which("docker")
    if not docker:
        print("[FAIL] 'docker' executable not found on PATH.", file=sys.stderr)
        sys.exit(1)
    return [docker]


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic Docker Compose startup runner")
    parser.add_argument("--prod", action="store_true", help="Use production compose file (docker-compose.prod.yml)")
    parser.add_argument("--build", action="store_true", help="Build images before starting containers")
    parser.add_argument("--fresh", action="store_true", help="Tear down volumes and orphans before starting")
    parser.add_argument("--project", type=str, default="", help="Docker Compose project name")
    parser.add_argument("--web-port", type=str, default="8080", help="Web host port (default: 8080)")
    parser.add_argument("--api-host-port", type=str, default="8001", help="API host port (default: 8001)")
    parser.add_argument("--down-after", action="store_true", help="Tear down stack at completion (notification-verify only)")

    args = parser.parse_args()

    if args.down_after and args.project != "notification-verify":
        print("[FAIL] --down-after is only allowed together with --project notification-verify", file=sys.stderr)
        sys.exit(1)

    compose_file = "docker-compose.prod.yml" if args.prod else "docker-compose.yml"
    project_name = args.project or ("notification-prod" if args.prod else "notification-dev")

    # Set port overrides in environment
    env = os.environ.copy()
    env["WEB_PORT"] = args.web_port
    env["API_HOST_PORT"] = args.api_host_port

    docker_base = get_docker_cmd() + ["compose", "-p", project_name, "-f", compose_file]

    # Handle --fresh
    if args.fresh:
        if args.project != "notification-verify":
            print(f"WARNING: --fresh will delete all data and volumes for project '{project_name}'.")
            confirm = input("Type 'yes' to proceed: ").strip()
            if confirm != "yes":
                print("Aborting.")
                sys.exit(0)
        print(f"[{project_name}] Tearing down existing stack and volumes...")
        run_cmd(docker_base + ["down", "-v", "--remove-orphans"], env=env)

    # Build up command
    up_cmd = docker_base + ["up", "-d"]
    if args.build:
        up_cmd.append("--build")
    up_cmd.extend(["--remove-orphans", "--wait", "--wait-timeout", "240"])

    print(f"[{project_name}] Starting services using {compose_file}...")
    proc = run_cmd(up_cmd, env=env)

    if proc.returncode != 0:
        print("\n=== STARTUP FAILURE DIAGNOSTIC ===")
        print("\n--- Container States ---")
        run_cmd(docker_base + ["ps", "-a"], env=env)

        # Inspect migrate container exit code
        migrate_exit = None
        inspect_proc = subprocess.run(
            get_docker_cmd() + ["inspect", f"{project_name}-migrate-1", "--format", "{{.State.ExitCode}}"],
            capture_output=True,
            text=True,
        )
        if inspect_proc.returncode == 0 and inspect_proc.stdout.strip().isdigit():
            migrate_exit = int(inspect_proc.stdout.strip())

        print("\n--- Recent Logs (migrate first) ---")
        run_cmd(docker_base + ["logs", "--tail=60", "migrate"], env=env)

        # Check logs for other non-healthy containers
        ps_out = subprocess.run(
            docker_base + ["ps", "--format", "{{.Service}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            env=env,
        )
        if ps_out.returncode == 0:
            for line in ps_out.stdout.strip().splitlines():
                if not line:
                    continue
                svc = line.split("\t")[0]
                if svc != "migrate" and ("unhealthy" in line or "Exit" in line):
                    print(f"\n--- Logs for {svc} ---")
                    run_cmd(docker_base + ["logs", "--tail=60", svc], env=env)

        print("\n--- Database Blocker Activity ---")
        blocker_sql = (
            "SELECT pid, state, wait_event_type, wait_event, clock_timestamp() - state_change AS age, "
            "left(query, 100) AS query FROM pg_stat_activity WHERE datname = current_database(); "
            "SELECT pid, unnest(pg_blocking_pids(pid)) AS blocking_pid FROM pg_stat_activity WHERE datname = current_database();"
        )
        exec_cmd = docker_base + [
            "exec", "-T", "db", "sh", "-c",
            f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "{blocker_sql}"'
        ]
        run_cmd(exec_cmd, env=env)

        print("\n--- Plain-Language Diagnosis ---")
        if migrate_exit == 2:
            print("Diagnosis: Database not reachable (exit code 2). Check database container health and connection credentials.")
        elif migrate_exit == 3:
            print("Diagnosis: Lock timeout or migration error (exit code 3). A lock or conflicting migration failed.")
            print("Next step: Run 'python scripts/up.py --fresh' for dev data you can lose, or terminate the blocking PIDs shown above.")
        elif migrate_exit == 4:
            print("Diagnosis: Migration watchdog timed out (exit code 4). Alembic execution was hung for > 240 seconds.")
        else:
            print(f"Diagnosis: Startup failed (migrate exit code: {migrate_exit}). Inspect the container logs above.")

        if args.down_after:
            print(f"\n[{project_name}] Tearing down temporary verification project...")
            run_cmd(docker_base + ["down", "-v", "--remove-orphans"], env=env)

        sys.exit(1)

    print(f"\n[{project_name}] All services started and healthy!")
    print(f"Web URL:        http://localhost:{args.web_port}")
    print(f"Direct API URL: http://127.0.0.1:{args.api_host_port}")

    doctor_script = ROOT / "scripts" / "doctor.py"
    if doctor_script.exists():
        print("\n--- Doctor Validation ---")
        doc_proc = subprocess.run(
            [sys.executable, str(doctor_script), "--base", f"http://localhost:{args.web_port}", "--direct", f"http://127.0.0.1:{args.api_host_port}"],
            capture_output=True,
            text=True,
        )
        # Print summary lines from doctor
        summary_lines = [l for l in doc_proc.stdout.splitlines() if "[OK]" in l or "[FAIL]" in l or "[WARN]" in l]
        print("\n".join(summary_lines[:8]) if summary_lines else doc_proc.stdout)

    if args.down_after:
        print(f"\n[{project_name}] Tearing down temporary verification project (--down-after)...")
        run_cmd(docker_base + ["down", "-v", "--remove-orphans"], env=env)
        print(f"[{project_name}] Teardown complete.")

    sys.exit(0)


if __name__ == "__main__":
    main()
