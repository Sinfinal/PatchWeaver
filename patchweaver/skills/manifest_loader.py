"""Skill manifest 解析。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from patchweaver.models.skill import SkillManifest


def load_skill_manifest(manifest_path: Path, *, source_layer: str) -> SkillManifest:
    """从 YAML 文件读取 skill manifest。"""

    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    entry = raw.get("entry") or {}
    return SkillManifest(
        skill_name=raw.get("name", manifest_path.parent.name),
        source_layer=source_layer,
        visibility=str(raw.get("visibility", source_layer)),
        preferred_rank=int(raw.get("priority", 100)),
        readonly=bool(raw.get("readonly", True)),
        allow_readonly_subagent=bool(raw.get("allow_readonly_subagent", False)),
        allowed_tags=list(raw.get("tags") or []),
        input_schema=_to_optional_str(raw.get("input_schema")),
        output_schema=_to_optional_str(raw.get("output_schema")),
        input_contract=[str(item) for item in raw.get("input_contract") or []],
        output_contract=[str(item) for item in raw.get("output_contract") or []],
        evidence_tags=[str(item) for item in raw.get("evidence_tags") or []],
        tool_allowlist=[str(item) for item in raw.get("tool_allowlist") or []],
        entry_kind=str(entry.get("kind", "placeholder")),
        stage_name=str(entry.get("stage", manifest_path.parent.name)),
        description=str(raw.get("description", "")),
        enabled=bool(raw.get("enabled", False)),
        manifest_path=str(manifest_path),
    )


def _to_optional_str(value: Any) -> str | None:
    """把空值安全地转换为可选字符串。"""

    if value is None:
        return None
    return str(value)
