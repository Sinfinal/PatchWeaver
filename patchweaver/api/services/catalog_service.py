"""规则、配方、Skill 和 Prompt 目录查询服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.skills.manifest_loader import load_skill_manifest
from patchweaver.skills.source_policy import resolve_skill_roots


class CatalogService:
    """负责汇总工程侧静态资产目录。"""

    def __init__(self, context: ApiContext) -> None:
        """保存 API 共享上下文。"""

        self.context = context

    def list_rules(self) -> dict[str, Any]:
        """返回规则库与配方目录摘要。"""

        rules_config = self.context.rules_config
        project_root = self.context.project_root
        sections = {
            "risk_rules": self._scan_dir(project_root / rules_config.risk_rules_dir),
            "patch_author_guide": self._scan_dir(project_root / rules_config.patch_author_guide_dir),
            "primitive_rules": self._scan_dir(project_root / rules_config.primitive_rules_dir),
            "livepatch_rules": self._scan_dir(project_root / rules_config.livepatch_rule_dir),
            "ranking_rules": self._scan_dir(project_root / rules_config.ranking_rules_dir),
            "recipe_templates": self._scan_dir(project_root / "recipes" / "templates"),
            "recipe_manifests": self._scan_dir(project_root / "recipes" / "manifests"),
            "smpl_templates": self._scan_dir(project_root / "recipes" / "smpl"),
        }
        return {
            "sections": sections,
            "summary": {name: len(section["files"]) for name, section in sections.items()},
        }

    def list_skills(self) -> dict[str, Any]:
        """扫描 Skill 清单。"""

        entries: list[dict[str, Any]] = []
        for source_layer, root in resolve_skill_roots(self.context.project_root):
            manifests = sorted(root.glob("*/manifest.yaml")) if root.exists() else []
            for manifest_path in manifests:
                manifest = load_skill_manifest(manifest_path, source_layer=source_layer)
                entries.append(
                    {
                        "skill_name": manifest.skill_name,
                        "stage_name": manifest.stage_name,
                        "source_layer": manifest.source_layer,
                        "visibility": manifest.visibility,
                        "enabled": manifest.enabled,
                        "entry_kind": manifest.entry_kind,
                        "description": manifest.description,
                        "manifest_path": manifest.manifest_path,
                    }
                )
        return {
            "source_priority": self.context.skills_config.skill_source_priority,
            "enabled_skills": self.context.skills_config.enabled_skills,
            "entries": sorted(entries, key=lambda item: (item["stage_name"], item["skill_name"], item["source_layer"])),
        }

    def list_prompts(self) -> dict[str, Any]:
        """返回 Prompt 目录与配置摘要。"""

        prompt_root = self.context.project_root / "prompts"
        sections = {
            "system": self._scan_dir(prompt_root / "system"),
            "bootstrap": self._scan_dir(prompt_root / "bootstrap"),
            "stages": self._scan_dir(prompt_root / "stages"),
            "workers": self._scan_dir(prompt_root / "workers"),
            "contracts": self._scan_dir(prompt_root / "contracts"),
        }
        return {
            "default_prompt_profile": self.context.prompts_config.default_prompt_profile,
            "bootstrap_fragment_dirs": self.context.prompts_config.bootstrap_fragment_dirs,
            "sections": sections,
        }

    def list_settings(self) -> dict[str, Any]:
        """输出几类主要配置，便于控制台查看。"""

        return {
            "system": self.context.system_config.model_dump(),
            "build": self.context.build_config.model_dump(),
            "verify": self.context.verify_config.model_dump(),
            "prompts": self.context.prompts_config.model_dump(),
            "skills": self.context.skills_config.model_dump(),
            "rules": self.context.rules_config.model_dump(),
            "logging": self.context.logging_config.model_dump(),
        }

    def _scan_dir(self, path: Path) -> dict[str, Any]:
        """递归扫描目录中的文件。"""

        files: list[dict[str, Any]] = []
        if path.exists():
            for file_path in sorted(path.rglob("*")):
                if file_path.is_dir():
                    continue
                files.append(
                    {
                        "name": file_path.name,
                        "relative_path": str(file_path.relative_to(self.context.project_root)).replace("\\", "/"),
                        "size": file_path.stat().st_size,
                    }
                )
        return {
            "path": str(path),
            "exists": path.exists(),
            "files": files,
        }
