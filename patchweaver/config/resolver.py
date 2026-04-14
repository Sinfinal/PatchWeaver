"""运行时配置解析。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.config.loader import (
    discover_project_root,
    load_build_config,
    load_profiles_config,
    load_prompts_config,
    load_skills_config,
    load_system_config,
    load_verify_config,
)
from patchweaver.config.models import ProfileSettings, PromptsConfig, ResolvedRuntime, SkillsConfig, VerifyConfig


def _resolve_path(project_root: Path, raw_path: str) -> Path:
    """把配置路径解析为可直接使用的绝对路径。"""
    # 运行时统一把相对路径换成绝对路径，后续模块直接使用即可。
    candidate = Path(raw_path)
    return candidate if candidate.is_absolute() else (project_root / candidate)


def resolve_profile_settings(*, project_root: Path | None = None, profile_name: str | None = None) -> ProfileSettings | None:
    """读取指定运行档位的配置。"""

    root = discover_project_root(project_root)
    if not profile_name:
        return None

    profiles = load_profiles_config(root)
    profile = profiles.profiles.get(profile_name)
    if profile is None:
        raise ValueError(f"未知运行档位：{profile_name}")
    return profile


def apply_profile_overrides(
    *,
    profile: ProfileSettings | None,
    verify_config: VerifyConfig,
    prompts_config: PromptsConfig,
    skills_config: SkillsConfig,
) -> tuple[VerifyConfig, PromptsConfig, SkillsConfig]:
    """把运行档位中的行为开关覆盖到各子系统配置上。"""

    resolved_verify = verify_config.model_copy(deep=True)
    resolved_prompts = prompts_config.model_copy(deep=True)
    resolved_skills = skills_config.model_copy(deep=True)

    if profile is None:
        return resolved_verify, resolved_prompts, resolved_skills

    if profile.enable_semantic_guard is not None:
        resolved_verify.enable_semantic_guard = profile.enable_semantic_guard
    if profile.enable_regression is not None:
        resolved_verify.enable_regression = profile.enable_regression

    for prompt_name, prompt_profile in resolved_prompts.prompt_profiles.items():
        updated = prompt_profile.model_copy(deep=True)
        if profile.enable_context_dedup is not None:
            updated.suppress_duplicate_evidence = profile.enable_context_dedup
        if profile.track_token_cost is not None:
            updated.track_token_cost = profile.track_token_cost
        resolved_prompts.prompt_profiles[prompt_name] = updated

    if resolved_skills.skill_profiles:
        skill_profile_names = [resolved_skills.default_skill_profile]
        if resolved_skills.default_skill_profile not in resolved_skills.skill_profiles:
            skill_profile_names = list(resolved_skills.skill_profiles)
        for skill_profile_name in skill_profile_names:
            current = resolved_skills.skill_profiles.get(skill_profile_name)
            if current is None:
                continue
            updated = current.model_copy(deep=True)
            if profile.allow_readonly_subagent is not None:
                updated.allow_readonly_subagent = profile.allow_readonly_subagent
                if not profile.allow_readonly_subagent:
                    updated.subagent_allowed_stages = []
            resolved_skills.skill_profiles[skill_profile_name] = updated

    return resolved_verify, resolved_prompts, resolved_skills


def load_effective_configs(*, project_root: Path | None = None, profile_name: str | None = None) -> dict[str, object]:
    """读取并返回应用档位覆盖后的主配置集合。"""

    root = discover_project_root(project_root)
    profile = resolve_profile_settings(project_root=root, profile_name=profile_name)
    verify_config, prompts_config, skills_config = apply_profile_overrides(
        profile=profile,
        verify_config=load_verify_config(root),
        prompts_config=load_prompts_config(root),
        skills_config=load_skills_config(root),
    )
    return {
        "build": load_build_config(root),
        "verify": verify_config,
        "prompts": prompts_config,
        "skills": skills_config,
    }


def resolve_runtime(
    *,
    project_root: Path | None = None,
    profile_name: str | None = None,
    cli_database_path: str | None = None,
    cli_max_attempts: int | None = None,
) -> ResolvedRuntime:
    """按命令行、档位和配置文件的优先级解析运行参数。"""

    root = discover_project_root(project_root)
    system = load_system_config(root)
    profiles = load_profiles_config(root)

    profile = None
    if profile_name:
        # profile 不存在时直接失败，避免悄悄退回默认配置造成排查困难。
        profile = profiles.profiles.get(profile_name)
        if profile is None:
            raise ValueError(f"未知运行档位：{profile_name}")

    # 优先级固定为 CLI > 运行档位 > system.yaml，避免不同入口解析结果不一致。
    effective_max_attempts = cli_max_attempts
    if effective_max_attempts is None and profile and profile.max_attempts is not None:
        effective_max_attempts = profile.max_attempts
    if effective_max_attempts is None:
        effective_max_attempts = system.max_attempts

    # 数据库路径允许 CLI 直接覆盖，便于联调时切换临时库。
    database_path = cli_database_path or system.database_path

    # failover 只作为窄状态开关保留在运行时里，不在这里扩展更多行为。
    enable_narrow_failover = False
    if profile and profile.enable_narrow_failover is not None:
        enable_narrow_failover = profile.enable_narrow_failover

    # 当前并发开关只允许档位配置覆盖，便于区分不同运行模式。
    enable_read_parallel = False
    if profile and profile.enable_read_parallel is not None:
        enable_read_parallel = profile.enable_read_parallel

    return ResolvedRuntime(
        project_root=root,
        config_dir=root / "config",
        data_dir=root / "data",
        workspace_root=_resolve_path(root, system.workspace_root).resolve(),
        database_path=_resolve_path(root, database_path).resolve(),
        manifest_dir=_resolve_path(root, system.manifest_dir).resolve(),
        default_kernel=system.default_kernel,
        max_attempts=effective_max_attempts,
        parallel_read_limit=system.parallel_read_limit,
        write_lock_scope=system.write_lock_scope,
        trace_mode=system.trace_mode,
        profile_name=profile_name,
        enable_narrow_failover=enable_narrow_failover,
        enable_read_parallel=enable_read_parallel,
    )
