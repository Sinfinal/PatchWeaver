#!/usr/bin/env python3
"""Judge-facing one-step deployment and environment preflight for PatchWeaver.

The script is intentionally standalone so it can run before PatchWeaver's
editable install has completed.  Dry-run and print-plan modes never execute
commands that can change the Python environment or project runtime state.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MIN_PYTHON = (3, 11)
KEY_BUILD_PATHS = (
    "clean_kernel_src_dir",
    "vendor_kernel_src_dir",
    "stable_kernel_src_dir",
    "stable_source_git_dir",
    "stable_source_cache_dir",
    "prepared_kernel_src_dir",
    "kernel_src_dir",
    "kernel_devel_dir",
    "patched_kernel_src_dir",
    "vmlinux_path",
)


@dataclass
class Check:
    name: str
    status: str
    detail: str
    hint: str | None = None


@dataclass
class Step:
    name: str
    command: list[str] | None
    action: str
    skipped: bool = False
    reason: str | None = None
    returncode: int | None = None


@dataclass
class Context:
    project_root: Path
    config_path: Path
    target_kernel: str | None
    dry_run: bool
    json_output: bool
    print_plan: bool
    skip_install: bool
    skip_doctor: bool
    with_db: bool
    checks: list[Check] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy PatchWeaver and run judge-facing environment checks.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and checks without executing mutating commands.")
    parser.add_argument("--print-plan", action="store_true", help="Print the deployment plan and exit without executing it.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--skip-install", action="store_true", help="Do not run pip install -e .")
    parser.add_argument("--skip-doctor", action="store_true", help="Do not run patchweaver doctor.")
    parser.add_argument("--target-kernel", help="Expected target kernel release; defaults to uname -r when available.")
    parser.add_argument("--with-db", action="store_true", help="Run python -m patchweaver init --with-db before doctor.")
    parser.add_argument(
        "--project-root",
        default=None,
        help="PatchWeaver project root. Defaults to the parent of this script's scripts directory.",
    )
    return parser.parse_args(argv)


def status(ok: bool, *, warn: bool = False) -> str:
    if ok:
        return "ok"
    return "warn" if warn else "error"


def add_check(ctx: Context, name: str, status_value: str, detail: str, hint: str | None = None) -> None:
    ctx.checks.append(Check(name=name, status=status_value, detail=detail, hint=hint))


def resolve_project_root(raw_root: str | None) -> Path:
    if raw_root:
        return Path(raw_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def run_capture(command: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def detect_uname(project_root: Path) -> str | None:
    if platform.system().lower() == "windows":
        return None
    code, stdout, _stderr = run_capture(["uname", "-r"], project_root)
    if code == 0 and stdout:
        return stdout.splitlines()[0].strip()
    return None


def load_build_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-not-found]

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return load_simple_yaml(path)


def load_simple_yaml(path: Path) -> dict[str, Any]:
    """Small YAML fallback for the flat keys this preflight needs."""

    data: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line_without_comment = raw_line.split("#", 1)[0].rstrip()
        if not line_without_comment.strip():
            continue
        stripped = line_without_comment.strip()
        if stripped.startswith("- ") and current_key and current_list is not None:
            current_list.append(stripped[2:].strip().strip("\"'"))
            continue
        current_list = None
        current_key = None
        if ":" not in line_without_comment:
            continue
        key, raw_value = line_without_comment.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        current_key = key
        if value == "":
            current_list = []
            data[key] = current_list
        else:
            data[key] = value.strip("\"'")
    return data


def resolve_config_path(project_root: Path, raw_value: Any) -> tuple[str, bool] | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    raw_path = raw_value.strip()
    if raw_path.startswith("/") and os.name == "nt":
        # Preserve judge-machine POSIX paths when the preflight is previewed on Windows.
        return raw_path, False
    path = Path(raw_path).expanduser()
    resolved = path if path.is_absolute() else (project_root / path)
    return str(resolved), resolved.exists()


def check_python(ctx: Context) -> None:
    version = sys.version_info
    add_check(
        ctx,
        "python_version",
        status(version >= MIN_PYTHON),
        f"{version.major}.{version.minor}.{version.micro}",
        f"Use Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+." if version < MIN_PYTHON else None,
    )


def check_project(ctx: Context) -> None:
    pyproject = ctx.project_root / "pyproject.toml"
    package_dir = ctx.project_root / "patchweaver"
    add_check(ctx, "project_root", status(pyproject.exists() and package_dir.exists()), str(ctx.project_root))


def check_kpatch(ctx: Context, build_config: dict[str, Any]) -> None:
    configured_cmd = str(build_config.get("kpatch_build_cmd") or "kpatch-build")
    executable = configured_cmd.split()[0]
    found = shutil.which(executable)
    add_check(
        ctx,
        "kpatch_build",
        status(found is not None, warn=True),
        found or f"{executable} not found in PATH",
        "Install kpatch/kpatch-build on the Linux validation machine." if found is None else None,
    )


def check_kernel(ctx: Context) -> None:
    uname_kernel = detect_uname(ctx.project_root)
    expected = ctx.target_kernel or uname_kernel
    if uname_kernel is None:
        add_check(
            ctx,
            "target_kernel",
            "warn",
            f"uname -r unavailable on {platform.system()}; expected={expected or 'not set'}",
            "Run this script on the Linux validation machine or pass --target-kernel.",
        )
        return
    add_check(
        ctx,
        "target_kernel",
        status(expected == uname_kernel, warn=True),
        f"uname -r={uname_kernel}; expected={expected}",
        "Pass --target-kernel to document the intended kernel, or run on the target kernel." if expected != uname_kernel else None,
    )


def check_build_paths(ctx: Context, build_config: dict[str, Any]) -> None:
    if not ctx.config_path.exists():
        add_check(ctx, "build_config", "error", str(ctx.config_path), "Create config/build.yaml before deployment.")
        return
    add_check(ctx, "build_config", "ok", str(ctx.config_path))
    for key in KEY_BUILD_PATHS:
        resolved = resolve_config_path(ctx.project_root, build_config.get(key))
        if resolved is None:
            add_check(ctx, f"build_path.{key}", "warn", "not configured", f"Set {key} in config/build.yaml when required by validation.")
            continue
        display_path, path_exists = resolved
        add_check(
            ctx,
            f"build_path.{key}",
            status(path_exists, warn=True),
            display_path,
            f"Prepare this path on the validation machine or adjust config/build.yaml:{key}." if not path_exists else None,
        )


def build_plan(ctx: Context) -> None:
    if ctx.skip_install:
        ctx.steps.append(Step("install_editable", None, "skip", skipped=True, reason="--skip-install"))
    else:
        ctx.steps.append(Step("install_editable", [sys.executable, "-m", "pip", "install", "-e", "."], "execute"))
    if ctx.with_db:
        ctx.steps.append(Step("init_with_db", [sys.executable, "-m", "patchweaver", "init", "--with-db"], "execute"))
    else:
        ctx.steps.append(Step("init_with_db", None, "skip", skipped=True, reason="pass --with-db to initialize runtime dirs and SQLite"))
    if ctx.skip_doctor:
        ctx.steps.append(Step("doctor", None, "skip", skipped=True, reason="--skip-doctor"))
    else:
        ctx.steps.append(Step("doctor", [sys.executable, "-m", "patchweaver", "doctor", "--json"], "execute"))


def execute_plan(ctx: Context) -> int:
    if ctx.dry_run or ctx.print_plan:
        return 0
    failed = 0
    for step in ctx.steps:
        if step.skipped or not step.command:
            continue
        if not ctx.json_output:
            print(f"==> {' '.join(step.command)}")
        code, stdout, stderr = run_capture(step.command, ctx.project_root)
        step.returncode = code
        if stdout and not ctx.json_output:
            print(stdout)
        if stderr and not ctx.json_output:
            print(stderr, file=sys.stderr)
        if code != 0:
            failed = code
            break
    return failed


def summarize(ctx: Context, exit_code: int) -> dict[str, Any]:
    summary = {
        "ok": sum(1 for item in ctx.checks if item.status == "ok"),
        "warn": sum(1 for item in ctx.checks if item.status == "warn"),
        "error": sum(1 for item in ctx.checks if item.status == "error"),
    }
    return {
        "command": "deploy_patchweaver",
        "project_root": str(ctx.project_root),
        "dry_run": ctx.dry_run,
        "print_plan": ctx.print_plan,
        "target_kernel": ctx.target_kernel,
        "checks": [item.__dict__ for item in ctx.checks],
        "steps": [item.__dict__ for item in ctx.steps],
        "summary": summary,
        "exit_code": exit_code,
    }


def print_text(payload: dict[str, Any]) -> None:
    print("PatchWeaver deployment preflight")
    print(f"Project root: {payload['project_root']}")
    print(f"Mode: {'dry-run' if payload['dry_run'] else 'print-plan' if payload['print_plan'] else 'execute'}")
    print("\nChecks:")
    for item in payload["checks"]:
        line = f"  [{item['status']}] {item['name']}: {item['detail']}"
        print(line)
        if item.get("hint"):
            print(f"      hint: {item['hint']}")
    print("\nPlan:")
    for step in payload["steps"]:
        if step["skipped"]:
            print(f"  [skip] {step['name']}: {step.get('reason') or 'skipped'}")
            continue
        command = " ".join(step["command"] or [])
        result = f" returncode={step['returncode']}" if step.get("returncode") is not None else ""
        print(f"  [{step['action']}] {step['name']}: {command}{result}")
    summary = payload["summary"]
    print(f"\nSummary: ok={summary['ok']} warn={summary['warn']} error={summary['error']}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.print_plan:
        args.dry_run = True
    project_root = resolve_project_root(args.project_root)
    ctx = Context(
        project_root=project_root,
        config_path=project_root / "config" / "build.yaml",
        target_kernel=args.target_kernel,
        dry_run=args.dry_run,
        json_output=args.json,
        print_plan=args.print_plan,
        skip_install=args.skip_install,
        skip_doctor=args.skip_doctor,
        with_db=args.with_db,
    )

    build_config = load_build_config(ctx.config_path)
    check_python(ctx)
    check_project(ctx)
    check_kernel(ctx)
    check_kpatch(ctx, build_config)
    check_build_paths(ctx, build_config)
    build_plan(ctx)
    exit_code = execute_plan(ctx)
    payload = summarize(ctx, exit_code)
    if ctx.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(payload)
    if exit_code:
        return exit_code
    return 1 if payload["summary"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
