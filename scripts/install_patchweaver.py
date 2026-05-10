#!/usr/bin/env python3
"""Curated installer for PatchWeaver external delivery.

This entrypoint wraps the lower-level deployment preflight with a more formal
installation flow: environment preflight, runtime installation, and post-install
verification.  Dry-run mode is safe and does not mutate the project or host.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PRESETS = {"validation", "demo", "developer"}


@dataclass
class Phase:
    name: str
    title: str
    command: list[str] | None
    mutating: bool
    status: str = "pending"
    detail: str = ""
    returncode: int | None = None
    payload: dict[str, Any] | None = None


@dataclass
class InstallerContext:
    project_root: Path
    preset: str
    target_kernel: str | None
    dry_run: bool
    json_output: bool
    with_db: bool
    skip_install: bool
    skip_doctor: bool
    install_api_service: bool
    host: str
    port: int
    phases: list[Phase] = field(default_factory=list)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install PatchWeaver with a guided delivery-grade workflow.",
    )
    parser.add_argument("--preset", choices=sorted(PRESETS), default="validation", help="Installation profile.")
    parser.add_argument("--target-kernel", help="Expected target kernel release.")
    parser.add_argument("--dry-run", action="store_true", help="Preview the full installation plan without mutations.")
    parser.add_argument("--json", action="store_true", help="Emit a single machine-readable JSON document.")
    parser.add_argument("--with-db", action="store_true", help="Initialize runtime directories and SQLite database.")
    parser.add_argument("--skip-install", action="store_true", help="Skip editable package installation.")
    parser.add_argument("--skip-doctor", action="store_true", help="Skip post-install doctor verification.")
    parser.add_argument("--install-api-service", action="store_true", help="Install the Web/API systemd service on Linux.")
    parser.add_argument("--host", default="0.0.0.0", help="API service bind host when --install-api-service is used.")
    parser.add_argument("--port", type=int, default=18084, help="API service port when --install-api-service is used.")
    parser.add_argument(
        "--project-root",
        default=None,
        help="PatchWeaver project root. Defaults to the parent of this script's scripts directory.",
    )
    return parser.parse_args(argv)


def resolve_project_root(raw_root: str | None) -> Path:
    if raw_root:
        return Path(raw_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def run_command(command: list[str], *, cwd: Path) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def build_context(args: argparse.Namespace) -> InstallerContext:
    return InstallerContext(
        project_root=resolve_project_root(args.project_root),
        preset=args.preset,
        target_kernel=args.target_kernel,
        dry_run=args.dry_run,
        json_output=args.json,
        with_db=args.with_db,
        skip_install=args.skip_install,
        skip_doctor=args.skip_doctor,
        install_api_service=args.install_api_service,
        host=args.host,
        port=args.port,
    )


def deploy_command(ctx: InstallerContext, *, dry_run: bool) -> list[str]:
    script = ctx.project_root / "scripts" / "deploy_patchweaver.py"
    command = [
        sys.executable,
        str(script),
        "--project-root",
        str(ctx.project_root),
        "--json",
    ]
    if dry_run:
        command.append("--dry-run")
    if ctx.target_kernel:
        command.extend(["--target-kernel", ctx.target_kernel])
    if ctx.with_db:
        command.append("--with-db")
    if ctx.skip_install:
        command.append("--skip-install")
    if ctx.skip_doctor:
        command.append("--skip-doctor")
    return command


def api_service_command(ctx: InstallerContext) -> list[str]:
    return [
        sys.executable,
        "-m",
        "patchweaver",
        "install-api-service",
        "--host",
        ctx.host,
        "--port",
        str(ctx.port),
        "--service-name",
        "patchweaver-web",
        "--json",
    ]


def build_phases(ctx: InstallerContext) -> None:
    ctx.phases = [
        Phase(
            name="environment_preflight",
            title="Environment preflight",
            command=deploy_command(ctx, dry_run=True),
            mutating=False,
            detail="Validate Python, kernel, kpatch-build, and configured build paths.",
        ),
        Phase(
            name="runtime_installation",
            title="Runtime installation",
            command=deploy_command(ctx, dry_run=False),
            mutating=True,
            detail="Install editable package, initialize runtime state, and run deployment checks.",
        ),
        Phase(
            name="post_install_verification",
            title="Post-install verification",
            command=api_service_command(ctx) if ctx.install_api_service else [sys.executable, "-m", "patchweaver", "doctor", "--json"],
            mutating=ctx.install_api_service,
            detail="Verify CLI and optionally register the Web/API service.",
        ),
    ]


def execute(ctx: InstallerContext) -> int:
    build_phases(ctx)
    exit_code = 0

    for phase in ctx.phases:
        if ctx.dry_run:
            if phase.name == "environment_preflight" and phase.command:
                code, stdout, stderr = run_command(phase.command, cwd=ctx.project_root)
                phase.returncode = code
                phase.status = "passed" if code == 0 else "failed"
                phase.payload = _try_parse_json(stdout)
                if stderr and not ctx.json_output:
                    print(stderr, file=sys.stderr)
                if code != 0:
                    exit_code = code
            else:
                phase.status = "planned"
            continue

        if not phase.command:
            phase.status = "skipped"
            continue
        code, stdout, stderr = run_command(phase.command, cwd=ctx.project_root)
        phase.returncode = code
        phase.payload = _try_parse_json(stdout)
        phase.status = "passed" if code == 0 else "failed"
        if stdout and not ctx.json_output:
            print(stdout)
        if stderr and not ctx.json_output:
            print(stderr, file=sys.stderr)
        if code != 0:
            exit_code = code
            break

    return exit_code


def _try_parse_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def payload(ctx: InstallerContext, exit_code: int) -> dict[str, Any]:
    mutating_steps_planned = 0 if ctx.dry_run else sum(1 for phase in ctx.phases if phase.mutating and phase.status != "skipped")
    phase_payloads = [
        {
            "name": phase.name,
            "title": phase.title,
            "status": phase.status,
            "mutating": phase.mutating,
            "command": phase.command,
            "detail": phase.detail,
            "returncode": phase.returncode,
            "payload": phase.payload,
        }
        for phase in ctx.phases
    ]
    failed = sum(1 for phase in ctx.phases if phase.status == "failed")
    passed = sum(1 for phase in ctx.phases if phase.status == "passed")
    planned = sum(1 for phase in ctx.phases if phase.status == "planned")
    return {
        "command": "install_patchweaver",
        "preset": ctx.preset,
        "project_root": str(ctx.project_root),
        "target_kernel": ctx.target_kernel,
        "dry_run": ctx.dry_run,
        "phases": phase_payloads,
        "summary": {
            "passed": passed,
            "planned": planned,
            "failed": failed,
            "mutating_steps_planned": mutating_steps_planned,
            "exit_code": exit_code,
        },
        "next_steps": [
            "patchweaver doctor --json",
            "patchweaver serve-api --host 0.0.0.0 --port 18084 --foreground",
            "patchweaver create --cve CVE-2024-26742 --task-id demo-26742 --json",
        ],
    }


def print_text(result: dict[str, Any]) -> None:
    print("PatchWeaver installer")
    print(f"Preset: {result['preset']}")
    print(f"Project root: {result['project_root']}")
    print(f"Target kernel: {result['target_kernel'] or 'auto'}")
    print(f"Mode: {'dry-run' if result['dry_run'] else 'execute'}")
    print("")
    print("Phases:")
    for phase in result["phases"]:
        print(f"  [{phase['status']}] {phase['name']} - {phase['title']}")
        print(f"      {phase['detail']}")
        if phase["command"]:
            print(f"      command: {' '.join(phase['command'])}")
    print("")
    print("Next steps:")
    for step in result["next_steps"]:
        print(f"  - {step}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    ctx = build_context(args)
    exit_code = execute(ctx)
    result = payload(ctx, exit_code)
    if ctx.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text(result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

