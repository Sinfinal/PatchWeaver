"""配置文件加载工具"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

from patchweaver.config.models import (
    BuildConfig,
    LoggingConfig,
    ModelsConfig,
    ProfilesConfig,
    PromptsConfig,
    RagConfig,
    RulesConfig,
    SkillsConfig,
    SystemConfig,
    VerifyConfig,
)

T = TypeVar("T", bound=BaseModel)
_UNSET = object()


def discover_project_root(start: Path | None = None) -> Path:
    """自当前路径向上查找仓库根目录"""

    current = (start or Path(__file__).resolve()).resolve()
    search_root = current if current.is_dir() else current.parent

    # 同时命中 pyproject.toml 和主包目录时，认为已经回到了项目根目录
    for candidate in (search_root, *search_root.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "patchweaver").exists():
            return candidate

    raise FileNotFoundError("无法从当前路径定位 PatchWeaver 项目根目录。")


def config_path(project_root: Path, filename: str) -> Path:
    """拼接配置文件的标准路径"""
    # 配置目录先统一约定在仓库根的 config/ 下，避免调用方自己拼路径
    return project_root / "config" / filename


def read_yaml_file(path: Path) -> dict[str, Any]:
    """读取 YAML 配置文件"""
    if not path.exists():
        raise FileNotFoundError(f"缺少配置文件：{path}")

    # 空文件按空映射处理，方便逐步补齐配置而不至于直接报错
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"配置文件内容必须是 YAML 映射结构：{path}")
    return raw


def load_model(path: Path, model_cls: type[T]) -> T:
    """按模型类型加载并校验配置"""
    # 所有配置模型都走同一层校验，字段缺省和类型转换交给 pydantic 处理
    return model_cls.model_validate(read_yaml_file(path))


def load_system_config(project_root: Path | None = None) -> SystemConfig:
    """加载 system.yaml"""
    # 下面这组加载函数保持扁平，命令层调用时更直观
    root = discover_project_root(project_root)
    return load_model(config_path(root, "system.yaml"), SystemConfig)


def load_profiles_config(project_root: Path | None = None) -> ProfilesConfig:
    """加载 profiles.yaml"""
    root = discover_project_root(project_root)
    return load_model(config_path(root, "profiles.yaml"), ProfilesConfig)


def load_build_config(project_root: Path | None = None) -> BuildConfig:
    """加载 build.yaml"""
    root = discover_project_root(project_root)
    return load_model(config_path(root, "build.yaml"), BuildConfig)


def load_verify_config(project_root: Path | None = None) -> VerifyConfig:
    """加载 verify.yaml"""
    root = discover_project_root(project_root)
    return load_model(config_path(root, "verify.yaml"), VerifyConfig)


def load_prompts_config(project_root: Path | None = None) -> PromptsConfig:
    """加载 prompts.yaml"""
    root = discover_project_root(project_root)
    return load_model(config_path(root, "prompts.yaml"), PromptsConfig)


def load_skills_config(project_root: Path | None = None) -> SkillsConfig:
    """加载 skills.yaml"""
    root = discover_project_root(project_root)
    return load_model(config_path(root, "skills.yaml"), SkillsConfig)


def load_rules_config(project_root: Path | None = None) -> RulesConfig:
    """加载 rules.yaml"""
    root = discover_project_root(project_root)
    return load_model(config_path(root, "rules.yaml"), RulesConfig)


def load_logging_config(project_root: Path | None = None) -> LoggingConfig:
    """加载 logging.yaml"""
    root = discover_project_root(project_root)
    return load_model(config_path(root, "logging.yaml"), LoggingConfig)


def load_models_config(project_root: Path | None = None) -> ModelsConfig:
    """加载 models.yaml"""

    root = discover_project_root(project_root)
    return load_model(config_path(root, "models.yaml"), ModelsConfig)


def load_rag_config(project_root: Path | None = None) -> RagConfig:
    """加载 rag.yaml"""

    root = discover_project_root(project_root)
    return load_model(config_path(root, "rag.yaml"), RagConfig)


def _render_yaml_scalar(value: str) -> str:
    """把字符串渲染成安全的 YAML 标量"""

    return json.dumps(value, ensure_ascii=False)


def _replace_top_level_scalar(text: str, *, key: str, value: str, after_key: str | None = None) -> str:
    """更新顶层标量字段，并尽量保留原文件结构"""

    lines = text.splitlines()
    rendered_line = f"{key}: {_render_yaml_scalar(value)}"
    key_pattern = re.compile(rf"^{re.escape(key)}\s*:")

    for index, line in enumerate(lines):
        if key_pattern.match(line):
            lines[index] = rendered_line
            return "\n".join(lines).rstrip() + "\n"

    insert_at = len(lines)
    if after_key is not None:
        anchor_pattern = re.compile(rf"^{re.escape(after_key)}\s*:")
        for index, line in enumerate(lines):
            if anchor_pattern.match(line):
                insert_at = index + 1
                break

    lines.insert(insert_at, rendered_line)
    return "\n".join(lines).rstrip() + "\n"


def save_models_api_settings(
    project_root: Path | None = None,
    *,
    api_key: str | object = _UNSET,
    api_key_env: str | object = _UNSET,
) -> Path:
    """更新 models.yaml 里的 API Key 相关字段"""

    root = discover_project_root(project_root)
    path = config_path(root, "models.yaml")
    text = path.read_text(encoding="utf-8")

    if api_key_env is not _UNSET:
        text = _replace_top_level_scalar(text, key="api_key_env", value=str(api_key_env), after_key="base_url")

    if api_key is not _UNSET:
        text = _replace_top_level_scalar(text, key="api_key", value=str(api_key), after_key="api_key_env")

    path.write_text(text, encoding="utf-8")
    return path
