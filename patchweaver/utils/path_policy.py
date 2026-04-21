"""项目内统一的路径展示与持久化策略"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

_EXPLICIT_PATH_KEYS = {
    "project_root",
    "config_dir",
    "workspace_root",
    "workspace_dir",
    "database_path",
    "manifest_dir",
    "submission_root",
    "source_dir",
    "source_ref",
    "final_path",
    "detail_path",
    "root",
    "path",
    "unit_path",
}

_EXPLICIT_PATH_LIST_KEYS = {
    "bootstrap_dirs",
    "created_paths",
    "generated_files",
    "manifest_templates",
    "replay_files",
}


def ensure_within_root(root: Path, value: Path | str, *, label: str) -> Path:
    """确保路径位于指定根目录内，避免把产物写到项目外部"""

    resolved_root = root.resolve()
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.is_absolute() else (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} 必须位于 {resolved_root.as_posix()} 内，当前值为 {resolved.as_posix()}") from exc
    return resolved


def to_project_relative(project_root: Path | None, value: Path | str | None) -> str | None:
    """把项目内路径统一转换成相对源码根目录的表达"""

    if value is None:
        return None

    text = str(value).replace("\\", "/")
    candidate = Path(text)
    if project_root is None:
        return candidate.as_posix()

    root = project_root.resolve()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            return resolved.as_posix()
        return relative.as_posix() if relative.as_posix() else "."

    return candidate.as_posix()


def resolve_project_path(project_root: Path | None, value: Path | str | None) -> Path | None:
    """把已持久化的相对路径恢复为当前项目下可用的绝对路径"""

    if value is None:
        return None

    candidate = Path(value)
    if candidate.is_absolute() or project_root is None:
        return candidate.resolve()
    return (project_root.resolve() / candidate).resolve()


def relativize_payload(payload: Any, project_root: Path | None, *, field_name: str | None = None) -> Any:
    """递归把结构化数据中的项目内路径转换成相对路径"""

    if isinstance(payload, BaseModel):
        return relativize_payload(payload.model_dump(mode="json"), project_root, field_name=field_name)

    if isinstance(payload, Path):
        return to_project_relative(project_root, payload)

    if isinstance(payload, dict):
        return {
            key: relativize_payload(value, project_root, field_name=key)
            for key, value in payload.items()
        }

    if isinstance(payload, list):
        if field_name and _is_path_collection_field(field_name):
            return [
                to_project_relative(project_root, item) if isinstance(item, (Path, str)) else relativize_payload(item, project_root)
                for item in payload
            ]
        return [relativize_payload(item, project_root) for item in payload]

    if isinstance(payload, str) and field_name and _is_path_field(field_name):
        return to_project_relative(project_root, payload)

    return payload


def _is_path_field(field_name: str) -> bool:
    """判断字段名是否应按路径处理"""

    normalized = field_name.lower()
    return (
        normalized in _EXPLICIT_PATH_KEYS
        or normalized.endswith("_path")
        or normalized.endswith("_dir")
        or normalized.endswith("_root")
    )


def _is_path_collection_field(field_name: str) -> bool:
    """判断字段名是否为路径列表"""

    normalized = field_name.lower()
    return (
        normalized in _EXPLICIT_PATH_LIST_KEYS
        or normalized.endswith("_paths")
        or normalized.endswith("_dirs")
        or normalized.endswith("_roots")
        or normalized.endswith("_files")
    )
