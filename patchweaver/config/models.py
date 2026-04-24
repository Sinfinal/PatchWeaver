"""命令行启动阶段使用的配置模型"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConfigModel(BaseModel):
    """基础配置模型，默认忽略暂未使用的字段"""

    model_config = ConfigDict(extra="ignore")


class SystemConfig(ConfigModel):
    """系统级基础配置"""

    # 这组字段主要决定单主工作区、数据库位置和最基础的运行约束
    # workspace_root、database_path、manifest_dir 都统一从源码根目录展开
    workspace_root: str = "workspaces"
    database_path: str = "data/patchweaver.db"
    default_kernel: str = "6.6.102-5.2.an23.x86_64"
    max_attempts: int = 5
    parallel_read_limit: int = 3
    write_lock_scope: Literal["task", "workspace", "global"] = "task"
    trace_mode: Literal["full", "compact"] = "full"
    manifest_dir: str = "data/manifests"
    report_formats: list[str] = Field(default_factory=lambda: ["json", "md"])
    api_host: str = "0.0.0.0"
    api_port: int = 18084
    api_service_name: str = "patchweaver-web"
    auto_install_api_service: bool = True


class ProfileSettings(ConfigModel):
    """运行档位的可选覆盖项"""

    # profile 只做策略覆盖，不复制 system.yaml 的全部字段
    max_attempts: int | None = None
    verification_profile: Literal["dev", "standard", "strict"] | None = None
    enable_semantic_guard: bool | None = None
    enable_regression: bool | None = None
    enable_context_dedup: bool | None = None
    track_token_cost: bool | None = None
    enable_narrow_failover: bool | None = None
    allow_readonly_subagent: bool | None = None
    enable_read_parallel: bool | None = None


class ProfilesConfig(ConfigModel):
    """按名称管理多套运行档位配置"""

    # 按名称索引 profile，CLI 侧直接通过 --profile 取值
    profiles: dict[str, ProfileSettings] = Field(default_factory=dict)


class BuildConfig(ConfigModel):
    """构建阶段使用的本机路径与命令配置"""

    # 当前工程固定采用“当前运行机本机构建”模式
    # 开发机与验证机之间只做代码同步，不再把验证机抽象成单独的构建后端
    build_backend: Literal["local"] = "local"
    clean_kernel_src_dir: str = ""
    prepared_kernel_src_dir: str = ""
    kernel_src_dir: str = "/opt/kernel-src"
    kernel_devel_dir: str = "/usr/src/kernels/6.6.102-5.2.an23.x86_64"
    patched_kernel_src_dir: str = ""
    build_source_priority: list[str] = Field(
        default_factory=lambda: [
            "clean_kernel_src_dir",
            "prepared_kernel_src_dir",
            "kernel_src_dir",
            "kernel_devel_dir",
            "patched_kernel_src_dir",
        ]
    )
    auto_switch_source_tree: bool = True
    auto_reverse_source_tree: bool = True
    vmlinux_path: str = "/usr/lib/debug/lib/modules/6.6.102-5.2.an23.x86_64/vmlinux"
    kpatch_build_cmd: str = "kpatch-build"
    build_timeout_sec: int = 3600


class VerifyConfig(ConfigModel):
    """热补丁验证阶段的开关配置"""

    # 验证开关保持独立，方便 dev/demo/full 三个档位按需组合
    verification_profile: Literal["dev", "standard", "strict"] = "standard"
    enable_semantic_guard: bool = True
    enable_load_test: bool = True
    enable_unload_test: bool = True
    enable_smoke_test: bool = True
    enable_regression: bool = False
    smoke_test_script: str = "scripts/validate_smoke.sh"


class PromptProfile(ConfigModel):
    """单套提示词约束与裁剪策略"""

    # 这一层主要控制提示词长度、结构化约束和上下文裁剪策略
    require_json_schema: bool = True
    max_evidence_snippets: int = 8
    max_memory_hits: int = 3
    suppress_duplicate_evidence: bool = True
    annotate_truncation: bool = True
    track_token_cost: bool = True
    allow_freeform_patch_output: bool = False


class PromptsConfig(ConfigModel):
    """提示词系统的全局配置"""

    default_prompt_profile: str = "strict"
    # bootstrap 目录按顺序注入，后面的片段可以补充前面的系统约束
    bootstrap_fragment_dirs: list[str] = Field(default_factory=lambda: ["prompts/system", "prompts/bootstrap"])
    record_bootstrap_manifest: bool = True
    prompt_profiles: dict[str, PromptProfile] = Field(default_factory=dict)


class SkillDirectories(ConfigModel):
    """Skill 来源目录配置"""

    # 来源目录拆开之后，后续路由器可以明确体现优先级和可见性边界
    project: str = "skills/project"
    shared: str = "skills/shared"
    builtin: str = "skills/builtin"


class SkillProfile(ConfigModel):
    """Skill 调度策略配置"""

    # skill profile 只负责调度边界，不直接承载任务主状态
    enable_skill_router: bool = True
    preferred_dispatch: str = "skill_first"
    fallback_dispatch: str = "direct_worker"
    enable_skill_fallback: bool = True
    allow_readonly_subagent: bool = True
    subagent_max_parallel: int = 2
    subagent_allowed_stages: list[str] = Field(default_factory=list)
    write_actions_via_harness_only: bool = True


class SkillsConfig(ConfigModel):
    """Skill 体系的全局配置"""

    default_skill_profile: str = "contest"
    # 同名 skill 的解析顺序在这里冻结，后续 doctor 和 router 共用
    skill_source_priority: list[str] = Field(default_factory=lambda: ["workspace", "project", "shared", "builtin"])
    require_manifest: bool = True
    enforce_allowlist: bool = True
    skill_dirs: SkillDirectories = Field(default_factory=SkillDirectories)
    skill_profiles: dict[str, SkillProfile] = Field(default_factory=dict)
    allowed_skill_tags: list[str] = Field(default_factory=lambda: ["contest", "core"])
    enabled_skills: list[str] = Field(default_factory=list)


class RulesConfig(ConfigModel):
    """规则库和 recipe 的入口配置"""

    # 规则目录和 recipe 入口先集中收在这里，便于后面按模块统一读取
    risk_rules_dir: str = "rules/risk_rules"
    patch_author_guide_dir: str = "rules/risk_rules/patch_author_guide"
    primitive_rules_dir: str = "rules/primitive_rules"
    livepatch_rule_dir: str = "rules/primitive_rules/livepatch"
    ranking_rules_dir: str = "rules/ranking_rules"
    default_recipe_manifest: str = "recipes/manifests/default.yaml"


class LoggingConfig(ConfigModel):
    """日志输出相关配置"""

    # 日志配置首版只区分文本日志、JSONL 和控制台展示
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file_path: str = "data/logs/patchweaver.log"
    console_rich: bool = True
    enable_jsonl: bool = True
    jsonl_path: str = "data/logs/patchweaver.jsonl"


class ModelsConfig(ConfigModel):
    """模型后端、主模型拓扑和辅助模型边界配置"""

    provider: Literal["bailian", "custom"] = "bailian"
    endpoint_mode: Literal["openai_compatible", "native"] = "openai_compatible"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key_env: str = "PATCHWEAVER_BAILIAN_API_KEY"
    api_key: str = ""
    topology: Literal["single_primary_with_optional_helpers"] = "single_primary_with_optional_helpers"
    default_model: str = "qwen-plus-2025-07-28"
    development_model: str = "qwen-plus-2025-07-28"
    delivery_model: str = "qwen-plus-2025-07-28"
    fallback_model: str = "qwen-plus-2025-07-28"
    helper_models: dict[str, str] = Field(
        default_factory=lambda: {
            "code_assistant": "qwen-coder-turbo-0919",
            "vision": "qwen-vl-plus-2025-05-07",
            "log_summary": "qwen-plus-2025-07-28",
        }
    )
    helper_notes: dict[str, str] = Field(
        default_factory=lambda: {
            "code_assistant": "用于草拟局部改写提示、模板和代码片段，不直接决定最终放行结果。",
            "vision": "用于截图识别、页面检查和演示材料辅助场景。",
            "log_summary": "用于长日志压缩、失败解释和材料摘要，不直接替代构建判定。",
        }
    )
    interaction_record_mode: Literal["off", "basic", "full"] = "basic"
    interaction_jsonl_path: str = "data/logs/model_interactions.jsonl"
    execution_boundaries: list[str] = Field(
        default_factory=lambda: [
            "模型负责语义分析、草拟和解释，最终执行判定仍由规则、原语、Recipe、构建和验证链负责。",
            "不采用多模型协同主执行链，不通过多模型投票决定是否放行构建或验证。",
            "辅助模型只用于解释增强、视觉辅助和摘要压缩，不直接负责最终 patch 定稿。",
        ]
    )

    @property
    def vision_model(self) -> str | None:
        """返回视觉辅助模型"""

        return self.helper_models.get("vision")

    def config_api_key_present(self) -> bool:
        """判断配置文件里是否显式写了 API Key"""

        return bool(self.api_key.strip())

    def resolve_api_key(self) -> str | None:
        """按环境变量优先、配置文件兜底解析 API Key"""

        env_value = os.getenv(self.api_key_env, "").strip()
        if env_value:
            return env_value

        config_value = self.api_key.strip()
        if config_value:
            return config_value
        return None

    def resolve_api_key_source(self) -> Literal["env", "config", "missing"]:
        """返回当前 API Key 的来源"""

        if os.getenv(self.api_key_env, "").strip():
            return "env"
        if self.api_key.strip():
            return "config"
        return "missing"

    def masked_api_key(self) -> str | None:
        """返回脱敏后的 API Key"""

        value = self.resolve_api_key()
        if value is None:
            return None
        if len(value) <= 8:
            if len(value) <= 2:
                return "*" * len(value)
            return f"{value[:1]}{'*' * (len(value) - 2)}{value[-1:]}"
        return f"{value[:4]}***{value[-4:]}"

    def api_key_status(self) -> dict[str, str | bool | None]:
        """输出可直接给 CLI 和接口复用的密钥状态"""

        return {
            "api_key_env": self.api_key_env,
            "api_key_ready": self.resolve_api_key() is not None,
            "api_key_source": self.resolve_api_key_source(),
            "api_key_masked": self.masked_api_key(),
            "api_key_in_config": self.config_api_key_present(),
        }

    def safe_model_payload(self) -> dict[str, object]:
        """输出不包含明文密钥的模型配置摘要"""

        payload = self.model_dump()
        payload["api_key"] = None
        payload.update(self.api_key_status())
        return payload


class ResolvedRuntime(ConfigModel):
    """命令行解析后的生效运行时快照"""

    # 这是 CLI 和后续 orchestrator 共用的生效运行时快照
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
