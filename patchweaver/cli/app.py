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
from patchweaver.api.service_manager import (
    DEFAULT_API_SERVICE_NAME,
    install_systemd_service,
    wait_for_api_ready,
)
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.config.loader import (
    load_build_config,
    load_logging_config,
    load_models_config,
    load_prompts_config,
    load_skills_config,
    load_system_config,
    load_verify_config,
)
from patchweaver.config.resolver import load_effective_configs, resolve_runtime
from patchweaver.coordinator.task_runner import TaskRunner
from patchweaver.harness.attempt_engine import AttemptEngine
from patchweaver.harness.evaluator import Evaluator
from patchweaver.harness.workspace_guard import WorkspaceGuard
from patchweaver.models.task import TaskContext
from patchweaver.observability.run_logger import RunLogger
from patchweaver.reporter.release_service import ReleaseService
from patchweaver.reporter.stats_writer import StatsWriter
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


def _write_json_snapshot(path: Path, payload: dict[str, Any]) -> Path:
    """把结构化结果额外落成一份 JSON 快照。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


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
    task_commands = ["create", "analyze", "run", "report", "replay", "evaluate"]
    env_commands = [
        "init",
        "doctor",
        "paths",
        "models",
        "install-api-service",
        "finalize",
        "gate",
        "init-db",
        "db",
        "serve-api",
        "status",
        "version",
    ]
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
    lines.extend(_wrap_help_entry("patchweaver install-api-service", "在 Linux 验证机上安装并启动 Web/API 的 systemd 服务。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver db path", "查看当前配置解析出来的数据库路径。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver evaluate --fixture contest_samples", "按固定样例集输出阶段评测汇总。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver models --json", "查看当前模型分工和百炼环境变量状态。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver finalize", "生成 submission 目录和 final_manifest。", width=30, color="bright_green"))
    lines.extend(_wrap_help_entry("patchweaver gate", "执行第四阶段最终门禁检查。", width=30, color="bright_green"))
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
        "profile_name": task.profile_name,
        "status": task.status,
        "current_attempt": task.current_attempt,
        "max_attempts": task.max_attempts,
        "workspace_dir": str(task.workspace_dir),
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _build_task_runner(runtime: Any) -> TaskRunner:
    """按当前运行时配置创建任务编排器。"""

    configs = load_effective_configs(project_root=runtime.project_root, profile_name=runtime.profile_name)
    return TaskRunner(
        runtime=runtime,
        build_config=configs["build"],
        verify_config=configs["verify"],
        prompts_config=configs["prompts"],
        skills_config=configs["skills"],
    )


def _build_release_service(runtime: Any) -> ReleaseService:
    """按当前运行时配置创建第四阶段交付服务。"""

    return ReleaseService(
        runtime=runtime,
        build_config=load_build_config(runtime.project_root),
        logging_config=load_logging_config(runtime.project_root),
        models_config=load_models_config(runtime.project_root),
        task_repo=TaskRepository(runtime.database_path),
        attempt_repo=AttemptRepository(runtime.database_path),
        artifact_repo=ArtifactRepository(runtime.database_path),
    )


def _build_run_logger(runtime: Any) -> RunLogger:
    """创建当前命令使用的运行日志写入器。"""

    return RunLogger(runtime.project_root, load_logging_config(runtime.project_root))


def _resolve_task_runtime(task_id: str, base_runtime: Any) -> tuple[Any, TaskContext]:
    """按任务自身绑定的运行档位解析实际运行时。"""

    task = TaskRepository(base_runtime.database_path).get_task(task_id)
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
    """读取批量评测使用的固定样例集。"""

    filename = fixture_name if fixture_name.endswith(".json") else f"{fixture_name}.json"
    fixture_path = (project_root / "evaluations" / "fixtures" / filename).resolve()
    if not fixture_path.exists():
        raise ValueError(f"找不到固定样例集：{fixture_path}")

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"固定样例集格式不正确：{fixture_path}")
    return fixture_path.stem, payload


def _find_latest_task_for_fixture(tasks: list[TaskContext], fixture: dict[str, Any]) -> TaskContext | None:
    """按 CVE 和内核版本寻找最匹配的任务。"""

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
    """执行固定样例评测并输出阶段摘要。"""

    fixture_set_name, fixtures = _load_fixture_set(runtime.project_root, fixture_name)
    task_repo = TaskRepository(runtime.database_path)
    attempt_repo = AttemptRepository(runtime.database_path)
    artifact_repo = ArtifactRepository(runtime.database_path)
    evaluator = Evaluator()
    stats_writer = StatsWriter()

    # 比赛期任务规模可控，这里直接读一批最近任务做匹配，方便先把阶段统计链路跑通。
    tasks = task_repo.list_tasks(limit=500)
    results: list[dict[str, Any]] = []
    per_task_paths: list[str] = []
    output_dir = (runtime.data_dir / "evaluations" / fixture_set_name).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for fixture in fixtures:
        fixture_id = str(fixture.get("fixture_id") or fixture.get("cve_id") or "unknown")
        matched_task = _find_latest_task_for_fixture(tasks, fixture)
        if matched_task is None:
            results.append(
                {
                    "fixture_id": fixture_id,
                    "cve_id": fixture.get("cve_id"),
                    "target_kernel": fixture.get("target_kernel"),
                    "sample_group": fixture.get("sample_group") or fixture.get("group") or "unmatched",
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
            "task_id": matched_task.task_id,
            "cve_id": matched_task.cve_id,
            "target_kernel": matched_task.target_kernel,
            "task_status": matched_task.status,
            "task_summary": task_summary,
            "replay_comparison": replay_comparison,
        }
        per_task_path = output_dir / f"{fixture_id}.json"
        stats_writer.write_json(per_task_payload, per_task_path)
        per_task_paths.append(str(per_task_path))
        results.append(
            {
                "fixture_id": fixture_id,
                "cve_id": matched_task.cve_id,
                "target_kernel": matched_task.target_kernel,
                "sample_group": fixture.get("sample_group") or fixture.get("group") or "default",
                "matched": True,
                "task_id": matched_task.task_id,
                "final_status": matched_task.status,
                "attempts": len(attempts),
                "latest_failure_type": task_summary.get("latest_failure_type"),
                "evaluation_summary_path": str(per_task_path),
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
        "summary_json": str(summary_json_path),
        "summary_md": str(summary_md_path),
    }


def _doctor_payload(
    runtime: Any,
    build_config: Any,
    logging_config: Any,
    skills_config: Any,
    prompts_config: Any,
    models_config: Any,
) -> dict[str, Any]:
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
        checks.append(_check_item(category="config_file", name=filename, label=f"配置文件 `{filename}`", ok=config_path.exists(), detail=str(config_path)))

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
                name="api_key_env",
                label="百炼 API Key 环境变量",
                ok=bool(os.getenv(models_config.api_key_env)),
                detail=models_config.api_key_env,
            ),
            _check_item(
                category="delivery",
                name="submission_root",
                label="submission 根目录",
                ok=submission_root.exists(),
                detail=str(submission_root),
            ),
        ]
    )

    # 构建环境单独列出来，后面如果 doctor 报黄，基本一眼就能看出是环境问题还是代码问题。
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
    run_logger = _build_run_logger(runtime)
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
    run_logger.info(
        "cli.init",
        "完成最小工程初始化。",
        with_db=with_db,
        created_path_count=len(created_paths),
        manifest_template_count=len(created_manifest_templates),
    )

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
    models_config = load_models_config(runtime.project_root)
    payload = _doctor_payload(runtime, build_config, logging_config, skills_config, prompts_config, models_config)
    report_path = _write_json_snapshot(runtime.manifest_dir / "doctor_report.json", payload)

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
    typer.echo(f"诊断快照: {report_path}")


@app.command("models")
def models(
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """查看当前模型配置和环境变量状态。"""

    runtime = _load_runtime()
    models_config = load_models_config(runtime.project_root)
    payload = {
        "command": "models",
        "provider": models_config.provider,
        "endpoint_mode": models_config.endpoint_mode,
        "base_url": models_config.base_url,
        "api_key_env": models_config.api_key_env,
        "api_key_ready": bool(os.getenv(models_config.api_key_env)),
        "topology": models_config.topology,
        "default_model": models_config.default_model,
        "development_model": models_config.development_model,
        "delivery_model": models_config.delivery_model,
        "fallback_model": models_config.fallback_model,
        "helper_models": models_config.helper_models,
        "helper_notes": models_config.helper_notes,
        "execution_boundaries": models_config.execution_boundaries,
    }
    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"模型供应方: {payload['provider']}")
    typer.echo(f"调用模式: {payload['endpoint_mode']}")
    typer.echo(f"接口地址: {payload['base_url']}")
    typer.echo(f"API Key 环境变量: {payload['api_key_env']}")
    typer.echo(f"API Key 就绪: {payload['api_key_ready']}")
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


@app.command("create")
def create(
    cve: Annotated[str, typer.Option("--cve", help="指定要处理的 CVE ID。")] = ...,
    kernel: Annotated[str | None, typer.Option("--kernel", help="覆盖目标内核版本。")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    max_attempts: Annotated[int | None, typer.Option("--max-attempts", help="覆盖最大尝试次数。")] = None,
    task_id: Annotated[str | None, typer.Option("--task-id", help="手工指定任务编号。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """创建任务并初始化工作区骨架。"""

    runtime = _load_runtime(profile=profile, max_attempts=max_attempts)
    run_logger = _build_run_logger(runtime)
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
        profile_name=runtime.profile_name,
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
    run_logger.info(
        "cli.create",
        "创建任务并初始化工作区。",
        task_id=task.task_id,
        cve_id=task.cve_id,
        target_kernel=task.target_kernel,
        profile_name=task.profile_name,
    )
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
    runtime, _ = _resolve_task_runtime(task, runtime)
    run_logger = _build_run_logger(runtime)
    runner = _build_task_runner(runtime)
    try:
        payload = runner.run_task(task)
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
    runtime, _ = _resolve_task_runtime(task, runtime)
    run_logger = _build_run_logger(runtime)
    runner = _build_task_runner(runtime)
    try:
        payload = runner.analyze_task(task)
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
    runtime, _ = _resolve_task_runtime(task, runtime)
    run_logger = _build_run_logger(runtime)
    runner = _build_task_runner(runtime)
    try:
        payload = runner.build_report(task)
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


@app.command("replay")
def replay(
    task: Annotated[str, typer.Option("--task", help="指定任务编号。")] = ...,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """查看最近一轮回放信息。"""

    runtime = _load_runtime()
    runtime, _ = _resolve_task_runtime(task, runtime)
    run_logger = _build_run_logger(runtime)
    runner = _build_task_runner(runtime)
    try:
        payload = runner.replay_task(task)
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


@app.command("evaluate")
def evaluate(
    fixture: Annotated[str, typer.Option("--fixture", help="指定固定样例集名称或 JSON 文件名。")] = "contest_samples",
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """按固定样例集输出阶段评测结果。"""

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


@app.command("init-db")
def init_db(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """按当前生效配置初始化 SQLite 数据库。"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    final_path = initialize_sqlite_db(runtime.database_path)
    _build_run_logger(runtime).info("cli.init_db", "初始化 SQLite 数据库。", database_path=str(final_path))
    if json_output:
        _emit_json({"command": "init-db", "database_path": str(final_path), "status": "ok"})
        return
    typer.echo(f"已初始化 SQLite 数据库：{final_path}")


@app.command("finalize")
def finalize(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """生成 submission 目录和 final manifest。"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    run_logger = _build_run_logger(runtime)
    payload = _build_release_service(runtime).prepare_submission()
    run_logger.info("cli.finalize", "生成 submission 目录和 final manifest。", manifest=payload["final_manifest_json"])
    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"submission 根目录: {payload['submission_root']}")
    typer.echo(f"final_manifest.json: {payload['final_manifest_json']}")
    typer.echo(f"final_manifest.md: {payload['final_manifest_md']}")


@app.command("gate")
def gate(
    profile: Annotated[str | None, typer.Option("--profile", help="指定运行档位。")] = None,
    db_path: Annotated[str | None, typer.Option("--db-path", help="覆盖 SQLite 数据库路径。")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """执行第四阶段最终门禁检查。"""

    runtime = _load_runtime(profile=profile, db_path=db_path)
    run_logger = _build_run_logger(runtime)
    payload = _build_release_service(runtime).run_gate()
    run_logger.info("cli.gate", "执行最终门禁检查。", status=payload["status"], gate_report=payload["final_gate_json"])
    if json_output:
        _emit_json(payload)
        return

    typer.echo(f"总体状态: {payload['status']}")
    typer.echo(f"gate.json: {payload['final_gate_json']}")
    typer.echo(f"gate.md: {payload['final_gate_md']}")
    typer.echo(f"通过: {payload['summary']['passed']} / 带限制通过: {payload['summary']['limited']} / 未通过: {payload['summary']['failed']}")


@app.command("install-api-service")
def install_api_service_command(
    service_name: Annotated[str | None, typer.Option("--service-name", help="systemd 服务名。")] = None,
    host: Annotated[str | None, typer.Option("--host", help="API 服务监听地址。")] = None,
    port: Annotated[int | None, typer.Option("--port", help="API 服务监听端口。")] = None,
    enable: Annotated[bool, typer.Option("--enable/--no-enable", help="是否加入开机自启。")] = True,
    start: Annotated[bool, typer.Option("--start/--no-start", help="安装后是否立即启动。")] = True,
    timeout_sec: Annotated[int, typer.Option("--timeout-sec", help="等待健康检查通过的秒数。")] = 15,
    json_output: Annotated[bool, typer.Option("--json", help="以 JSON 输出，便于脚本解析。")] = False,
) -> None:
    """在 Linux 验证机上安装并启动 Web/API 的 systemd 服务。"""

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
            python_executable=Path(sys.executable).resolve(),
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
        "project_root": str(runtime.project_root),
        "service_name": final_service_name,
        "host": final_host,
        "port": final_port,
        "enable": enable,
        "start": start,
        "healthz": install_payload["healthz"],
        "console": install_payload["console"],
        "unit_path": install_payload["unit_path"],
        "ready": ready_payload["ready"] if ready_payload else False,
    }
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
    typer.echo(f"快照: {snapshot_path}")


@app.command("serve-api")
def serve_api(
    host: Annotated[str | None, typer.Option("--host", help="指定 API 监听地址。")] = None,
    port: Annotated[int | None, typer.Option("--port", help="指定 API 监听端口。")] = None,
    reload: Annotated[bool, typer.Option("--reload", help="开发阶段开启自动重载。")] = False,
) -> None:
    """启动 Web 控制台后端接口。"""

    # API 服务默认直接复用当前仓库里的 patchweaver.api.app，不再单独维护第二套启动脚本。
    import uvicorn

    runtime = _load_runtime()
    system_config = load_system_config(runtime.project_root)
    final_host = host or system_config.api_host
    final_port = port or system_config.api_port
    _build_run_logger(runtime).info("cli.serve_api", "启动 Web 控制台后端接口。", host=final_host, port=final_port, reload=reload)
    typer.echo(f"启动 PatchWeaver API: http://{final_host}:{final_port}")
    uvicorn.run("patchweaver.api.app:app", host=final_host, port=final_port, reload=reload)


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
