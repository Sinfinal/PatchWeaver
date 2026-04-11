"""Skill 注册中心。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.config.loader import load_skills_config
from patchweaver.models.skill import SkillManifest
from patchweaver.skills.allowlist import is_skill_allowed
from patchweaver.skills.manifest_loader import load_skill_manifest
from patchweaver.skills.source_policy import resolve_skill_roots


class SkillRegistry:
    """负责扫描并缓存可用 skill manifest。"""

    def __init__(self, project_root: Path) -> None:
        """记录项目根目录。"""

        self.project_root = project_root

    def discover(self) -> list[SkillManifest]:
        """扫描当前项目可见的 skill manifest。"""

        skills_config = load_skills_config(self.project_root)
        enabled_skills = set(skills_config.enabled_skills)
        manifests: list[SkillManifest] = []
        for source_layer, root in resolve_skill_roots(self.project_root):
            if not root.exists():
                continue
            # 这里按来源优先级顺序扫描，同名 skill 的覆盖关系就落在遍历顺序上了。
            for manifest_path in sorted(root.glob("*/manifest.yaml")):
                manifest = load_skill_manifest(manifest_path, source_layer=source_layer)
                # manifest 自身开关和 config 总开关都要过，避免测试目录里的半成品混进主链。
                if not manifest.enabled:
                    continue
                if enabled_skills and manifest.skill_name not in enabled_skills:
                    continue
                if is_skill_allowed(self.project_root, manifest):
                    manifests.append(manifest)
        return manifests

    def find_by_stage(self, stage_name: str) -> list[SkillManifest]:
        """读取某一阶段可见的 skill 列表。"""

        return [manifest for manifest in self.discover() if manifest.stage_name == stage_name]
