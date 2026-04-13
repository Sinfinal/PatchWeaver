"""PatchWeaver 命令行入口。"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import sys
from pathlib import Path
from shutil import get_terminal_size
from textwrap import wrap
from typing import Annotated, Any

import click
import typer
from typer.core import TyperGroup

from patchweaver import __version__
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.config.loader import load_build_config, load_logging_config, load_prompts_config, load_skills_config, load_verify_config
from patchweaver.config.resolver import resolve_runtime
from patchweaver.coordinator.task_runner import TaskRunner
from patchweaver.harness.attempt_engine import AttemptEngine
from patchweaver.harness.workspace_guard import WorkspaceGuard
from patchweaver.models.task import TaskContext
from patchweaver.storage.artifact_repo import ArtifactRepository
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.sqlite import initialize_sqlite_db
from patchweaver.storage.task_repo import TaskRepository

class PatchWeaverHelpGroup(TyperGroup):
    """统一渲染更适合人读的帮助页。"""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """输出统一风格的帮助页。"""
        # 统一接管帮助页渲染，避免根命令和子命令出现两套风格。
        formatter.write(_render_help_page(ctx, self))


app = typer.Typer(
    name="patchweaver",
    cls=PatchWeaverHelpGroup,
    no_args_is_help=True,
    help="PatchWeaver 命令行工具。",
)
db_app = typer.Typer(
    name="db",
    cls=PatchWeaverHelpGroup,
    no_args_is_help=True,
    help="SQLite 相关命令。",
)
app.add_typer(db_app, name="db")


def _load_runtime(profile: str | None = None, db_path: str | None = None, max_attempts: int | None = None):
    """解析当前命令实际生效的运行时配置。"""
    try:
        # 启动阶段统一走这里解析运行参数，命令层不用重复处理配置优先级。
        return resolve_runtime(
            profile_name=profile,
            cli_database_path=db_path,
            cli_max_attempts=max_attempts,
        )
    except Exception as exc:  # pragma: no cover - 启动期异常分支
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


def _placeholder(command_name: str) -> None:
    """输出占位命令的统一提示。"""
    typer.echo(f"[待实现] `{command_name}` 命令骨架已就绪，当前版本暂未实现具体逻辑。")


def _resolve_project_path(project_root: Path, raw_path: str) -> Path:
    """把配置路径转换为项目内可用的绝对路径。"""
    # 配置里允许写相对路径，统一按项目根目录展开。
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else (project_root / candidate)


def _should_use_color(*, plain: bool = False, no_color: bool = False) -> bool:
    """判断当前输出是否启用颜色。"""
    # 带 --plain / --no-color 或外部显式关闭颜色时，直接走纯文本输出。
    if plain or no_color or os.getenv("NO_COLOR") == "1":
        return False
    return sys.stdout.isatty()


def _emit_json(payload: dict[str, Any]) -> None:
    """输出结构化 JSON。"""
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _check_item(
    *,
    category: str,
    name: str,
    label: str,
    ok: bool,
    detail: str,
    failed_status: str = "warn",
) -> dict[str, Any]:
    """构造单条检查结果。"""
    # doctor 里的检查项统一走这一层，保证文本输出和 JSON 输出使用同一份状态语义。
    status = "ok" if ok else failed_status
    return {
        "category": category,
        "name": name,
        "label": label,
        "ok": ok,
        "status": status,
        "detail": detail,
    }


def _project_skill_dirs(project_root: Path, skills_config: Any) -> dict[str, Path]:
    """计算项目级 skill 的目录位置。"""
    project_root_dir = _resolve_project_path(project_root, skills_config.skill_dirs.project)
    # 首版只为已启用 skill 建项目级目录，避免一开始铺太多空目录。
    return {
        skill_name: (project_root_dir / skill_name).resolve()
        for skill_name in skills_config.enabled_skills
    }


def _manifest_template_specs(project_root: Path, runtime: Any, skills_config: Any) -> dict[Path, str]:
    """生成初始化阶段需要写入的模板内容。"""
    allowed_tags = skills_config.allowed_skill_tags or ["contest", "core"]
    # 这些模板属于最小 onboard 产物，先把结构和字段约定冻结下来。
    specs: dict[Path, str] = {
        runtime.manifest_dir / "bootstrap_manifest.template.json": json.dumps(
            {
                "manifest_type": "bootstrap_manifest",
                "version": "0.1.0",
                "fragments": [
                    {"name": "system", "source": "prompts/system", "required": True},
                    {"name": "bootstrap", "source": "prompts/bootstrap", "required": False},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        runtime.manifest_dir / "failover_record.template.json": json.dumps(
            {
                "record_type": "failover_record",
                "version": "0.1.0",
                "allowed_switches": ["模型档位", "提示档位", "超时", "并发预算"],
                "note": "窄状态 failover 只能调整调用参数，不能直接修改任务状态或工作区。",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }

    for skill_name, skill_dir in _project_skill_dirs(project_root, skills_config).items():
        # skill manifest 先给出最小骨架，后面逐步替换成真实入口和约束。
        specs[skill_dir / "manifest.yaml"] = "\n".join(
            [
                f"name: {skill_name}",
                "version: 0.1.0",
                "enabled: false",
                "visibility: project",
                "tags:",
                *[f"  - {tag}" for tag in allowed_tags],
                "entry:",
                "  kind: placeholder",
                f"  stage: {skill_name}",
                f"description: {skill_name} 阶段能力包模板，后续补充实际实现。",
                "",
            ]
        )

    return specs


def _ensure_template_file(path: Path, content: str) -> bool:
    """在目标文件不存在时写入模板。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 已存在的模板不覆盖，避免 init 把手工修改过的内容冲掉。
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _command_help(command: click.Command) -> str:
    """读取命令的短帮助说明。"""
    return command.get_short_help_str(limit=80) or "暂无说明。"


def _help_width() -> int:
    """根据终端宽度计算帮助页的展示宽度。"""
    return max(76, min(get_terminal_size((96, 30)).columns, 100))


def _style_help(text: str, *, fg: str | None = None, bold: bool = False, dim: bool = False) -> str:
    """为帮助页文本附加简单样式。"""
    if not _should_use_color():
        return text
    return click.style(text, fg=fg, bold=bold, dim=dim)


def _help_rule(char: str = "=") -> str:
    """生成帮助页使用的分隔线。"""
    return char * _help_width()


def _help_section(title: str) -> str:
    """渲染帮助页的小节标题。"""
    return _style_help(title, fg="bright_blue", bold=True)


def _help_item(name: str, description: str, *, indent: int = 2, width: int = 16, color: str = "bright_blue") -> str:
    """生成单行帮助项。"""
    padded = name.ljust(width)
    return f"{' ' * indent}{_style_help(padded, fg=color, bold=True)} {description}"


def _wrap_help_entry(name: str, description: str, *, width: int = 22, color: str = "bright_blue") -> list[str]:
    """生成可换行的帮助项。"""
    # 长描述按终端宽度折行，避免帮助页在窄终端里挤成一团。
    total_width = _help_width()
    content_width = max(30, total_width - width - 3)
    wrapped = wrap(description, width=content_width) or [description]
    lines = [f"  {_style_help(name.ljust(width), fg=color, bold=True)} {wrapped[0]}"]
    lines.extend(f"  {' ' * width} {line}" for line in wrapped[1:])
    return lines


def _render_root_help(ctx: click.Context, command: click.Command) -> str:
    """渲染根命令帮助页。"""
    program_name = command.name or "patchweaver"
    commands = {name: command.get_command(ctx, name) for name in command.list_commands(ctx)}
    task_commands = ["create", "analyze", "run", "report", "replay"]
    env_commands = ["init", "doctor", "paths", "init-db", "db", "serve-api", "status", "version"]
    lines = [
        f"{_style_help('PatchWeaver', fg='bright_blue', bold=True)} {_style_help(__version__, fg='bright_yellow', bold=True)}"
        " — 从上游 CVE 修复补丁到 livepatch 构建尝试的最小工程壳。",
        "",
        f"{_style_help('Usage:', fg='bright_blue', bold=True)} {program_name} [options] [command]",
        "",
        _help_section("Options:"),
    ]

    lines.extend(_wrap_help_entry("--help", "显示帮助页。", color="bright_yellow"))
    lines.extend(_wrap_help_entry("--install-completion", "为当前 shell 安装命令补全。", color="bright_yellow"))
    lines.extend(_wrap_help_entry("--show-completion", "输出补全脚本，便于自行集成。", color="bright_yellow"))
    lines.extend(_wrap_help_entry("--no-color", "关闭 ANSI 颜色。doctor 命令也支持该输出模式。", color="bright_green"))
    lines.extend(_wrap_help_entry("--json", "部分命令支持结构化输出，适合脚本和测试。", color="bright_green"))
    lines.extend(_wrap_help_entry("--plain", "部分命令支持纯文本输出，适合日志采集或远程终端。", color="bright_green"))

    lines.extend(
        [
            "",
            _help_section("Commands:"),
            "  Hint: 带 * 的命令包含子命令。可运行 <command> --help 查看详情。",
        ]
    )

    for name in env_commands:
        child = commands.get(name)
        if child is None:
            continue
        label = f"{name} *" if name == "db" else name
        lines.extend(_wrap_help_entry(label, _command_help(child)))

    for name in task_commands:
        child = commands.get(name)
        if child is not None:
            lines.extend(_wrap_help_entry(name, _command_help(child)))

    lines.extend(
        [
            "",
            _help_section("Examples:"),
        ]
    )
    lines.extend(_wrap_help_entry("patchweaver doctor --json", "输出结构化环境检查结果。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver init --with-db", "初始化最小工程目录，并同时建立 SQLite 数据库。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver paths --json", "输出当前生效的路径、运行时和 manifest 目录。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver serve-api --reload", "启动 FastAPI 接口，供 Web 控制台开发调试。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver db path", "查看当前配置解析出来的数据库路径。", width=30, color="bright_green"))
    lines.extend(
        [
            "",
            f"{_style_help('Docs:', fg='bright_blue', bold=True)} docs/PatchWeaver-总方案与创新设计总文档.md",
        ]
    )
    return "\n".join(lines)


def _render_db_help(command: click.Command) -> str:
    """渲染 db 子命令帮助页。"""
    ctx = click.Context(command)
    lines = [
        f"{_style_help('PatchWeaver / db', fg='bright_blue', bold=True)}"
        " — SQLite 与状态索引相关命令。",
        "",
        f"{_style_help('Usage:', fg='bright_blue', bold=True)} patchweaver db [options] [command]",
        "",
        _help_section("Options:"),
    ]

    lines.extend(_wrap_help_entry("--help", "显示帮助页。", color="bright_yellow"))
    lines.extend(_wrap_help_entry("--json", "部分子命令支持结构化输出，适合脚本调用。", color="bright_green"))

    lines.extend(
        [
            "",
            _help_section("Commands:"),
        ]
    )
    for name in command.list_commands(ctx):
        child = command.get_command(ctx, name)
        if child is not None:
            lines.extend(_wrap_help_entry(name, _command_help(child)))

    lines.extend(
        [
            "",
            _help_section("Examples:"),
        ]
    )
    lines.extend(_wrap_help_entry("patchweaver db init", "初始化 SQLite 数据库并写入基础 schema。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver db path --json", "输出当前生效的数据库路径，便于外部脚本读取。", width=30, color="bright_green"))
    lines.extend(
        [
            "",
            f"{_style_help('Docs:', fg='bright_blue', bold=True)} docs/PatchWeaver-总方案与创新设计总文档.md",
        ]
    )
    return "\n".join(lines)


def _render_help_page(ctx: click.Context, command: click.Command) -> str:
    """根据命令类型选择帮助页模板。"""
    if command.name == "db":
        return _render_db_help(command)
    return _render_root_help(ctx, command)


def _print_status(label: str, ok: bool, detail: str, *, use_color: bool = True) -> None:
    """输出一条环境检查结果。"""
    prefix = "[正常]" if ok else "[提示]"
    color = typer.colors.GREEN if ok else typer.colors.YELLOW
    message = f"{prefix} {label}: {detail}"
    if use_color:
        typer.secho(message, fg=color)
    else:
        typer.echo(message)


def _runtime_payload(runtime: Any) -> dict[str, Any]:
    """整理运行时信息，供文本和 JSON 复用。"""
    return {
        "project_root": str(runtime.project_root),
        "config_dir": str(runtime.config_dir),
        "workspace_root": str(runtime.workspace_root),
        "database_path": str(runtime.database_path),
        "manifest_dir": str(runtime.manifest_dir),
        "default_kernel": runtime.default_kernel,
        "max_attempts": runtime.max_attempts,
        "parallel_read_limit": runtime.parallel_read_limit,
        "write_lock_scope": runtime.write_lock_scope,
        "trace_mode": runtime.trace_mode,
        "profile_name": runtime.profile_name,
        "enable_narrow_failover": runtime.enable_narrow_failover,
        "enable_read_parallel": runtime.enable_read_parallel,
    }


def _task_payload(task: TaskContext) -> dict[str, Any]:
    """把任务对象整理成统一输出结构。"""

    return {
        "task_id": task.task_id,
        "cve_id": task.cve_id,
        "target_kernel": task.target_kernel,
        "status": task.status,
        "current_attempt": task.current_attempt,
        "max_attempts": task.max_attempts,
        "workspace_dir": str(task.workspace_dir),
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _build_task_runner(runtime: Any) -> TaskRunner:
    """按当前运行时配置创建任务编排器。"""

    build_config = load_build_config(runtime.project_root)
    verify_config = load_verify_config(runtime.project_root)
    prompts_config = load_prompts_config(runtime.project_root)
    return TaskRunner(
        runtime=runtime,
        build_config=build_config,
        verify_config=verify_config,
        prompts_config=prompts_config,
    )


def _doctor_payload(runtime: Any, build_config: Any, logging_config: Any, skills_config: Any, prompts_config: Any) -> dict[str, Any]:
    """组装 doctor 命令的完整检查结果。"""
    checks: list[dict[str, Any]] = []

    # 先把几块固定上下文整理出来，后面的检查项都直接引用这份快照。
    skill_roots = {
        "project": str(_resolve_project_path(runtime.project_root, skills_config.skill_dirs.project).resolve()),
        "shared": str(_resolve_project_path(runtime.project_root, skills_config.skill_dirs.shared).resolve()),
        "builtin": str(_resolve_project_path(runtime.project_root, skills_config.skill_dirs.builtin).resolve()),
    }
    bootstrap_dirs = [
        str(_resolve_project_path(runtime.project_root, raw_dir).resolve())
        for raw_dir in prompts_config.bootstrap_fragment_dirs
    ]
    build_env = BuildOrchestrator(build_config).probe_environment()
    build_env["default_kernel"] = runtime.default_kernel

    # Python 依赖放在最前面查，CLI 自己起不来的问题会最先暴露。
    required_modules = {
        "typer": "命令行框架",
        "pydantic": "配置与模型校验",
        "yaml": "YAML 解析",
        "jinja2": "模板渲染",
        "unidiff": "补丁解析",
        "rich": "终端输出",
        "paramiko": "SSH 构建通道",
    }
    for module_name, description in required_modules.items():
        ok = importlib.util.find_spec(module_name) is not None
        checks.append(_check_item(category="python_module", name=module_name, label=f"Python 模块 `{module_name}`", ok=ok, detail=description))

    config_files = [
        "system.yaml",
        "profiles.yaml",
        "build.yaml",
        "verify.yaml",
        "skills.yaml",
        "prompts.yaml",
        "rules.yaml",
        "logging.yaml",
    ]
    for filename in config_files:
        config_path = runtime.config_dir / filename
        checks.append(_check_item(category="config_file", name=filename, label=f"配置文件 `{filename}`", ok=config_path.exists(), detail=str(config_path)))

    # 构建环境单独列出来，后面如果 doctor 报黄，基本一眼就能看出是环境问题还是代码问题。
    checks.append(
        _check_item(
            category="build_backend",
            name="build_backend",
            label="构建后端",
            ok=True,
            detail=build_env["backend"],
        )
    )

    if build_env["backend"] == "ssh":
        checks.extend(
            [
                _check_item(
                    category="build_env",
                    name="remote_host",
                    label="远端构建主机",
                    ok=bool(build_env.get("remote_host")),
                    detail=build_env.get("host_label") or "未配置",
                    failed_status="error",
                ),
                _check_item(
                    category="build_env",
                    name="remote_password_env",
                    label="远端密码环境变量",
                    ok=bool(build_env.get("password_present")),
                    detail=build_env.get("remote_password_env") or "未配置",
                    failed_status="error",
                ),
                _check_item(
                    category="build_env",
                    name="remote_connection",
                    label="远端连接",
                    ok=bool(build_env.get("reachable")),
                    detail=build_env.get("error") or "连接正常",
                    failed_status="error",
                ),
                _check_item(
                    category="external_command",
                    name=build_config.kpatch_build_cmd,
                    label=f"远端构建命令 `{build_config.kpatch_build_cmd}`",
                    ok=bool(build_env.get("builder_ok")),
                    detail=build_env.get("builder_path") or "远端未找到",
                    failed_status="error",
                ),
                _check_item(
                    category="build_env",
                    name="selected_source_dir",
                    label="远端源码目录",
                    ok=bool(build_env.get("selected_source_ok")),
                    detail=build_env.get("selected_source_dir") or "未找到可用目录",
                    failed_status="error",
                ),
                _check_item(
                    category="build_env",
                    name="config_path",
                    label="远端 .config",
                    ok=bool(build_env.get("config_ok")),
                    detail=build_env.get("config_path") or "未找到",
                    failed_status="error",
                ),
                _check_item(
                    category="build_env",
                    name="vmlinux_path",
                    label="远端 vmlinux",
                    ok=bool(build_env.get("vmlinux_ok")),
                    detail=build_env.get("vmlinux_path") or "未配置",
                    failed_status="error",
                ),
            ]
        )
    else:
        checks.extend(
            [
                _check_item(
                    category="external_command",
                    name=build_config.kpatch_build_cmd,
                    label=f"构建命令 `{build_config.kpatch_build_cmd}`",
                    ok=bool(build_env.get("builder_ok")),
                    detail=build_env.get("builder_path") or "当前 PATH 中未找到",
                    failed_status="error",
                ),
                _check_item(
                    category="build_env",
                    name="selected_source_dir",
                    label="内核源码目录",
                    ok=bool(build_env.get("selected_source_ok")),
                    detail=build_env.get("selected_source_dir") or "未找到可用目录",
                    failed_status="error",
                ),
                _check_item(
                    category="build_env",
                    name="config_path",
                    label="内核 .config",
                    ok=bool(build_env.get("config_ok")),
                    detail=build_env.get("config_path") or "未找到",
                    failed_status="error",
                ),
                _check_item(
                    category="build_env",
                    name="vmlinux_path",
                    label="vmlinux 路径",
                    ok=bool(build_env.get("vmlinux_ok")),
                    detail=build_env.get("vmlinux_path") or "未配置",
                    failed_status="error",
                ),
            ]
        )

    for source_name, raw_path in skill_roots.items():
        skill_root = Path(raw_path)
        checks.append(
            _check_item(
                category="skill_root",
                name=source_name,
                label=f"Skill 根目录 `{source_name}`",
                ok=skill_root.exists(),
                detail=str(skill_root),
            )
        )

    if skills_config.require_manifest:
        # 要求 manifest 时，项目级 skill 必须至少具备可检查的最小入口描述。
        for skill_name, skill_dir in _project_skill_dirs(runtime.project_root, skills_config).items():
            manifest_path = skill_dir / "manifest.yaml"
            checks.append(
                _check_item(
                    category="skill_manifest",
                    name=skill_name,
                    label=f"Skill Manifest `{skill_name}`",
                    ok=manifest_path.exists(),
                    detail=str(manifest_path),
                )
            )

    # bootstrap 目录和 contracts 目录分开检查，方便排查 prompt 体系是不是缺文件。
    for bootstrap_dir in bootstrap_dirs:
        bootstrap_path = Path(bootstrap_dir)
        checks.append(
            _check_item(
                category="bootstrap_dir",
                name=bootstrap_path.name,
                label=f"Bootstrap 目录 `{bootstrap_path.name}`",
                ok=bootstrap_path.exists(),
                detail=str(bootstrap_path),
            )
        )

    prompt_contract_dir = (runtime.project_root / "prompts" / "contracts").resolve()
    checks.append(
        _check_item(
            category="prompt_contract",
            name="contracts",
            label="Prompt Contracts 目录",
            ok=prompt_contract_dir.exists(),
            detail=str(prompt_contract_dir),
        )
    )

    checks.append(
        _check_item(
            category="filesystem",
            name="manifest_dir",
            label="Manifest 目录",
            ok=runtime.manifest_dir.exists(),
            detail=str(runtime.manifest_dir),
        )
    )

    for template_path in _manifest_template_specs(runtime.project_root, runtime, skills_config):
        # doctor 只检查运行期 manifest 目录下的模板文件，项目 skill manifest 走上面的专项检查。
        if template_path.parent != runtime.manifest_dir:
            continue
        checks.append(
            _check_item(
                category="manifest_template",
                name=template_path.name,
                label=f"Manifest 模板 `{template_path.name}`",
                ok=template_path.exists(),
                detail=str(template_path),
            )
        )

    # 最后一段再看文件系统状态，这里基本能判断当前环境能不能继续跑任务。
    log_path = _resolve_project_path(runtime.project_root, logging_config.file_path)
    jsonl_path = _resolve_project_path(runtime.project_root, logging_config.jsonl_path)
    checks.extend(
        [
            _check_item(category="filesystem", name="log_dir", label="日志目录", ok=log_path.parent.exists(), detail=str(log_path.parent)),
            _check_item(category="filesystem", name="jsonl_dir", label="JSONL 目录", ok=jsonl_path.parent.exists(), detail=str(jsonl_path.parent)),
            _check_item(category="filesystem", name="workspace_root", label="工作区目录", ok=runtime.workspace_root.exists(), detail=str(runtime.workspace_root)),
            _check_item(category="filesystem", name="sqlite_file", label="SQLite 文件", ok=runtime.database_path.exists(), detail=str(runtime.database_path)),
        ]
    )

    # 汇总值直接从检查项回算，避免文本输出和 JSON 输出统计不一致。
    summary = {
        "total": len(checks),
        "ok": sum(1 for item in checks if item["status"] == "ok"),
        "warn": sum(1 for item in checks if item["status"] == "warn"),
        "error": sum(1 for item in checks if item["status"] == "error"),
    }

    return {
        "command": "doctor",
        "runtime": {
            **_runtime_payload(runtime),
            "python_version": platform.python_version(),
            "skill_source_priority": skills_config.skill_source_priority,
        },
        "skill_roots": skill_roots,
        "bootstrap_dirs": bootstrap_dirs,
        "build_env": build_env,
        "checks": checks,
        "summary": summary,
    }

@app.command("version")
def version(
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """显示当前版本。"""

    if json_output:
        _emit_json({"name": "PatchWeaver", "version": __version__})
        return

    typer.echo(f"PatchWeaver {__version__}")


@app.command("paths")
def paths(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    max_attempts: Annotated[int | None, typer.Option("--max-attempts", help="覆盖最大尝试次数。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """打印当前生效的运行路径和关键配置。"""

    runtime = _load_runtime(profile=profile, db_path=db_path, max_attempts=max_attempts)
    payload = _runtime_payload(runtime)

    if json_output:
        _emit_json({"command": "paths", **payload})
        return

    typer.echo(f"项目根目录: {payload['project_root']}")
    typer.echo(f"配置目录: {payload['config_dir']}")
    typer.echo(f"工作区根目录: {payload['workspace_root']}")
    typer.echo(f"数据库路径: {payload['database_path']}")
    typer.echo(f"Manifest 目录: {payload['manifest_dir']}")
    typer.echo(f"默认内核版本: {payload['default_kernel']}")
    typer.echo(f"最大尝试次数: {payload['max_attempts']}")
    typer.echo(f"只读并发上限: {payload['parallel_read_limit']}")
    typer.echo(f"写入独占粒度: {payload['write_lock_scope']}")
    typer.echo(f"Trace 模式: {payload['trace_mode']}")
    typer.echo(f"窄状态 Failover: {payload['enable_narrow_failover']}")


@app.command("init")
def init_command(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    max_attempts: Annotated[int | None, typer.Option("--max-attempts", help="覆盖最大尝试次数。")] = None,
    with_db: Annotated[bool, typer.Option("--with-db", help="同时初始化 SQLite 数据库。")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """初始化最小运行目录。"""

    runtime = _load_runtime(profile=profile, db_path=db_path, max_attempts=max_attempts)
    logging_config = load_logging_config(runtime.project_root)
    skills_config = load_skills_config(runtime.project_root)
    prompts_config = load_prompts_config(runtime.project_root)
    # 把启动期会立即用到的目录一次建齐，避免后续命令各自补目录。
    paths_to_create = [
        runtime.data_dir,
        runtime.data_dir / "cache",
        runtime.data_dir / "logs",
        runtime.manifest_dir,
        runtime.data_dir / "traces",
        runtime.workspace_root,
        runtime.database_path.parent,
        _resolve_project_path(runtime.project_root, logging_config.file_path).parent,
        _resolve_project_path(runtime.project_root, logging_config.jsonl_path).parent,
        (runtime.project_root / "prompts" / "contracts").resolve(),
    ]
    paths_to_create.extend(
        _resolve_project_path(runtime.project_root, raw_dir).resolve()
        for raw_dir in prompts_config.bootstrap_fragment_dirs
    )
    paths_to_create.extend(
        _resolve_project_path(runtime.project_root, raw_dir).resolve()
        for raw_dir in skills_config.skill_dirs.model_dump().values()
    )
    # 项目级 skill 目录按 enabled_skills 展开，和当前启用集合保持一致。
    paths_to_create.extend(_project_skill_dirs(runtime.project_root, skills_config).values())

    created: list[Path] = []
    for path in paths_to_create:
        path.mkdir(parents=True, exist_ok=True)
        created.append(path.resolve())

    created_paths = [str(path) for path in sorted(set(created))]
    created_manifest_templates: list[str] = []
    # 模板和目录分开处理，方便区分“目录已存在”和“首次生成模板”的初始化结果。
    for template_path, content in _manifest_template_specs(runtime.project_root, runtime, skills_config).items():
        if _ensure_template_file(template_path, content):
            created_manifest_templates.append(str(template_path.resolve()))

    final_path: Path | None = None
    if with_db:
        final_path = initialize_sqlite_db(runtime.database_path)

    if json_output:
        _emit_json(
            {
                "command": "init",
                "created_paths": created_paths,
                "manifest_templates": created_manifest_templates,
                "database_initialized": with_db,
                "database_path": str(final_path or runtime.database_path),
                "next_steps": [
                    "patchweaver doctor",
                    "patchweaver paths --json",
                    "补充 prompts/bootstrap 和 skills/project 下的实际模板与 manifest。",
                ],
                "status": "ok",
            }
        )
        return

    typer.echo("已完成最小工程初始化：")
    for path in created_paths:
        typer.echo(f"  - {path}")

    if created_manifest_templates:
        typer.echo("已初始化 Manifest 模板：")
        for path in created_manifest_templates:
            typer.echo(f"  - {path}")

    if with_db:
        typer.echo(f"已初始化 SQLite 数据库：{final_path}")

    typer.echo("下一步建议：")
    typer.echo("  1. patchweaver doctor")
    typer.echo("  2. patchweaver paths --json")
    typer.echo("  3. 补充 prompts/bootstrap 和 skills/project 下的实际模板与 manifest。")


@app.command("doctor")
def doctor(
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
    plain: Annotated[bool, typer.Option("--plain", help="强制使用纯文本输出。")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="关闭 ANSI 颜色。")] = False,
) -> None:
    """执行本地环境自检。"""

    runtime = _load_runtime()
    build_config = load_build_config(runtime.project_root)
    logging_config = load_logging_config(runtime.project_root)
    skills_config = load_skills_config(runtime.project_root)
    prompts_config = load_prompts_config(runtime.project_root)
    payload = _doctor_payload(runtime, build_config, logging_config, skills_config, prompts_config)

    # JSON 模式优先给脚本消费，不混入任何说明性文本。
    if json_output:
        _emit_json(payload)
        return

    use_color = _should_use_color(plain=plain, no_color=no_color)
    if use_color:
        typer.secho("PatchWeaver 环境检查", fg=typer.colors.YELLOW, bold=True)
    else:
        typer.echo("PatchWeaver 环境检查")
    typer.echo(f"项目根目录: {payload['runtime']['project_root']}")
    typer.echo(f"数据库路径: {payload['runtime']['database_path']}")
    typer.echo(f"Manifest 目录: {payload['runtime']['manifest_dir']}")
    typer.echo(f"Python 版本: {payload['runtime']['python_version']}")

    for item in payload["checks"]:
        _print_status(item["label"], item["ok"], item["detail"], use_color=use_color)

    # 最后一行保留汇总，便于快速判断当前环境是“可继续开发”还是“先补环境”。
    typer.echo(
        f"汇总: 正常 {payload['summary']['ok']} / 提示 {payload['summary']['warn']} / 错误 {payload['summary']['error']}"
    )


@app.command("create")
def create(
    cve: Annotated[str, typer.Option("--cve", help="指定要处理的 CVE ID。")] = ...,
    kernel: Annotated[str | None, typer.Option("--kernel", help="覆盖目标内核版本。")] = None,
    task_id: Annotated[str | None, typer.Option("--task-id", help="手工指定任务编号。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """创建任务并初始化工作区骨架。"""

    runtime = _load_runtime()
    task_repo = TaskRepository(runtime.database_path)
    attempt_repo = AttemptRepository(runtime.database_path)
    artifact_repo = ArtifactRepository(runtime.database_path)

    final_task_id = task_id or task_repo.next_task_id()
    if task_repo.task_exists(final_task_id):
        typer.secho(f"错误: 任务已存在：{final_task_id}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    task = TaskContext(
        task_id=final_task_id,
        cve_id=cve,
        target_kernel=kernel or runtime.default_kernel,
        status="created",
        max_attempts=runtime.max_attempts,
        current_attempt=0,
        workspace_dir=(runtime.workspace_root / final_task_id).resolve(),
    )

    workspace_guard = WorkspaceGuard(runtime.workspace_root)
    task_dir = workspace_guard.create_task_workspace(task)
    workspace_guard.create_attempt_workspace(task_dir, 1)
    task_repo.create_task(task)

    initial_state = AttemptEngine().create_initial_state(task_id=task.task_id, max_attempts=task.max_attempts)
    attempt_repo.save_attempt_state(initial_state)
    artifact_repo.add_artifact(
        task_id=task.task_id,
        artifact_type="task_context",
        artifact_path=task_dir / "task_context.json",
        metadata={"kind": "workspace_snapshot"},
    )

    payload = {
        "command": "create",
        "task": _task_payload(task),
        "prepared_attempt_dir": str(task_dir / "attempts" / "001"),
        "status": "ok",
    }
    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"已创建任务: {task.task_id}")
    typer.echo(f"CVE 编号: {task.cve_id}")
    typer.echo(f"目标内核: {task.target_kernel}")
    typer.echo(f"工作区目录: {task.workspace_dir}")
    typer.echo(f"首轮尝试目录: {task_dir / 'attempts' / '001'}")


@app.command("run")
def run(
    task: Annotated[str, typer.Option("--task", help="指定任务编号。")] = ...,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """执行最小单轮尝试。"""

    runtime = _load_runtime()
    runner = _build_task_runner(runtime)
    try:
        payload = runner.run_task(task)
    except Exception as exc:
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"任务编号: {payload['task_id']}")
    typer.echo(f"尝试编号: {payload['attempt_id']}")
    typer.echo(f"执行结果: {payload['status']}")
    typer.echo(f"失败类型: {payload['failure_type']}")
    typer.echo(f"构建日志: {payload['build_log_path']}")
    typer.echo(f"Trace 路径: {payload['trace_path']}")


@app.command("status")
def status(
    task: Annotated[str | None, typer.Option("--task", help="指定任务编号。")] = None,
    limit: Annotated[int, typer.Option("--limit", help="限制返回的任务条数。")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """查看任务状态。"""

    runtime = _load_runtime()
    task_repo = TaskRepository(runtime.database_path)

    if task:
        task_context = task_repo.get_task(task)
        if task_context is None:
            typer.secho(f"错误: 未找到任务：{task}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1)
        payload = {"command": "status", "task": _task_payload(task_context)}
        if json_output:
            _emit_json(payload)
            return
        typer.echo(f"任务编号: {task_context.task_id}")
        typer.echo(f"CVE 编号: {task_context.cve_id}")
        typer.echo(f"目标内核: {task_context.target_kernel}")
        typer.echo(f"当前状态: {task_context.status}")
        typer.echo(f"当前尝试轮: {task_context.current_attempt}/{task_context.max_attempts}")
        typer.echo(f"工作区目录: {task_context.workspace_dir}")
        return

    tasks = task_repo.list_tasks(limit=limit)
    payload = {"command": "status", "tasks": [_task_payload(item) for item in tasks]}
    if json_output:
        _emit_json(payload)
        return

    if not tasks:
        typer.echo("当前还没有任务记录。")
        return

    typer.echo("最近任务：")
    for item in tasks:
        typer.echo(f"  - {item.task_id} | {item.cve_id} | {item.status} | {item.workspace_dir}")


@app.command("analyze")
def analyze(
    task: Annotated[str, typer.Option("--task", help="指定任务编号。")] = ...,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """执行最小分析链路。"""

    runtime = _load_runtime()
    runner = _build_task_runner(runtime)
    try:
        payload = runner.analyze_task(task)
    except Exception as exc:
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"任务编号: {payload['task_id']}")
    typer.echo(f"PatchBundle: {payload['patch_bundle_path']}")
    typer.echo(f"SemanticCard: {payload['semantic_card_path']}")
    typer.echo(f"ConstraintReport: {payload['constraint_report_path']}")
    typer.echo(f"Bootstrap Manifest: {payload['bootstrap_manifest_path']}")


@app.command("report")
def report(
    task: Annotated[str, typer.Option("--task", help="指定任务编号。")] = ...,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """生成任务报告。"""

    runtime = _load_runtime()
    runner = _build_task_runner(runtime)
    try:
        payload = runner.build_report(task)
    except Exception as exc:
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"任务编号: {payload['task_id']}")
    typer.echo(f"JSON 报告: {payload['report_json']}")
    typer.echo(f"Markdown 报告: {payload['report_md']}")


@app.command("replay")
def replay(
    task: Annotated[str, typer.Option("--task", help="指定任务编号。")] = ...,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """查看最近一轮回放信息。"""

    runtime = _load_runtime()
    runner = _build_task_runner(runtime)
    try:
        payload = runner.replay_task(task)
    except Exception as exc:
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"任务编号: {payload['task_id']}")
    typer.echo(f"最近尝试: {payload['latest_attempt_id']}")
    typer.echo(f"尝试结果: {payload['latest_attempt_status']}")
    typer.echo(f"Trace 路径: {payload['trace_path']}")
    typer.echo(f"报告路径: {payload['report_path']}")


@app.command("init-db")
def init_db(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """按当前生效配置初始化 SQLite 数据库。"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    final_path = initialize_sqlite_db(runtime.database_path)
    if json_output:
        _emit_json({"command": "init-db", "database_path": str(final_path), "status": "ok"})
        return
    typer.echo(f"已初始化 SQLite 数据库：{final_path}")


@app.command("serve-api")
def serve_api(
    host: Annotated[str, typer.Option("--host", help="指定 API 监听地址。")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="指定 API 监听端口。")] = 18080,
    reload: Annotated[bool, typer.Option("--reload", help="开发阶段开启自动重载。")] = False,
) -> None:
    """启动 Web 控制台后端接口。"""

    # API 服务默认直接复用当前仓库里的 patchweaver.api.app，不再单独维护第二套启动脚本。
    import uvicorn

    typer.echo(f"启动 PatchWeaver API: http://{host}:{port}")
    uvicorn.run("patchweaver.api.app:app", host=host, port=port, reload=reload)


@db_app.command("init")
def db_init(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """初始化 SQLite 数据库。"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    final_path = initialize_sqlite_db(runtime.database_path)
    if json_output:
        _emit_json({"command": "db init", "database_path": str(final_path), "status": "ok"})
        return
    typer.echo(f"已初始化 SQLite 数据库：{final_path}")


@db_app.command("path")
def db_path(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """打印当前生效的 SQLite 路径。"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    if json_output:
        _emit_json({"command": "db path", "database_path": str(runtime.database_path)})
        return
    typer.echo(runtime.database_path)


if __name__ == "__main__":
    app()
