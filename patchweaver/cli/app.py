"""PatchWeaver 命令行入口"""

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
from typer.core import TyperCommand, TyperGroup

from patchweaver import __version__
from patchweaver.api.service_manager import (
    DEFAULT_API_SERVICE_NAME,
    install_systemd_service,
    systemd_available,
    wait_for_api_ready,
)
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.builder.source_preparer import prepare_validation_source_tree
from patchweaver.config.loader import (
    load_build_config,
    load_logging_config,
    load_models_config,
    load_prompts_config,
    save_models_api_settings,
    load_skills_config,
    load_system_config,
    load_verify_config,
)
from patchweaver.config.resolver import load_effective_configs, resolve_runtime
from patchweaver.coordinator.task_runner import TaskRunner
from patchweaver.harness.evaluator import Evaluator
from patchweaver.harness.workspace_guard import WorkspaceGuard
from patchweaver.models.task import TaskContext
from patchweaver.observability.run_logger import RunLogger
from patchweaver.reporter.release_service import ReleaseService
from patchweaver.reporter.stats_writer import StatsWriter
from patchweaver.runtime_inspector import collect_machine_profile, resolve_task_binding
from patchweaver.storage.artifact_repo import ArtifactRepository
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.sqlite import initialize_sqlite_db
from patchweaver.storage.task_repo import TaskRepository
from patchweaver.task_creation_policy import build_duplicate_scope, build_duplicate_task_notice
from patchweaver.utils.path_policy import relativize_payload, to_project_relative

_RAW_TYPER_ECHO = typer.echo
_RAW_TYPER_SECHO = typer.secho


def _sanitize_cli_text(value: Any) -> Any:
    """统一收掉命令行展示里的中文句号"""

    if isinstance(value, str):
        return value.replace("。", "")
    return value


def _cli_echo(message: Any = None, *args: Any, **kwargs: Any) -> None:
    """统一处理人读输出"""

    _RAW_TYPER_ECHO(_sanitize_cli_text(message), *args, **kwargs)


def _cli_secho(message: Any = None, *args: Any, **kwargs: Any) -> None:
    """统一处理带样式的人读输出"""

    _RAW_TYPER_SECHO(_sanitize_cli_text(message), *args, **kwargs)


typer.echo = _cli_echo
typer.secho = _cli_secho


class PatchWeaverHelpGroup(TyperGroup):
    """统一渲染更适合人读的帮助页"""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """输出统一风格的帮助页"""
        # 统一接管帮助页渲染，避免根命令和子命令出现两套风格
        formatter.write(_render_help_page(ctx, self))


class PatchWeaverHelpCommand(TyperCommand):
    """统一渲染单命令帮助页"""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """输出单命令帮助页"""
        formatter.write(_render_command_help(ctx, self))


app = typer.Typer(
    name="patchweaver",
    cls=PatchWeaverHelpGroup,
    no_args_is_help=True,
    help="PatchWeaver 命令行工具。",
)
models_app = typer.Typer(
    name="models",
    cls=PatchWeaverHelpGroup,
    help="查看模型配置并维护 API Key",
)
db_app = typer.Typer(
    name="db",
    cls=PatchWeaverHelpGroup,
    no_args_is_help=True,
    help="SQLite 相关命令。",
)
app.add_typer(models_app, name="models")
app.add_typer(db_app, name="db")


def _load_runtime(profile: str | None = None, db_path: str | None = None, max_attempts: int | None = None):
    """解析当前命令实际生效的运行时配置"""
    try:
        # 启动阶段统一走这里解析运行参数，命令层不用重复处理配置优先级
        return resolve_runtime(
            profile_name=profile,
            cli_database_path=db_path,
            cli_max_attempts=max_attempts,
        )
    except Exception as exc:  # pragma: no cover - 启动期异常分支
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


def _placeholder(command_name: str) -> None:
    """输出占位命令的统一提示"""
    typer.echo(f"[待实现] `{command_name}` 命令骨架已就绪，当前版本暂未实现具体逻辑。")


def _resolve_project_path(project_root: Path, raw_path: str) -> Path:
    """把配置路径转换为项目内可用的绝对路径"""
    # 配置里允许写相对路径，统一按项目根目录展开
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else (project_root / candidate)


def _should_use_color(*, plain: bool = False, no_color: bool = False) -> bool:
    """判断当前输出是否启用颜色"""
    # 带 --plain / --no-color 或外部显式关闭颜色时，直接走纯文本输出
    if plain or no_color or os.getenv("NO_COLOR") == "1":
        return False
    return sys.stdout.isatty()


def _emit_json(payload: dict[str, Any]) -> None:
    """输出结构化 JSON"""
    _RAW_TYPER_ECHO(json.dumps(payload, ensure_ascii=False, indent=2))


def _write_json_snapshot(path: Path, payload: dict[str, Any]) -> Path:
    """把结构化结果额外落成一份 JSON 快照"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _project_path(project_root: Path, value: Path | str | None) -> str | None:
    """把路径统一转换成相对源码根目录的展示格式"""

    return to_project_relative(project_root, value)


def _project_payload(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """把命令输出中的项目内路径统一收敛为相对路径"""

    normalized = relativize_payload(payload, project_root)
    if not isinstance(normalized, dict):
        raise TypeError("CLI 输出必须是字典。")
    return normalized


def _api_key_source_label(source: str) -> str:
    """把 API Key 来源转换成人更容易读的文案"""

    labels = {
        "env": "环境变量",
        "config": "配置文件",
        "missing": "未配置",
    }
    return labels.get(source, source)


def _models_payload(models_config: Any) -> dict[str, Any]:
    """整理模型配置输出，并隐藏敏感字段"""

    payload = {
        "command": "models",
        "provider": models_config.provider,
        "endpoint_mode": models_config.endpoint_mode,
        "base_url": models_config.base_url,
        "topology": models_config.topology,
        "default_model": models_config.default_model,
        "development_model": models_config.development_model,
        "delivery_model": models_config.delivery_model,
        "fallback_model": models_config.fallback_model,
        "helper_models": models_config.helper_models,
        "helper_notes": models_config.helper_notes,
        "interaction_record_mode": models_config.interaction_record_mode,
        "interaction_jsonl_path": models_config.interaction_jsonl_path,
        "execution_boundaries": models_config.execution_boundaries,
    }
    payload.update(models_config.api_key_status())
    return payload


def _check_item(
    *,
    category: str,
    name: str,
    label: str,
    ok: bool,
    detail: str,
    failed_status: str = "warn",
) -> dict[str, Any]:
    """构造单条检查结果"""
    # doctor 里的检查项统一走这一层，保证文本输出和 JSON 输出使用同一份状态语义
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
    """计算项目级 skill 的目录位置"""
    project_root_dir = _resolve_project_path(project_root, skills_config.skill_dirs.project)
    # 首版只为已启用 skill 建项目级目录，避免一开始铺太多空目录
    return {
        skill_name: (project_root_dir / skill_name).resolve()
        for skill_name in skills_config.enabled_skills
    }


def _manifest_template_specs(project_root: Path, runtime: Any, skills_config: Any) -> dict[Path, str]:
    """生成初始化阶段需要写入的模板内容"""
    allowed_tags = skills_config.allowed_skill_tags or ["contest", "core"]
    # 这些模板属于最小 onboard 产物，先把结构和字段约定冻结下来
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
        # skill manifest 先给出最小骨架，后面逐步替换成真实入口和约束
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
    """在目标文件不存在时写入模板"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 已存在的模板不覆盖，避免 init 把手工修改过的内容冲掉
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _command_help(command: click.Command) -> str:
    """读取命令的短帮助说明"""
    return _sanitize_cli_text(command.get_short_help_str(limit=80) or "暂无说明")


def _help_width() -> int:
    """根据终端宽度计算帮助页的展示宽度"""
    return max(76, min(get_terminal_size((96, 30)).columns, 100))


def _style_help(text: str, *, fg: str | None = None, bold: bool = False, dim: bool = False) -> str:
    """为帮助页文本附加简单样式"""
    if not _should_use_color():
        return text
    return click.style(text, fg=fg, bold=bold, dim=dim)


def _help_rule(char: str = "=") -> str:
    """生成帮助页使用的分隔线"""
    return char * _help_width()


def _help_section(title: str) -> str:
    """渲染帮助页的小节标题"""
    return _style_help(title, fg="bright_blue", bold=True)


def _help_item(name: str, description: str, *, indent: int = 2, width: int = 16, color: str = "bright_blue") -> str:
    """生成单行帮助项"""
    padded = name.ljust(width)
    return f"{' ' * indent}{_style_help(padded, fg=color, bold=True)} {description}"


def _wrap_help_entry(name: str, description: str, *, width: int = 22, color: str = "bright_blue") -> list[str]:
    """生成可换行的帮助项"""
    # 长描述按终端宽度折行，避免帮助页在窄终端里挤成一团
    total_width = _help_width()
    content_width = max(30, total_width - width - 3)
    clean_name = _sanitize_cli_text(name)
    clean_description = _sanitize_cli_text(description)
    wrapped = wrap(clean_description, width=content_width) or [clean_description]
    lines = [f"  {_style_help(clean_name.ljust(width), fg=color, bold=True)} {wrapped[0]}"]
    lines.extend(f"  {' ' * width} {line}" for line in wrapped[1:])
    return lines


def _command_path(ctx: click.Context, command: click.Command | None = None) -> str:
    """按项目 CLI 规范拼出命令路径"""
    parts: list[str] = []
    cursor: click.Context | None = ctx
    while cursor is not None:
        name = cursor.command.name
        if name:
            parts.append(name)
        cursor = cursor.parent

    normalized = list(reversed(parts))
    if command is not None and (not normalized or normalized[-1] != command.name):
        normalized.append(command.name or "")
    if not normalized or normalized[0] != "patchweaver":
        normalized.insert(0, "patchweaver")
    return " ".join(part for part in normalized if part)


def _command_heading(command_path: str) -> str:
    """把命令路径转换成页头标题"""
    parts = command_path.split()
    if parts:
        parts[0] = "PatchWeaver"
    return " / ".join(parts)


def _normalize_help_description(text: str) -> str:
    """把 Click 默认帮助语句调整成项目内统一文案"""
    normalized = text.replace("Show this message and exit.", "显示帮助页。")
    normalized = normalized.replace("[default:", "[默认:")
    return _sanitize_cli_text(normalized)


def _command_option_entries(ctx: click.Context, command: click.Command) -> list[tuple[str, str]]:
    """提取命令帮助页里可展示的参数说明"""
    entries: list[tuple[str, str]] = []
    for param in command.get_params(ctx):
        help_record = param.get_help_record(ctx)
        if help_record is None:
            continue
        name, description = help_record
        entries.append((name, _normalize_help_description(description)))
    return entries


def _command_examples(command_path: str) -> list[tuple[str, str]]:
    """返回常用命令示例"""
    examples: dict[str, list[tuple[str, str]]] = {
        "patchweaver models": [
            (f"{command_path} --json", "查看当前模型配置、API Key 来源和脱敏状态"),
            ("patchweaver models set-api-key --value sk-xxxx", "把 API Key 写入 config/models.yaml"),
            ("patchweaver models set-api-key-env --name PATCHWEAVER_BAILIAN_API_KEY", "修改优先读取的环境变量名"),
            ("patchweaver models clear-api-key", "清空 config/models.yaml 里的明文 API Key"),
        ],
        "patchweaver serve-api": [
            (f"{command_path} --foreground", "以前台方式启动后端接口，便于本地联调。"),
            (f"{command_path} --host 0.0.0.0 --port 18084", "指定监听地址和端口。"),
        ],
        "patchweaver init": [
            (f"{command_path} --with-db", "初始化最小运行目录，并同时建立 SQLite 数据库。"),
        ],
        "patchweaver doctor": [
            (f"{command_path} --json", "输出结构化环境检查结果。"),
        ],
        "patchweaver paths": [
            (f"{command_path} --json", "输出当前生效的运行路径和关键配置。"),
        ],
        "patchweaver create": [
            (f"{command_path} --cve CVE-2024-1086", "创建任务并初始化工作区。"),
        ],
        "patchweaver run": [
            (f"{command_path} --task-id task-001", "执行最小单轮尝试。"),
        ],
        "patchweaver evaluate": [
            (f"{command_path} --fixture contest_samples", "按固定样例集输出阶段评测汇总。"),
        ],
        "patchweaver finalize": [
            (f"{command_path}", "生成 submission 目录和 final manifest。"),
        ],
        "patchweaver gate": [
            (f"{command_path}", "执行第四阶段最终门禁检查。"),
        ],
        "patchweaver install-api-service": [
            (f"{command_path} --host 0.0.0.0 --port 18084", "在 Linux 验证机上安装并启动 API 服务。"),
        ],
        "patchweaver prepare-build-tree": [
            (
                f"{command_path} --kernel-release 6.6.102-5.2.an23.x86_64 --warm-target vmlinux --warm-jobs 20",
                "准备完整源码树，并预热 vmlinux 构建缓存。",
            ),
        ],
        "patchweaver db init": [
            (f"{command_path}", "初始化 SQLite 数据库并写入基础 schema。"),
        ],
        "patchweaver db path": [
            (f"{command_path} --json", "输出当前生效的数据库路径。"),
        ],
    }
    return examples.get(command_path, [])


def _render_root_help(ctx: click.Context, command: click.Command) -> str:
    """渲染根命令帮助页"""
    program_name = command.name or "patchweaver"
    commands = {name: command.get_command(ctx, name) for name in command.list_commands(ctx)}
    task_commands = ["create", "analyze", "run", "report", "replay", "evaluate"]
    env_commands = [
        "init",
        "doctor",
        "paths",
        "models",
        "install-api-service",
        "prepare-build-tree",
        "finalize",
        "gate",
        "init-db",
        "db",
        "serve-api",
        "status",
        "version",
    ]
    # 根帮助页按“环境准备”和“任务链路”分组展示
    # 这样第一次接触项目的人更容易按顺序找到命令
    lines = [
        f"{_style_help('PatchWeaver', fg='bright_blue', bold=True)} {_style_help(__version__, fg='bright_yellow', bold=True)}"
        " — 面向内核 CVE 热补丁生成、构建与验证的工程化平台",
        "",
        f"{_style_help('Usage:', fg='bright_blue', bold=True)} {program_name} [global options] <command> [command options]",
        "",
        _help_section("Global Options:"),
    ]

    lines.extend(_wrap_help_entry("--help", "显示帮助页。", color="bright_yellow"))
    lines.extend(_wrap_help_entry("--install-completion", "为当前 shell 安装命令补全。", color="bright_yellow"))
    lines.extend(_wrap_help_entry("--show-completion", "输出补全脚本，便于自行集成。", color="bright_yellow"))
    lines.extend(_wrap_help_entry("--no-color", "关闭 ANSI 颜色，doctor 命令也支持该输出模式", color="bright_green"))
    lines.extend(_wrap_help_entry("--json", "部分命令支持结构化输出，适合脚本和测试。", color="bright_green"))
    lines.extend(_wrap_help_entry("--plain", "部分命令支持纯文本输出，适合日志采集或远程终端。", color="bright_green"))

    lines.extend(
        [
            "",
            _help_section("Commands:"),
            "  Hint: 带 * 的命令包含子命令，可运行 <command> --help 查看详情",
        ]
    )

    # 先列运行环境和交付相关命令，再列任务命令
    # 实际演示时顺序也基本是按这个走
    for name in env_commands:
        child = commands.get(name)
        if child is None:
            continue
        label = f"{name} *" if name in {"db", "models"} else name
        lines.extend(_wrap_help_entry(label, _command_help(child)))

    for name in task_commands:
        child = commands.get(name)
        if child is not None:
            lines.extend(_wrap_help_entry(name, _command_help(child)))

    root_examples = [
        ("patchweaver doctor --json", "输出结构化环境检查结果。"),
        ("patchweaver init --with-db", "初始化最小工程目录，并同时建立 SQLite 数据库。"),
        ("patchweaver paths --json", "输出当前生效的路径、运行时和 manifest 目录。"),
        ("patchweaver serve-api --reload", "启动 FastAPI 接口，供 Web 控制台开发调试。"),
        ("patchweaver install-api-service", "在 Linux 验证机上安装并启动 Web/API 的 systemd 服务。"),
        ("patchweaver prepare-build-tree --warm-target vmlinux", "在 Linux 验证机上准备并预热完整源码树。"),
        ("patchweaver db path", "查看当前配置解析出来的数据库路径。"),
        ("patchweaver evaluate --fixture contest_samples", "按固定样例集输出阶段评测汇总。"),
        ("patchweaver models --json", "查看当前模型分工和 API Key 来源。"),
        ("patchweaver models set-api-key --value sk-xxxx", "把 API Key 写入 config/models.yaml。"),
        ("patchweaver finalize", "生成 submission 目录和 final_manifest。"),
        ("patchweaver gate", "执行第四阶段最终门禁检查。"),
    ]
    lines.extend(
        [
            "",
            _help_section("Examples:"),
        ]
    )
    example_width = min(
        max((len(name) for name, _ in root_examples), default=30) + 2,
        46,
    )
    for name, description in root_examples:
        lines.extend(_wrap_help_entry(name, description, width=example_width, color="bright_green"))
    return _sanitize_cli_text("\n".join(lines))


def _render_db_help(command: click.Command) -> str:
    """渲染 db 子命令帮助页"""
    ctx = click.Context(command)
    command_path = _command_path(ctx, command)
    lines = [
        f"{_style_help('PatchWeaver / db', fg='bright_blue', bold=True)}"
        " — SQLite 与状态索引相关命令。",
        "",
        f"{_style_help('Usage:', fg='bright_blue', bold=True)} {command_path} <subcommand> [options]",
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

    db_examples = [
        ("patchweaver db init", "初始化 SQLite 数据库并写入基础 schema。"),
        ("patchweaver db path --json", "输出当前生效的数据库路径，便于外部脚本读取。"),
    ]
    lines.extend(
        [
            "",
            _help_section("Examples:"),
        ]
    )
    example_width = min(
        max((len(name) for name, _ in db_examples), default=30) + 2,
        36,
    )
    for name, description in db_examples:
        lines.extend(_wrap_help_entry(name, description, width=example_width, color="bright_green"))
    return _sanitize_cli_text("\n".join(lines))


def _render_models_help(command: click.Command) -> str:
    """渲染 models 子命令帮助页"""

    ctx = click.Context(command)
    command_path = _command_path(ctx, command)
    lines = [
        f"{_style_help('PatchWeaver / models', fg='bright_blue', bold=True)}"
        " — 模型配置与 API Key 管理命令",
        "",
        f"{_style_help('Usage:', fg='bright_blue', bold=True)} {command_path} [options]",
        f"       {command_path} <subcommand> [options]",
        "",
        _help_section("Options:"),
    ]

    lines.extend(_wrap_help_entry("--help", "显示帮助页", color="bright_yellow"))
    lines.extend(_wrap_help_entry("--json", "直接输出当前模型配置和 API Key 状态", color="bright_green"))

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

    model_examples = _command_examples(command_path)
    lines.extend(
        [
            "",
            _help_section("Examples:"),
        ]
    )
    example_width = min(
        max((len(name) for name, _ in model_examples), default=30) + 2,
        52,
    )
    for name, description in model_examples:
        lines.extend(_wrap_help_entry(name, description, width=example_width, color="bright_green"))
    return _sanitize_cli_text("\n".join(lines))


def _render_command_help(ctx: click.Context, command: click.Command) -> str:
    """渲染单命令帮助页"""
    command_path = _command_path(ctx, command)
    short_help = _command_help(command)
    help_text = _sanitize_cli_text((command.help or "").strip())
    lines = [
        _style_help(_command_heading(command_path), fg="bright_blue", bold=True),
        "",
        f"{_style_help('Usage:', fg='bright_blue', bold=True)} {command_path} [options]",
    ]

    if help_text:
        lines.extend(
            [
                "",
                help_text,
            ]
        )
    elif short_help:
        lines.extend(
            [
                "",
                short_help,
            ]
        )

    option_entries = _command_option_entries(ctx, command)
    if option_entries:
        # 选项表宽度按当前命令真实参数自适应
        # 避免短命令和长命令都被固定列宽拖得很散
        lines.extend(
            [
                "",
                _help_section("Options:"),
            ]
        )
        width = min(
            max((len(name) for name, _ in option_entries), default=18) + 2,
            30,
        )
        for name, description in option_entries:
            lines.extend(_wrap_help_entry(name, description, width=width, color="bright_yellow"))

    examples = _command_examples(command_path)
    if examples:
        # 示例只放最常用的几条，保持帮助页在终端里一屏内可读
        lines.extend(
            [
                "",
                _help_section("Examples:"),
            ]
        )
        example_width = min(
            max((len(name) for name, _ in examples), default=30) + 2,
            52,
        )
        for name, description in examples:
            lines.extend(_wrap_help_entry(name, description, width=example_width, color="bright_green"))
    return _sanitize_cli_text("\n".join(lines))


def _render_help_page(ctx: click.Context, command: click.Command) -> str:
    """根据命令类型选择帮助页模板"""
    if command.name == "db":
        return _render_db_help(command)
    if command.name == "models":
        return _render_models_help(command)
    return _render_root_help(ctx, command)


def _print_status(label: str, ok: bool, detail: str, *, use_color: bool = True) -> None:
    """输出一条环境检查结果"""
    prefix = "[正常]" if ok else "[提示]"
    color = typer.colors.GREEN if ok else typer.colors.YELLOW
    message = f"{prefix} {label}: {detail}"
    if use_color:
        typer.secho(message, fg=color)
    else:
        typer.echo(message)


def _runtime_payload(runtime: Any) -> dict[str, Any]:
    """整理运行时信息，供文本和 JSON 复用"""
    return {
        "project_root": _project_path(runtime.project_root, runtime.project_root),
        "config_dir": _project_path(runtime.project_root, runtime.config_dir),
        "workspace_root": _project_path(runtime.project_root, runtime.workspace_root),
        "database_path": _project_path(runtime.project_root, runtime.database_path),
        "manifest_dir": _project_path(runtime.project_root, runtime.manifest_dir),
        "default_kernel": runtime.default_kernel,
        "max_attempts": runtime.max_attempts,
        "parallel_read_limit": runtime.parallel_read_limit,
        "write_lock_scope": runtime.write_lock_scope,
        "trace_mode": runtime.trace_mode,
        "profile_name": runtime.profile_name,
        "enable_narrow_failover": runtime.enable_narrow_failover,
        "enable_read_parallel": runtime.enable_read_parallel,
    }


def _task_payload(task: TaskContext, project_root: Path | None = None) -> dict[str, Any]:
    """把任务对象整理成统一输出结构"""

    return {
        "task_id": task.task_id,
        "cve_id": task.cve_id,
        "target_kernel": task.target_kernel,
        "target_kernel_source": task.target_kernel_source,
        "profile_name": task.profile_name,
        "status": task.status,
        "current_attempt": task.current_attempt,
        "max_attempts": task.max_attempts,
        "workspace_dir": _project_path(project_root, task.workspace_dir),
        "machine_profile": task.machine_profile.model_dump(mode="json") if task.machine_profile is not None else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _attempt_summary_payload(attempt: Any, project_root: Path | None = None) -> dict[str, Any] | None:
    """整理最近一轮尝试的摘要字段"""

    if attempt is None:
        return None
    return {
        "attempt_id": attempt.attempt_id,
        "attempt_no": attempt.attempt_no,
        "status": attempt.status,
        "failure_type": attempt.failure_type,
        "build_exec_status": attempt.build_exec_status,
        "target_state": attempt.target_state,
        "build_log_path": _project_path(project_root, attempt.build_log_path),
        "module_path": _project_path(project_root, attempt.module_path),
        "rewritten_patch_path": _project_path(project_root, attempt.rewritten_patch_path),
        "started_at": attempt.started_at.isoformat(),
        "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
    }


def _build_task_runner(runtime: Any) -> TaskRunner:
    """按当前运行时配置创建任务编排器"""

    configs = load_effective_configs(project_root=runtime.project_root, profile_name=runtime.profile_name)
    return TaskRunner(
        runtime=runtime,
        build_config=configs["build"],
        verify_config=configs["verify"],
        prompts_config=configs["prompts"],
        skills_config=configs["skills"],
        models_config=load_models_config(runtime.project_root),
    )


def _build_release_service(runtime: Any) -> ReleaseService:
    """按当前运行时配置创建第四阶段交付服务"""

    return ReleaseService(
        runtime=runtime,
        build_config=load_build_config(runtime.project_root),
        logging_config=load_logging_config(runtime.project_root),
        models_config=load_models_config(runtime.project_root),
        task_repo=TaskRepository(runtime.database_path, runtime.project_root),
        attempt_repo=AttemptRepository(runtime.database_path, runtime.project_root),
        artifact_repo=ArtifactRepository(runtime.database_path, runtime.project_root),
    )


def _service_python_executable() -> Path:
    """Return the Python executable path that systemd should use."""

    # Keep the virtualenv entry path instead of resolving to the base interpreter.
    return Path(sys.executable)


def _build_run_logger(runtime: Any) -> RunLogger:
    """创建当前命令使用的运行日志写入器"""

    return RunLogger(runtime.project_root, load_logging_config(runtime.project_root))


def _resolve_task_runtime(task_id: str, base_runtime: Any) -> tuple[Any, TaskContext]:
    """按任务自身绑定的运行档位解析实际运行时"""

    task = TaskRepository(base_runtime.database_path, base_runtime.project_root).get_task(task_id)
    if task is None:
        raise ValueError(f"未找到任务：{task_id}")

    runtime = resolve_runtime(
        project_root=base_runtime.project_root,
        profile_name=task.profile_name,
        cli_database_path=str(base_runtime.database_path),
        cli_max_attempts=task.max_attempts,
    )
    return runtime, task


def _load_fixture_set(project_root: Path, fixture_name: str) -> tuple[str, list[dict[str, Any]]]:
    """读取批量评测使用的固定样例集"""

    filename = fixture_name if fixture_name.endswith(".json") else f"{fixture_name}.json"
    fixture_path = (project_root / "evaluations" / "fixtures" / filename).resolve()
    if not fixture_path.exists():
        raise ValueError(f"找不到固定样例集：{fixture_path}")

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"固定样例集格式不正确：{fixture_path}")
    return fixture_path.stem, payload


def _find_latest_task_for_fixture(tasks: list[TaskContext], fixture: dict[str, Any]) -> TaskContext | None:
    """按 CVE 和内核版本寻找最匹配的任务"""

    cve_id = str(fixture.get("cve_id") or "")
    target_kernel = str(fixture.get("target_kernel") or "")
    for task in tasks:
        if task.cve_id != cve_id:
            continue
        if target_kernel and task.target_kernel != target_kernel:
            continue
        return task
    return None


def _evaluate_fixture_set(runtime: Any, fixture_name: str) -> dict[str, Any]:
    """执行固定样例评测并输出阶段摘要"""

    fixture_set_name, fixtures = _load_fixture_set(runtime.project_root, fixture_name)
    task_repo = TaskRepository(runtime.database_path, runtime.project_root)
    attempt_repo = AttemptRepository(runtime.database_path, runtime.project_root)
    artifact_repo = ArtifactRepository(runtime.database_path, runtime.project_root)
    evaluator = Evaluator()
    stats_writer = StatsWriter(runtime.project_root)

    # 比赛期任务规模可控，这里直接读一批最近任务做匹配，方便先把阶段统计链路跑通
    tasks = task_repo.list_tasks(limit=500)
    results: list[dict[str, Any]] = []
    per_task_paths: list[str] = []
    output_dir = (runtime.data_dir / "evaluations" / fixture_set_name).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for fixture in fixtures:
        fixture_id = str(fixture.get("fixture_id") or fixture.get("cve_id") or "unknown")
        fixture_group = fixture.get("fixture_group") or fixture.get("sample_group") or fixture.get("group") or "default"
        matched_task = _find_latest_task_for_fixture(tasks, fixture)
        if matched_task is None:
            results.append(
                {
                    "fixture_id": fixture_id,
                    "cve_id": fixture.get("cve_id"),
                    "target_kernel": fixture.get("target_kernel"),
                    "fixture_group": fixture_group if fixture_group else "unmatched",
                    "matched": False,
                    "task_id": None,
                    "final_status": "missing",
                    "attempts": 0,
                    "latest_failure_type": None,
                    "evaluation_summary_path": None,
                }
            )
            continue

        attempts = attempt_repo.list_attempts(matched_task.task_id)
        artifacts = artifact_repo.list_artifacts(matched_task.task_id)
        task_summary = evaluator.summarize(attempts=attempts, artifacts=artifacts)
        task_dir = matched_task.workspace_dir.resolve()
        replay_comparison = evaluator.replay_comparison(
            task_id=matched_task.task_id,
            attempts=attempts,
            task_dir=task_dir,
        )
        per_task_payload = {
            "fixture_id": fixture_id,
            "fixture_group": fixture_group,
            "task_id": matched_task.task_id,
            "cve_id": matched_task.cve_id,
            "target_kernel": matched_task.target_kernel,
            "task_status": matched_task.status,
            "task_summary": task_summary,
            "replay_comparison": replay_comparison,
        }
        per_task_path = output_dir / f"{fixture_id}.json"
        stats_writer.write_json(per_task_payload, per_task_path)
        per_task_paths.append(_project_path(runtime.project_root, per_task_path) or "")
        results.append(
            {
                "fixture_id": fixture_id,
                "cve_id": matched_task.cve_id,
                "target_kernel": matched_task.target_kernel,
                "fixture_group": fixture_group,
                "matched": True,
                "task_id": matched_task.task_id,
                "final_status": matched_task.status,
                "attempts": len(attempts),
                "latest_failure_type": task_summary.get("latest_failure_type"),
                "evaluation_summary_path": _project_path(runtime.project_root, per_task_path),
            }
        )

    summary = evaluator.summarize_fixture_set(
        fixture_name=fixture_set_name,
        fixtures=fixtures,
        results=results,
    )
    summary["generated_files"] = per_task_paths
    summary_json_path = stats_writer.write_json(summary, output_dir / "summary.json")
    summary_md_path = stats_writer.write_markdown(summary, output_dir / "summary.md")

    return {
        "fixture_name": fixture_set_name,
        "fixture_count": len(fixtures),
        "summary": summary,
        "summary_json": _project_path(runtime.project_root, summary_json_path),
        "summary_md": _project_path(runtime.project_root, summary_md_path),
    }


def _doctor_payload(
    runtime: Any,
    build_config: Any,
    logging_config: Any,
    skills_config: Any,
    prompts_config: Any,
    models_config: Any,
) -> dict[str, Any]:
    """组装 doctor 命令的完整检查结果"""
    checks: list[dict[str, Any]] = []

    # 先把几块固定上下文整理出来，后面的检查项都直接引用这份快照
    skill_roots = {
        "project": _project_path(runtime.project_root, _resolve_project_path(runtime.project_root, skills_config.skill_dirs.project).resolve()),
        "shared": _project_path(runtime.project_root, _resolve_project_path(runtime.project_root, skills_config.skill_dirs.shared).resolve()),
        "builtin": _project_path(runtime.project_root, _resolve_project_path(runtime.project_root, skills_config.skill_dirs.builtin).resolve()),
    }
    bootstrap_dirs = [
        _project_path(runtime.project_root, _resolve_project_path(runtime.project_root, raw_dir).resolve())
        for raw_dir in prompts_config.bootstrap_fragment_dirs
    ]
    build_env = BuildOrchestrator(build_config).probe_environment()
    build_env["default_kernel"] = runtime.default_kernel
    machine_profile = collect_machine_profile(build_config, build_env=build_env).model_dump(mode="json")
    api_key_status = models_config.api_key_status()

    # Python 依赖放在最前面查，CLI 自己起不来的问题会最先暴露
    required_modules = {
        "typer": "命令行框架",
        "pydantic": "配置与模型校验",
        "yaml": "YAML 解析",
        "jinja2": "模板渲染",
        "unidiff": "补丁解析",
        "rich": "终端输出",
        "fastapi": "Web API",
        "uvicorn": "API 启动器",
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
        "models.yaml",
    ]
    for filename in config_files:
        config_path = runtime.config_dir / filename
        checks.append(_check_item(category="config_file", name=filename, label=f"配置文件 `{filename}`", ok=config_path.exists(), detail=_project_path(runtime.project_root, config_path)))

    submission_root = (runtime.project_root / "submission").resolve()
    checks.extend(
        [
            _check_item(
                category="models",
                name="model_topology",
                label="模型拓扑",
                ok=models_config.topology == "single_primary_with_optional_helpers",
                detail=models_config.topology,
                failed_status="error",
            ),
            _check_item(
                category="models",
                name="default_model",
                label="主模型",
                ok=bool(models_config.default_model),
                detail=models_config.default_model,
                failed_status="error",
            ),
            _check_item(
                category="models",
                name="delivery_model",
                label="正式交付模型",
                ok=bool(models_config.delivery_model),
                detail=models_config.delivery_model,
                failed_status="error",
            ),
            _check_item(
                category="models",
                name="api_key",
                label="百炼 API Key",
                ok=bool(api_key_status["api_key_ready"]),
                detail=(
                    f"{_api_key_source_label(str(api_key_status['api_key_source']))}"
                    f" / {api_key_status['api_key_masked'] or models_config.api_key_env}"
                ),
            ),
            _check_item(
                category="models",
                name="interaction_record_mode",
                label="模型交互记录模式",
                ok=models_config.interaction_record_mode in {"off", "basic", "full"},
                detail=models_config.interaction_record_mode,
                failed_status="error",
            ),
            _check_item(
                category="delivery",
                name="submission_root",
                label="submission 根目录",
                ok=submission_root.exists(),
                detail=_project_path(runtime.project_root, submission_root),
            ),
        ]
    )

    # 构建环境单独列出来，后面如果 doctor 报黄，基本一眼就能看出是环境问题还是代码问题
    checks.append(
        _check_item(
            category="build_backend",
            name="build_backend",
            label="构建后端",
            ok=build_env["backend"] == "local",
            detail=build_env["backend"],
            failed_status="error",
        )
    )

    checks.extend(
        [
            _check_item(
                category="external_command",
                name=build_config.kpatch_build_cmd,
                label=f"本机构建命令 `{build_config.kpatch_build_cmd}`",
                ok=bool(build_env.get("builder_ok")),
                detail=build_env.get("builder_path") or "当前 PATH 中未找到",
                failed_status="error",
            ),
            _check_item(
                category="build_env",
                name="selected_source_dir",
                label="当前运行机内核源码目录",
                ok=bool(build_env.get("selected_source_ok")),
                detail=build_env.get("selected_source_dir") or "未找到可用目录",
                failed_status="error",
            ),
            _check_item(
                category="build_env",
                name="config_path",
                label="当前运行机内核 .config",
                ok=bool(build_env.get("config_ok")),
                detail=build_env.get("config_path") or "未找到",
                failed_status="error",
            ),
            _check_item(
                category="build_env",
                name="vmlinux_path",
                label="当前运行机 vmlinux 路径",
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
                detail=_project_path(runtime.project_root, skill_root),
            )
        )

    if skills_config.require_manifest:
        # 要求 manifest 时，项目级 skill 必须至少具备可检查的最小入口描述
        for skill_name, skill_dir in _project_skill_dirs(runtime.project_root, skills_config).items():
            manifest_path = skill_dir / "manifest.yaml"
            checks.append(
                _check_item(
                    category="skill_manifest",
                    name=skill_name,
                    label=f"Skill Manifest `{skill_name}`",
                    ok=manifest_path.exists(),
                    detail=_project_path(runtime.project_root, manifest_path),
                )
            )

    # bootstrap 目录和 contracts 目录分开检查，方便排查 prompt 体系是不是缺文件
    for bootstrap_dir in bootstrap_dirs:
        bootstrap_path = Path(bootstrap_dir)
        checks.append(
            _check_item(
                category="bootstrap_dir",
                name=bootstrap_path.name,
                label=f"Bootstrap 目录 `{bootstrap_path.name}`",
                ok=bootstrap_path.exists(),
                detail=_project_path(runtime.project_root, bootstrap_path),
            )
        )

    prompt_contract_dir = (runtime.project_root / "prompts" / "contracts").resolve()
    checks.append(
        _check_item(
            category="prompt_contract",
            name="contracts",
            label="Prompt Contracts 目录",
            ok=prompt_contract_dir.exists(),
            detail=_project_path(runtime.project_root, prompt_contract_dir),
        )
    )

    checks.append(
        _check_item(
            category="filesystem",
            name="manifest_dir",
            label="Manifest 目录",
            ok=runtime.manifest_dir.exists(),
            detail=_project_path(runtime.project_root, runtime.manifest_dir),
        )
    )

    for template_path in _manifest_template_specs(runtime.project_root, runtime, skills_config):
        # doctor 只检查运行期 manifest 目录下的模板文件，项目 skill manifest 走上面的专项检查
        if template_path.parent != runtime.manifest_dir:
            continue
        checks.append(
            _check_item(
                category="manifest_template",
                name=template_path.name,
                label=f"Manifest 模板 `{template_path.name}`",
                ok=template_path.exists(),
                detail=_project_path(runtime.project_root, template_path),
            )
        )

    # 最后一段再看文件系统状态，这里基本能判断当前环境能不能继续跑任务
    log_path = _resolve_project_path(runtime.project_root, logging_config.file_path)
    jsonl_path = _resolve_project_path(runtime.project_root, logging_config.jsonl_path)
    interaction_jsonl_path = _resolve_project_path(runtime.project_root, models_config.interaction_jsonl_path)
    checks.extend(
        [
            _check_item(category="filesystem", name="log_dir", label="日志目录", ok=log_path.parent.exists(), detail=_project_path(runtime.project_root, log_path.parent)),
            _check_item(category="filesystem", name="jsonl_dir", label="JSONL 目录", ok=jsonl_path.parent.exists(), detail=_project_path(runtime.project_root, jsonl_path.parent)),
            _check_item(
                category="filesystem",
                name="model_interaction_jsonl_dir",
                label="模型交互日志目录",
                ok=interaction_jsonl_path.parent.exists(),
                detail=_project_path(runtime.project_root, interaction_jsonl_path.parent),
            ),
            _check_item(category="filesystem", name="workspace_root", label="工作区目录", ok=runtime.workspace_root.exists(), detail=_project_path(runtime.project_root, runtime.workspace_root)),
            _check_item(category="filesystem", name="sqlite_file", label="SQLite 文件", ok=runtime.database_path.exists(), detail=_project_path(runtime.project_root, runtime.database_path)),
        ]
    )

    # 汇总值直接从检查项回算，避免文本输出和 JSON 输出统计不一致
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
            "configured_default_kernel": runtime.default_kernel,
            "detected_target_kernel": machine_profile.get("build_target_kernel"),
            "detected_target_kernel_source": machine_profile.get("build_target_kernel_source"),
            "machine_kernel": machine_profile.get("machine_kernel"),
            "machine_arch": machine_profile.get("machine_arch"),
            "python_version": platform.python_version(),
            "skill_source_priority": skills_config.skill_source_priority,
        },
        "machine_profile": machine_profile,
        "skill_roots": skill_roots,
        "bootstrap_dirs": bootstrap_dirs,
        "build_env": build_env,
        "checks": checks,
        "summary": summary,
    }

@app.command("version", cls=PatchWeaverHelpCommand)
def version(
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """显示当前版本"""

    if json_output:
        _emit_json({"name": "PatchWeaver", "version": __version__})
        return

    typer.echo(f"PatchWeaver {__version__}")


@app.command("paths", cls=PatchWeaverHelpCommand)
def paths(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    max_attempts: Annotated[int | None, typer.Option("--max-attempts", help="覆盖最大尝试次数。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """打印当前生效的运行路径和关键配置"""

    runtime = _load_runtime(profile=profile, db_path=db_path, max_attempts=max_attempts)
    payload = _runtime_payload(runtime)

    if json_output:
        _emit_json(_project_payload(runtime.project_root, {"command": "paths", **payload}))
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


@app.command("init", cls=PatchWeaverHelpCommand)
def init_command(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    max_attempts: Annotated[int | None, typer.Option("--max-attempts", help="覆盖最大尝试次数。")] = None,
    with_db: Annotated[bool, typer.Option("--with-db", help="同时初始化 SQLite 数据库。")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """初始化最小运行目录"""

    runtime = _load_runtime(profile=profile, db_path=db_path, max_attempts=max_attempts)
    run_logger = _build_run_logger(runtime)
    logging_config = load_logging_config(runtime.project_root)
    skills_config = load_skills_config(runtime.project_root)
    prompts_config = load_prompts_config(runtime.project_root)
    # 把启动期会立即用到的目录一次建齐，避免后续命令各自补目录
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
        (runtime.project_root / "prompts" / "stages").resolve(),
    ]
    paths_to_create.extend(
        _resolve_project_path(runtime.project_root, raw_dir).resolve()
        for raw_dir in prompts_config.bootstrap_fragment_dirs
    )
    paths_to_create.extend(
        _resolve_project_path(runtime.project_root, raw_dir).resolve()
        for raw_dir in skills_config.skill_dirs.model_dump().values()
    )
    # 项目级 skill 目录按 enabled_skills 展开，和当前启用集合保持一致
    paths_to_create.extend(_project_skill_dirs(runtime.project_root, skills_config).values())

    created: list[Path] = []
    for path in paths_to_create:
        path.mkdir(parents=True, exist_ok=True)
        created.append(path.resolve())

    created_paths = [_project_path(runtime.project_root, path) or "" for path in sorted(set(created))]
    created_manifest_templates: list[str] = []
    # 模板和目录分开处理，方便区分“目录已存在”和“首次生成模板”的初始化结果
    for template_path, content in _manifest_template_specs(runtime.project_root, runtime, skills_config).items():
        if _ensure_template_file(template_path, content):
            created_manifest_templates.append(_project_path(runtime.project_root, template_path.resolve()) or "")

    final_path: Path | None = None
    if with_db:
        final_path = initialize_sqlite_db(runtime.database_path)
    run_logger.info(
        "cli.init",
        "完成最小工程初始化。",
        with_db=with_db,
        created_path_count=len(created_paths),
        manifest_template_count=len(created_manifest_templates),
    )

    if json_output:
        _emit_json(
            _project_payload(
                runtime.project_root,
                {
                    "command": "init",
                    "created_paths": created_paths,
                    "manifest_templates": created_manifest_templates,
                    "database_initialized": with_db,
                    "database_path": _project_path(runtime.project_root, final_path or runtime.database_path),
                    "next_steps": [
                        "patchweaver doctor",
                        "patchweaver paths --json",
                        "补充 prompts/bootstrap 和 skills/project 下的实际模板与 manifest。",
                    ],
                    "status": "ok",
                },
            )
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
        typer.echo(f"已初始化 SQLite 数据库：{_project_path(runtime.project_root, final_path)}")

    typer.echo("下一步建议：")
    typer.echo("  1. patchweaver doctor")
    typer.echo("  2. patchweaver paths --json")
    typer.echo("  3. 补充 prompts/bootstrap 和 skills/project 下的实际模板与 manifest。")


@app.command("doctor", cls=PatchWeaverHelpCommand)
def doctor(
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
    plain: Annotated[bool, typer.Option("--plain", help="强制使用纯文本输出。")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="关闭 ANSI 颜色。")] = False,
) -> None:
    """执行本地环境自检"""

    runtime = _load_runtime()
    build_config = load_build_config(runtime.project_root)
    logging_config = load_logging_config(runtime.project_root)
    skills_config = load_skills_config(runtime.project_root)
    prompts_config = load_prompts_config(runtime.project_root)
    models_config = load_models_config(runtime.project_root)
    payload = _project_payload(runtime.project_root, _doctor_payload(runtime, build_config, logging_config, skills_config, prompts_config, models_config))
    report_path = _write_json_snapshot(runtime.manifest_dir / "doctor_report.json", payload)

    # JSON 模式优先给脚本消费，不混入任何说明性文本
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
    typer.echo(f"配置默认内核: {payload['runtime']['configured_default_kernel']}")
    typer.echo(f"探测目标内核: {payload['runtime']['detected_target_kernel'] or '未探测到'}")
    typer.echo(f"目标内核探测来源: {payload['runtime']['detected_target_kernel_source'] or '未探测到'}")
    typer.echo(f"当前机器内核: {payload['runtime']['machine_kernel'] or '未探测到'}")
    typer.echo(f"Python 版本: {payload['runtime']['python_version']}")

    for item in payload["checks"]:
        _print_status(item["label"], item["ok"], item["detail"], use_color=use_color)

    # 最后一行保留汇总，便于快速判断当前环境是“可继续开发”还是“先补环境”
    typer.echo(
        f"汇总: 正常 {payload['summary']['ok']} / 提示 {payload['summary']['warn']} / 错误 {payload['summary']['error']}"
    )
    typer.echo(f"诊断快照: {_project_path(runtime.project_root, report_path)}")


@models_app.callback(invoke_without_command=True)
def models(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """查看当前模型配置和 API Key 状态"""

    if ctx.invoked_subcommand is not None:
        return

    runtime = _load_runtime()
    models_config = load_models_config(runtime.project_root)
    payload = _models_payload(models_config)
    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"模型供应方: {payload['provider']}")
    typer.echo(f"调用模式: {payload['endpoint_mode']}")
    typer.echo(f"接口地址: {payload['base_url']}")
    typer.echo(f"API Key 环境变量: {payload['api_key_env']}")
    typer.echo(f"API Key 来源: {_api_key_source_label(str(payload['api_key_source']))}")
    typer.echo(f"API Key 就绪: {payload['api_key_ready']}")
    typer.echo(f"API Key 脱敏值: {payload['api_key_masked'] or '未配置'}")
    typer.echo(f"配置文件已写入 Key: {payload['api_key_in_config']}")
    typer.echo(f"交互记录模式: {payload['interaction_record_mode']}")
    typer.echo(f"交互日志路径: {payload['interaction_jsonl_path']}")
    typer.echo(f"模型拓扑: {payload['topology']}")
    typer.echo(f"主模型: {payload['default_model']}")
    typer.echo(f"开发口径: {payload['development_model']}")
    typer.echo(f"交付口径: {payload['delivery_model']}")
    typer.echo(f"回退模型: {payload['fallback_model']}")
    typer.echo("辅助模型:")
    for helper_name, model_name in payload["helper_models"].items():
        note = payload["helper_notes"].get(helper_name, "")
        typer.echo(f"  - {helper_name}: {model_name} | {note}")
    typer.echo("执行边界:")
    for line in payload["execution_boundaries"]:
        typer.echo(f"  - {line}")


@models_app.command("set-api-key", cls=PatchWeaverHelpCommand)
def models_set_api_key(
    value: Annotated[str, typer.Option("--value", help="写入 config/models.yaml 的 API Key。")] = ...,
) -> None:
    """写入配置文件中的百炼 API Key"""

    runtime = _load_runtime()
    normalized_value = value.strip()
    if not normalized_value:
        typer.secho("错误: API Key 不能为空", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    path = save_models_api_settings(runtime.project_root, api_key=normalized_value)
    models_config = load_models_config(runtime.project_root)
    status = models_config.api_key_status()
    typer.echo(f"已更新: {_project_path(runtime.project_root, path)}")
    typer.echo(f"当前来源: {_api_key_source_label(str(status['api_key_source']))}")
    typer.echo(f"当前脱敏值: {status['api_key_masked'] or '未配置'}")
    typer.echo("说明: 当前 shell 的环境变量不会被命令直接改写，运行时仍会优先读取环境变量")


@models_app.command("set-api-key-env", cls=PatchWeaverHelpCommand)
def models_set_api_key_env(
    name: Annotated[str, typer.Option("--name", help="写入 models.yaml 的环境变量名。")] = ...,
) -> None:
    """修改优先读取的 API Key 环境变量名"""

    runtime = _load_runtime()
    env_name = name.strip()
    if not env_name:
        typer.secho("错误: 环境变量名不能为空", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    path = save_models_api_settings(runtime.project_root, api_key_env=env_name)
    typer.echo(f"已更新: {_project_path(runtime.project_root, path)}")
    typer.echo(f"新的环境变量名: {env_name}")
    typer.echo("说明: 运行时会先读取这个环境变量，没有命中时才回退到 config/models.yaml 中的 api_key")


@models_app.command("clear-api-key", cls=PatchWeaverHelpCommand)
def models_clear_api_key() -> None:
    """清空配置文件中的明文 API Key"""

    runtime = _load_runtime()
    path = save_models_api_settings(runtime.project_root, api_key="")
    typer.echo(f"已更新: {_project_path(runtime.project_root, path)}")
    typer.echo("config/models.yaml 中的 api_key 已清空")
    typer.echo("说明: 如果仍需调用模型，请继续使用环境变量或重新写入新的 api_key")


@app.command("create", cls=PatchWeaverHelpCommand)
def create(
    cve: Annotated[str, typer.Option("--cve", help="指定要处理的 CVE ID。")] = ...,
    kernel: Annotated[str | None, typer.Option("--kernel", help="覆盖目标内核版本。")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    max_attempts: Annotated[int | None, typer.Option("--max-attempts", help="覆盖最大尝试次数。")] = None,
    task_id: Annotated[str | None, typer.Option("--task-id", help="手工指定任务编号。")] = None,
    force_new: Annotated[bool, typer.Option("--force-new", help="忽略同配置任务查重，强制创建新的任务编号。")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """创建任务并初始化工作区骨架"""

    runtime = _load_runtime(profile=profile, max_attempts=max_attempts)
    run_logger = _build_run_logger(runtime)
    build_config = load_build_config(runtime.project_root)
    task_repo = TaskRepository(runtime.database_path, runtime.project_root)
    artifact_repo = ArtifactRepository(runtime.database_path, runtime.project_root)

    final_task_id = task_id or task_repo.next_task_id()
    if task_repo.task_exists(final_task_id):
        typer.secho(f"错误: 任务已存在：{final_task_id}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    target_kernel, target_kernel_source, machine_profile = resolve_task_binding(
        build_config=build_config,
        configured_default_kernel=runtime.default_kernel,
        cli_target_kernel=kernel,
    )
    duplicate_scope = build_duplicate_scope(
        cve_id=cve,
        target_kernel=target_kernel,
        target_kernel_source=target_kernel_source,
        profile_name=runtime.profile_name,
        machine_profile=machine_profile,
    )
    if not force_new:
        existing_task = task_repo.find_latest_equivalent_task(
            cve_id=cve,
            target_kernel=target_kernel,
            profile_name=runtime.profile_name,
            target_kernel_source=target_kernel_source,
            machine_profile=machine_profile,
        )
        if existing_task is not None:
            latest_attempt = AttemptRepository(runtime.database_path, runtime.project_root).get_latest_attempt(existing_task.task_id)
            duplicate_notice = build_duplicate_task_notice(existing_task, latest_attempt)
            duplicate_payload = _project_payload(
                runtime.project_root,
                {
                    "command": "create",
                    "status": "duplicate",
                    "created": False,
                    "message": duplicate_notice["message"],
                    "decision": duplicate_notice["decision"],
                    "reason": duplicate_notice["reason"],
                    "recommended_action": duplicate_notice["recommended_action"],
                    "next_steps": duplicate_notice["next_steps"],
                    "duplicate_scope": duplicate_scope,
                    "existing_task": _task_payload(existing_task, runtime.project_root),
                    "latest_attempt": _attempt_summary_payload(latest_attempt, runtime.project_root),
                },
            )
            run_logger.info(
                "cli.create_duplicate",
                duplicate_notice["message"],
                cve_id=cve,
                existing_task_id=existing_task.task_id,
                reason=duplicate_notice["reason"],
                duplicate_scope=duplicate_scope,
            )
            if json_output:
                _emit_json(duplicate_payload)
                return

            typer.echo("未创建新任务")
            typer.echo(duplicate_notice["message"])
            typer.echo(f"现有任务: {existing_task.task_id}")
            typer.echo(f"目标内核: {existing_task.target_kernel}")
            typer.echo(f"Profile: {existing_task.profile_name or 'default'}")
            typer.echo(f"最近状态: {latest_attempt.status if latest_attempt is not None else existing_task.status}")
            if latest_attempt is not None and latest_attempt.target_state:
                typer.echo(f"最近目标态: {latest_attempt.target_state}")
            typer.echo(f"建议: {duplicate_notice['recommended_action']}")
            typer.echo("说明: 如已切换源码树且确需新建任务，可追加 `--force-new`")
            return

    task = TaskContext(
        task_id=final_task_id,
        cve_id=cve,
        target_kernel=target_kernel,
        target_kernel_source=target_kernel_source,
        profile_name=runtime.profile_name,
        status="created",
        max_attempts=runtime.max_attempts,
        current_attempt=0,
        workspace_dir=(runtime.workspace_root / final_task_id).resolve(),
        machine_profile=machine_profile,
    )

    workspace_guard = WorkspaceGuard(runtime.workspace_root, runtime.project_root)
    task_dir = workspace_guard.create_task_workspace(task)
    task_repo.create_task(task)
    artifact_repo.add_artifact(
        task_id=task.task_id,
        artifact_type="task_context",
        artifact_path=task_dir / "task_context.json",
        metadata={"kind": "workspace_snapshot"},
    )

    payload = {
        "command": "create",
        "task": _task_payload(task, runtime.project_root),
        "next_attempt_dir": _project_path(runtime.project_root, task_dir / "attempts" / "001"),
        "prepared_attempt_dir": _project_path(runtime.project_root, task_dir / "attempts" / "001"),
        "status": "ok",
        "created": True,
    }
    payload = _project_payload(runtime.project_root, payload)
    run_logger.info(
        "cli.create",
        "创建任务并初始化工作区。",
        task_id=task.task_id,
        cve_id=task.cve_id,
        target_kernel=task.target_kernel,
        target_kernel_source=task.target_kernel_source,
        profile_name=task.profile_name,
        machine_profile=machine_profile.model_dump(mode="json"),
    )
    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"已创建任务: {task.task_id}")
    typer.echo(f"CVE 编号: {task.cve_id}")
    typer.echo(f"目标内核: {task.target_kernel}")
    typer.echo(f"目标内核来源: {task.target_kernel_source or 'unknown'}")
    typer.echo(f"工作区目录: {payload['task']['workspace_dir']}")
    typer.echo(f"首轮尝试目录: {payload['next_attempt_dir']}")
    typer.echo("说明: 尝试目录会在首次执行 `patchweaver run` 时创建。")


@app.command("run", cls=PatchWeaverHelpCommand)
def run(
    task: Annotated[str, typer.Option("--task", help="指定任务编号。")] = ...,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """执行最小单轮尝试"""

    runtime = _load_runtime()
    # 任务创建后可能带着自己的 profile 和 max_attempts
    # 这里重新按任务快照解析一次，避免命令入口和任务真实配置不一致
    runtime, _ = _resolve_task_runtime(task, runtime)
    run_logger = _build_run_logger(runtime)
    runner = _build_task_runner(runtime)
    try:
        payload = _project_payload(runtime.project_root, runner.run_task(task))
    except Exception as exc:
        run_logger.error("cli.run", "单轮执行失败。", task_id=task, error=str(exc))
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    run_logger.info(
        "cli.run",
        "完成单轮执行。",
        task_id=payload["task_id"],
        attempt_id=payload["attempt_id"],
        status=payload["status"],
        failure_type=payload["failure_type"],
    )

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"任务编号: {payload['task_id']}")
    typer.echo(f"尝试编号: {payload['attempt_id']}")
    typer.echo(f"执行结果: {payload['status']}")
    typer.echo(f"失败类型: {payload['failure_type']}")
    typer.echo(f"构建日志: {payload['build_log_path']}")
    typer.echo(f"Trace 路径: {payload['trace_path']}")


@app.command("status", cls=PatchWeaverHelpCommand)
def status(
    task: Annotated[str | None, typer.Option("--task", help="指定任务编号。")] = None,
    limit: Annotated[int, typer.Option("--limit", help="限制返回的任务条数。")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """查看任务状态"""

    runtime = _load_runtime()
    task_repo = TaskRepository(runtime.database_path, runtime.project_root)

    if task:
        task_context = task_repo.get_task(task)
        if task_context is None:
            typer.secho(f"错误: 未找到任务：{task}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1)
        payload = _project_payload(runtime.project_root, {"command": "status", "task": _task_payload(task_context, runtime.project_root)})
        if json_output:
            _emit_json(payload)
            return
        typer.echo(f"任务编号: {task_context.task_id}")
        typer.echo(f"CVE 编号: {task_context.cve_id}")
        typer.echo(f"目标内核: {task_context.target_kernel}")
        if task_context.target_kernel_source:
            typer.echo(f"目标内核来源: {task_context.target_kernel_source}")
        typer.echo(f"当前状态: {task_context.status}")
        typer.echo(f"当前尝试轮: {task_context.current_attempt}/{task_context.max_attempts}")
        typer.echo(f"工作区目录: {payload['task']['workspace_dir']}")
        return

    tasks = task_repo.list_tasks(limit=limit)
    payload = _project_payload(runtime.project_root, {"command": "status", "tasks": [_task_payload(item, runtime.project_root) for item in tasks]})
    if json_output:
        _emit_json(payload)
        return

    if not tasks:
        typer.echo("当前还没有任务记录。")
        return

    typer.echo("最近任务：")
    for item in payload["tasks"]:
        typer.echo(f"  - {item['task_id']} | {item['cve_id']} | {item['status']} | {item['workspace_dir']}")


@app.command("analyze", cls=PatchWeaverHelpCommand)
def analyze(
    task: Annotated[str, typer.Option("--task", help="指定任务编号。")] = ...,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """执行最小分析链路"""

    runtime = _load_runtime()
    # analyze 也按任务侧 runtime 执行
    # 这样 create、analyze、run 看到的是同一套路径和档位
    runtime, _ = _resolve_task_runtime(task, runtime)
    run_logger = _build_run_logger(runtime)
    runner = _build_task_runner(runtime)
    try:
        payload = _project_payload(runtime.project_root, runner.analyze_task(task))
    except Exception as exc:
        run_logger.error("cli.analyze", "分析阶段执行失败。", task_id=task, error=str(exc))
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    run_logger.info("cli.analyze", "完成分析阶段。", task_id=payload["task_id"])

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"任务编号: {payload['task_id']}")
    typer.echo(f"PatchBundle: {payload['patch_bundle_path']}")
    if payload.get("source_fetch_trace_path"):
        typer.echo(f"SourceFetchTrace: {payload['source_fetch_trace_path']}")
    typer.echo(f"SemanticCard: {payload['semantic_card_path']}")
    if payload.get("semantic_card_enrichment_path"):
        typer.echo(f"SemanticEnrichment: {payload['semantic_card_enrichment_path']}")
    typer.echo(f"ConstraintReport: {payload['constraint_report_path']}")
    typer.echo(f"Bootstrap Manifest: {payload['bootstrap_manifest_path']}")


@app.command("report", cls=PatchWeaverHelpCommand)
def report(
    task: Annotated[str, typer.Option("--task", help="指定任务编号。")] = ...,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """生成任务报告"""

    runtime = _load_runtime()
    # 报告阶段主要是读取任务产物
    # 这里仍然对齐任务自己的配置，避免 report/replay 指到别的目录
    runtime, _ = _resolve_task_runtime(task, runtime)
    run_logger = _build_run_logger(runtime)
    runner = _build_task_runner(runtime)
    try:
        payload = _project_payload(runtime.project_root, runner.build_report(task))
    except Exception as exc:
        run_logger.error("cli.report", "报告生成失败。", task_id=task, error=str(exc))
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    run_logger.info("cli.report", "生成最终报告。", task_id=payload["task_id"], report_json=payload["report_json"])

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"任务编号: {payload['task_id']}")
    typer.echo(f"JSON 报告: {payload['report_json']}")
    typer.echo(f"Markdown 报告: {payload['report_md']}")


@app.command("replay", cls=PatchWeaverHelpCommand)
def replay(
    task: Annotated[str, typer.Option("--task", help="指定任务编号。")] = ...,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """查看最近一轮回放信息"""

    runtime = _load_runtime()
    # 回放只读历史产物
    # 但路径基准仍然以任务快照为准，避免跨 profile 时读错目录
    runtime, _ = _resolve_task_runtime(task, runtime)
    run_logger = _build_run_logger(runtime)
    runner = _build_task_runner(runtime)
    try:
        payload = _project_payload(runtime.project_root, runner.replay_task(task))
    except Exception as exc:
        run_logger.error("cli.replay", "回放信息读取失败。", task_id=task, error=str(exc))
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    run_logger.info("cli.replay", "读取任务回放信息。", task_id=payload["task_id"])

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"任务编号: {payload['task_id']}")
    typer.echo(f"最近尝试: {payload['latest_attempt_id']}")
    typer.echo(f"尝试结果: {payload['latest_attempt_status']}")
    typer.echo(f"Trace 路径: {payload['trace_path']}")
    typer.echo(f"报告路径: {payload['report_path']}")


@app.command("evaluate", cls=PatchWeaverHelpCommand)
def evaluate(
    fixture: Annotated[str, typer.Option("--fixture", help="指定固定样例集名称或 JSON 文件名。")] = "contest_samples",
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """按固定样例集输出阶段评测结果"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    run_logger = _build_run_logger(runtime)
    try:
        payload = _evaluate_fixture_set(runtime, fixture)
    except Exception as exc:
        run_logger.error("cli.evaluate", "阶段评测执行失败。", fixture=fixture, error=str(exc))
        typer.secho(f"错误: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    run_logger.info(
        "cli.evaluate",
        "完成阶段评测。",
        fixture_name=payload["fixture_name"],
        fixture_count=payload["fixture_count"],
        summary_json=payload["summary_json"],
    )

    if json_output:
        _emit_json(payload)
        return

    summary = payload["summary"]
    typer.echo(f"固定样例集: {payload['fixture_name']}")
    typer.echo(f"样例总数: {payload['fixture_count']}")
    typer.echo(f"命中样例: {summary['matched_fixtures']}")
    typer.echo(f"成功数: {summary['success_count']}")
    typer.echo(f"成功率: {summary['success_rate']:.2%}")
    typer.echo(f"平均尝试轮次: {summary['average_attempts']}")
    typer.echo(f"JSON 摘要: {payload['summary_json']}")
    typer.echo(f"Markdown 摘要: {payload['summary_md']}")


@app.command("init-db", cls=PatchWeaverHelpCommand)
def init_db(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """按当前生效配置初始化 SQLite 数据库"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    final_path = initialize_sqlite_db(runtime.database_path)
    final_path_text = _project_path(runtime.project_root, final_path)
    _build_run_logger(runtime).info("cli.init_db", "初始化 SQLite 数据库。", database_path=final_path_text)
    if json_output:
        _emit_json({"command": "init-db", "database_path": final_path_text, "status": "ok"})
        return
    typer.echo(f"已初始化 SQLite 数据库：{final_path_text}")


@app.command("finalize", cls=PatchWeaverHelpCommand)
def finalize(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """生成 submission 目录和 final manifest"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    run_logger = _build_run_logger(runtime)
    payload = _project_payload(runtime.project_root, _build_release_service(runtime).prepare_submission())
    run_logger.info("cli.finalize", "生成 submission 目录和 final manifest。", manifest=payload["final_manifest_json"])
    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"submission 根目录: {payload['submission_root']}")
    typer.echo(f"final_manifest.json: {payload['final_manifest_json']}")
    typer.echo(f"final_manifest.md: {payload['final_manifest_md']}")


@app.command("gate", cls=PatchWeaverHelpCommand)
def gate(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """执行第四阶段最终门禁检查"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    run_logger = _build_run_logger(runtime)
    payload = _project_payload(runtime.project_root, _build_release_service(runtime).run_gate())
    run_logger.info("cli.gate", "执行最终门禁检查。", status=payload["status"], gate_report=payload["final_gate_json"])
    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"总体状态: {payload['status']}")
    typer.echo(f"gate.json: {payload['final_gate_json']}")
    typer.echo(f"gate.md: {payload['final_gate_md']}")
    typer.echo(f"通过: {payload['summary']['passed']} / 带限制通过: {payload['summary']['limited']} / 未通过: {payload['summary']['failed']}")


@app.command("install-api-service", cls=PatchWeaverHelpCommand)
def install_api_service_command(
    service_name: Annotated[str | None, typer.Option("--service-name", help="systemd 服务名。")] = None,
    host: Annotated[str | None, typer.Option("--host", help="API 服务监听地址。")] = None,
    port: Annotated[int | None, typer.Option("--port", help="API 服务监听端口。")] = None,
    enable: Annotated[bool, typer.Option("--enable/--no-enable", help="是否加入开机自启。")] = True,
    start: Annotated[bool, typer.Option("--start/--no-start", help="安装后是否立即启动。")] = True,
    timeout_sec: Annotated[int, typer.Option("--timeout-sec", help="等待健康检查通过的秒数。")] = 45,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """在 Linux 验证机上安装并启动 Web/API 的 systemd 服务"""

    runtime = _load_runtime()
    run_logger = _build_run_logger(runtime)
    system_config = load_system_config(runtime.project_root)

    final_service_name = service_name or system_config.api_service_name or DEFAULT_API_SERVICE_NAME
    final_host = host or system_config.api_host
    final_port = port or system_config.api_port

    if platform.system() != "Linux":
        typer.secho("错误: install-api-service 仅支持 Linux + systemd 环境。", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        install_payload = install_systemd_service(
            service_name=final_service_name,
            python_executable=_service_python_executable(),
            project_root=runtime.project_root,
            host=final_host,
            port=final_port,
            enable=enable,
            start=start,
        )
        ready_payload = wait_for_api_ready(host=final_host, port=final_port, timeout_sec=float(timeout_sec)) if start else None
    except Exception as exc:
        typer.secho(f"错误: API 服务安装失败: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    payload = {
        "command": "install-api-service",
        "project_root": _project_path(runtime.project_root, runtime.project_root),
        "service_name": final_service_name,
        "host": final_host,
        "port": final_port,
        "enable": enable,
        "start": start,
        "healthz": install_payload["healthz"],
        "console": install_payload["console"],
        "unit_path": _project_path(runtime.project_root, install_payload["unit_path"]),
        "ready": ready_payload["ready"] if ready_payload else False,
    }
    payload = _project_payload(runtime.project_root, payload)
    snapshot_path = _write_json_snapshot(runtime.manifest_dir / "api_service_install.json", payload)
    run_logger.info(
        "cli.install_api_service",
        "已安装 Web/API 的 systemd 服务。",
        service_name=final_service_name,
        host=final_host,
        port=final_port,
        enable=enable,
        start=start,
        snapshot_path=str(snapshot_path),
    )

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"已安装 API 服务: {final_service_name}")
    typer.echo(f"unit 文件: {payload['unit_path']}")
    typer.echo(f"healthz: {payload['healthz']}")
    typer.echo(f"console: {payload['console']}")
    typer.echo(f"快照: {_project_path(runtime.project_root, snapshot_path)}")


@app.command("prepare-build-tree", cls=PatchWeaverHelpCommand)
def prepare_build_tree_command(
    kernel_release: Annotated[str | None, typer.Option("--kernel-release", help="目标内核版本。")] = None,
    output_dir: Annotated[str | None, typer.Option("--output-dir", help="完整源码树输出目录。")] = None,
    overlay_dirs: Annotated[list[str] | None, typer.Option("--overlay-dir", help="需要 overlay 到完整源码树上的目录，可重复指定。")] = None,
    kernel_devel_package: Annotated[str | None, typer.Option("--kernel-devel-package", help="用于下载 source rpm 的包名。")] = None,
    dnf_cmd: Annotated[str, typer.Option("--dnf-cmd", help="下载 source rpm 时使用的命令。")] = "dnf",
    force: Annotated[bool, typer.Option("--force", help="若输出目录已存在则强制重建。")] = False,
    warm_targets: Annotated[list[str] | None, typer.Option("--warm-target", help="额外预热的 make target，可重复指定。")] = None,
    warm_jobs: Annotated[int | None, typer.Option("--warm-jobs", help="预热源码树时 make 使用的并发数。")] = None,
    force_warm: Annotated[bool, typer.Option("--force-warm", help="即便已有预热记录也重新执行预热。")] = False,
    write_build_config: Annotated[bool, typer.Option("--write-build-config/--no-write-build-config", help="是否把 prepared_kernel_src_dir 写回 build.yaml。")] = True,
    build_config_path: Annotated[str | None, typer.Option("--build-config", help="build.yaml 路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """在 Linux 验证机上准备可供 kpatch-build 使用的完整源码树"""

    runtime = _load_runtime()
    run_logger = _build_run_logger(runtime)

    if platform.system() != "Linux":
        typer.secho("错误: prepare-build-tree 仅支持 Linux 环境", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    final_kernel_release = kernel_release or runtime.default_kernel
    final_output_dir = Path(output_dir) if output_dir else Path("/opt/patchweaver/kernel-src-prepared") / final_kernel_release
    final_overlay_dirs = [Path(item) for item in (overlay_dirs or [])]
    if not final_overlay_dirs:
        final_overlay_dirs = [
            Path("/opt/kernel-src"),
            Path(f"/usr/src/kernels/{final_kernel_release}"),
        ]
    final_build_config_path = Path(build_config_path) if build_config_path else runtime.config_dir / "build.yaml"

    try:
        result = prepare_validation_source_tree(
            kernel_release=final_kernel_release,
            output_dir=final_output_dir,
            overlay_dirs=final_overlay_dirs,
            force=force,
            dnf_cmd=dnf_cmd,
            kernel_devel_package=kernel_devel_package,
            build_config_path=final_build_config_path,
            write_build_config=write_build_config,
            warm_targets=warm_targets,
            warm_jobs=warm_jobs,
            force_warm=force_warm,
        )
    except Exception as exc:
        typer.secho(f"错误: 完整源码树准备失败: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    payload = {
        "command": "prepare-build-tree",
        **result.to_payload(),
    }
    payload = _project_payload(runtime.project_root, payload)
    run_logger.info(
        "cli.prepare_build_tree",
        "已完成完整源码树准备",
        kernel_release=final_kernel_release,
        output_dir=str(final_output_dir),
        reused_existing=result.reused_existing,
        warmup_targets=result.warmup_targets,
        warmup_performed=result.warmup_performed,
        build_config_path=str(final_build_config_path) if write_build_config else None,
    )

    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"已准备源码树: {payload['output_dir']}")
    typer.echo(f"kernel release: {payload['kernel_release']}")
    typer.echo(f"source rpm: {payload['srpm_path'] or '<reused>'}")
    typer.echo(f"source tarball: {payload['source_tarball'] or '<reused>'}")
    typer.echo(f"overlay dirs: {', '.join(payload['overlay_dirs']) if payload['overlay_dirs'] else '<none>'}")
    typer.echo(f"setlocalversion patched: {payload['setlocalversion_patched']}")
    typer.echo(f"build config: {payload['build_config_path'] or '<not written>'}")


@app.command("serve-api", cls=PatchWeaverHelpCommand)
def serve_api(
    host: Annotated[str | None, typer.Option("--host", help="指定 API 监听地址。")] = None,
    port: Annotated[int | None, typer.Option("--port", help="指定 API 监听端口。")] = None,
    reload: Annotated[bool, typer.Option("--reload", help="开发阶段开启自动重载。")] = False,
    foreground: Annotated[bool, typer.Option("--foreground", help="以前台方式启动并占用当前终端。")] = False,
    timeout_sec: Annotated[int, typer.Option("--timeout-sec", help="后台模式等待健康检查通过的秒数。")] = 15,
) -> None:
    """启动 Web 控制台后端接口"""

    # API 服务默认直接复用当前仓库里的 patchweaver.api.app，不再单独维护第二套启动脚本
    import uvicorn

    runtime = _load_runtime()
    system_config = load_system_config(runtime.project_root)
    final_host = host or system_config.api_host
    final_port = port or system_config.api_port
    run_logger = _build_run_logger(runtime)

    # Linux 验证机默认走后台服务模式，便于执行命令后立即回到 shell
    background_mode = (
        not foreground
        and not reload
        and system_config.auto_install_api_service
        and systemd_available()
    )

    if background_mode:
        service_name = system_config.api_service_name or DEFAULT_API_SERVICE_NAME
        try:
            install_payload = install_systemd_service(
                service_name=service_name,
                python_executable=_service_python_executable(),
                project_root=runtime.project_root,
                host=final_host,
                port=final_port,
                enable=True,
                start=True,
            )
            ready_payload = wait_for_api_ready(host=final_host, port=final_port, timeout_sec=float(timeout_sec))
        except Exception as exc:
            typer.secho(
                f"错误: 后台启动 API 服务失败: {exc}；如需临时前台调试，可改用 `patchweaver serve-api --foreground`",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1) from exc

        run_logger.info(
            "cli.serve_api_background",
            "已在后台重启 Web 控制台后端接口。",
            service_name=service_name,
            host=final_host,
            port=final_port,
            ready=ready_payload["ready"],
        )
        typer.echo(f"已在后台重启 PatchWeaver API: http://{final_host}:{final_port}")
        typer.echo(f"systemd 服务: {service_name}")
        typer.echo(f"healthz: {install_payload['healthz']}")
        typer.echo(f"console: {install_payload['console']}")
        return

    run_logger.info(
        "cli.serve_api",
        "以前台方式启动 Web 控制台后端接口。",
        host=final_host,
        port=final_port,
        reload=reload,
        foreground=True,
    )
    typer.echo(f"启动 PatchWeaver API: http://{final_host}:{final_port}")
    uvicorn.run("patchweaver.api.app:app", host=final_host, port=final_port, reload=reload)


@db_app.command("init", cls=PatchWeaverHelpCommand)
def db_init(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """初始化 SQLite 数据库"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    final_path = initialize_sqlite_db(runtime.database_path)
    if json_output:
        _emit_json({"command": "db init", "database_path": _project_path(runtime.project_root, final_path), "status": "ok"})
        return
    typer.echo(f"已初始化 SQLite 数据库：{_project_path(runtime.project_root, final_path)}")


@db_app.command("path", cls=PatchWeaverHelpCommand)
def db_path(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """打印当前生效的 SQLite 路径"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    if json_output:
        _emit_json({"command": "db path", "database_path": _project_path(runtime.project_root, runtime.database_path)})
        return
    typer.echo(_project_path(runtime.project_root, runtime.database_path))


if __name__ == "__main__":
    app()
