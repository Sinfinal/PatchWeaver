"""命令行启动阶段使用的配置模型。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConfigModel(BaseModel):
    """基础配置模型，默认忽略暂未使用的字段。"""

    model_config = ConfigDict(extra="ignore")


class SystemConfig(ConfigModel):
    """系统级基础配置。"""

    # 这组字段主要决定单主工作区、数据库位置和最基础的运行约束。
    workspace_root: str = "workspaces"
    database_path: str = "data/patchweaver.db"
    default_kernel: str = "6.6.102-5.2.an23.x86_64"
    max_attempts: int = 5
    parallel_read_limit: int = 3
    write_lock_scope: Literal["task", "workspace", "global"] = "task"
    trace_mode: Literal["full", "compact"] = "full"
    manifest_dir: str = "data/manifests"
    report_formats: list[str] = Field(default_factory=lambda: ["json", "md"])


class ProfileSettings(ConfigModel):
    """运行档位的可选覆盖项。"""

    # profile 只做策略覆盖，不复制 system.yaml 的全部字段。
    max_attempts: int | None = None
    enable_semantic_guard: bool | None = None
    enable_regression: bool | None = None
    enable_context_dedup: bool | None = None
    track_token_cost: bool | None = None
    enable_narrow_failover: bool | None = None
    allow_readonly_subagent: bool | None = None
    enable_read_parallel: bool | None = None


class ProfilesConfig(ConfigModel):
    """按名称管理多套运行档位配置。"""

    # 按名称索引 profile，CLI 侧直接通过 --profile 取值。
    profiles: dict[str, ProfileSettings] = Field(default_factory=dict)


class BuildConfig(ConfigModel):
    """构建阶段使用的路径和命令配置。"""

    # 构建配置先只收束最关键的路径和命令，避免首版配置面过宽。
    kernel_src_dir: str = "/opt/kernel-src"
    kernel_devel_dir: str = "/usr/src/kernels/6.6.102-5.2.an23.x86_64"
    vmlinux_path: str = "/usr/lib/debug/lib/modules/6.6.102-5.2.an23.x86_64/vmlinux"
    kpatch_build_cmd: str = "kpatch-build"
    build_timeout_sec: int = 3600


class VerifyConfig(ConfigModel):
    """热补丁验证阶段的开关配置。"""

    # 验证开关保持独立，方便 dev/demo/full 三个档位按需组合。
    enable_load_test: bool = True
    enable_unload_test: bool = True
    enable_smoke_test: bool = True
    enable_regression: bool = False
    smoke_test_script: str = "scripts/validate_smoke.sh"


class PromptProfile(ConfigModel):
    """单套提示词约束与裁剪策略。"""

    # 这一层主要控制提示词长度、结构化约束和上下文裁剪策略。
    require_json_schema: bool = True
    max_evidence_snippets: int = 8
    max_memory_hits: int = 3
    suppress_duplicate_evidence: bool = True
    annotate_truncation: bool = True
    track_token_cost: bool = True
    allow_freeform_patch_output: bool = False


class PromptsConfig(ConfigModel):
    """提示词系统的全局配置。"""

    default_prompt_profile: str = "strict"
    # bootstrap 目录按顺序注入，后面的片段可以补充前面的系统约束。
    bootstrap_fragment_dirs: list[str] = Field(default_factory=lambda: ["prompts/system", "prompts/bootstrap"])
    record_bootstrap_manifest: bool = True
    prompt_profiles: dict[str, PromptProfile] = Field(default_factory=dict)


class SkillDirectories(ConfigModel):
    """Skill 来源目录配置。"""

    # 来源目录拆开之后，后续路由器可以明确体现优先级和可见性边界。
    project: str = "skills/project"
    shared: str = "skills/shared"
    builtin: str = "skills/builtin"


class SkillProfile(ConfigModel):
    """Skill 调度策略配置。"""

    # skill profile 只负责调度边界，不直接承载任务主状态。
    enable_skill_router: bool = True
    preferred_dispatch: str = "skill_first"
    fallback_dispatch: str = "direct_worker"
    enable_skill_fallback: bool = True
    allow_readonly_subagent: bool = True
    subagent_max_parallel: int = 2
    subagent_allowed_stages: list[str] = Field(default_factory=list)
    write_actions_via_harness_only: bool = True


class SkillsConfig(ConfigModel):
    """Skill 体系的全局配置。"""

    default_skill_profile: str = "contest"
    # 同名 skill 的解析顺序在这里冻结，后续 doctor 和 router 共用。
    skill_source_priority: list[str] = Field(default_factory=lambda: ["workspace", "project", "shared", "builtin"])
    require_manifest: bool = True
    enforce_allowlist: bool = True
    skill_dirs: SkillDirectories = Field(default_factory=SkillDirectories)
    skill_profiles: dict[str, SkillProfile] = Field(default_factory=dict)
    allowed_skill_tags: list[str] = Field(default_factory=lambda: ["contest", "core"])
    enabled_skills: list[str] = Field(default_factory=list)


class RulesConfig(ConfigModel):
    """规则库和 recipe 的入口配置。"""

    # 规则目录和 recipe 入口先集中收在这里，便于后面按模块统一读取。
    risk_rules_dir: str = "rules/risk_rules"
    patch_author_guide_dir: str = "rules/risk_rules/patch_author_guide"
    primitive_rules_dir: str = "rules/primitive_rules"
    livepatch_rule_dir: str = "rules/primitive_rules/livepatch"
    ranking_rules_dir: str = "rules/ranking_rules"
    default_recipe_manifest: str = "recipes/manifests/default.yaml"


class LoggingConfig(ConfigModel):
    """日志输出相关配置。"""

    # 日志配置首版只区分文本日志、JSONL 和控制台展示。
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file_path: str = "data/logs/patchweaver.log"
    console_rich: bool = True
    enable_jsonl: bool = True
    jsonl_path: str = "data/logs/patchweaver.jsonl"


class ResolvedRuntime(ConfigModel):
    """命令行解析后的生效运行时快照。"""

    # 这是 CLI 和后续 orchestrator 共用的生效运行时快照。
    project_root: Path
    config_dir: Path
    data_dir: Path
    workspace_root: Path
    database_path: Path
    manifest_dir: Path
    default_kernel: str
    max_attempts: int
    parallel_read_limit: int
    write_lock_scope: str
    trace_mode: str
    profile_name: str | None = None
    enable_narrow_failover: bool = False
    enable_read_parallel: bool = False
