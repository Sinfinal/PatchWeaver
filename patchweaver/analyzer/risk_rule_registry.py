"""风险规则注册表"""

from __future__ import annotations

import re
from pathlib import Path

from patchweaver.config.loader import discover_project_root, load_rules_config, read_yaml_file
from patchweaver.models.constraint import RiskItem
from patchweaver.models.patch import PatchBundle


class RiskRuleRegistry:
    """负责提供 MVP 阶段的最小风险规则"""

    def __init__(self, project_root: Path | None = None) -> None:
        """初始化规则目录"""

        self.project_root = discover_project_root(project_root)
        self.rules_config = load_rules_config(self.project_root)
        self.risk_rules_dir = (self.project_root / self.rules_config.risk_rules_dir).resolve()

    def evaluate(self, patch_bundle: PatchBundle) -> list[RiskItem]:
        """根据补丁信息生成基础风险项"""

        patch_text = self._read_patch_text(patch_bundle)
        affected_files = patch_bundle.affected_files or []
        items: list[RiskItem] = []

        for rule_path in sorted(self.risk_rules_dir.glob("*.yaml")):
            raw = read_yaml_file(rule_path)
            if not raw:
                continue
            if not self._matches(raw.get("detection") or {}, patch_text, affected_files):
                continue
            risk_type = str(raw.get("id") or rule_path.stem)
            items.append(
                RiskItem(
                    risk_type=risk_type,
                    severity=str(raw.get("severity", "medium")),
                    evidence=self._build_evidence(risk_type=risk_type, affected_files=affected_files, patch_text=patch_text),
                    affected_functions=self._affected_functions(affected_files),
                    required_primitives=[str(item) for item in raw.get("primitive") or []],
                )
            )

        if items:
            return items
        if affected_files:
            return [
                RiskItem(
                    risk_type="unknown_patchability",
                    severity="low",
                    evidence=[f"涉及文件: {path}" for path in affected_files],
                    affected_functions=self._affected_functions(affected_files),
                    required_primitives=["wrapper"],
                )
            ]
        return []

    def _read_patch_text(self, patch_bundle: PatchBundle) -> str:
        """读取 patch 文本"""

        source_path = patch_bundle.normalized_patch_path or patch_bundle.raw_patch_path
        if source_path is None or not source_path.exists():
            return ""
        return source_path.read_text(encoding="utf-8")

    def _matches(self, detection: dict[str, object], patch_text: str, affected_files: list[str]) -> bool:
        """判断单条规则是否命中"""

        kind = str(detection.get("kind") or "")
        if kind == "patch_shape":
            requires = [str(item) for item in detection.get("requires") or []]
            return all(self._patch_shape_match(item, patch_text) for item in requires)
        if kind == "regex_any":
            patterns = [str(item) for item in detection.get("patterns") or []]
            return any(re.search(pattern, patch_text, flags=re.IGNORECASE | re.MULTILINE) for pattern in patterns)
        if kind == "path_regex":
            patterns = [str(item) for item in detection.get("patterns") or []]
            return any(re.search(pattern, path, flags=re.IGNORECASE) for pattern in patterns for path in affected_files)
        if kind == "content_keywords":
            keywords = [str(item).lower() for item in detection.get("keywords") or []]
            lowered = patch_text.lower()
            return all(keyword in lowered for keyword in keywords)
        return False

    def _patch_shape_match(self, requirement: str, patch_text: str) -> bool:
        """判断 patch 形态条件"""

        if requirement == "unified_hunks":
            return "@@" in patch_text
        return requirement in patch_text

    def _build_evidence(self, *, risk_type: str, affected_files: list[str], patch_text: str) -> list[str]:
        """生成风险证据摘要"""

        evidence = [f"规则命中: {risk_type}"]
        evidence.extend(f"涉及文件: {path}" for path in affected_files[:3])
        if patch_text:
            excerpt = patch_text.replace("\r\n", "\n").splitlines()[:6]
            evidence.append("patch 摘要: " + " | ".join(excerpt[:3]))
        return evidence

    def _affected_functions(self, affected_files: list[str]) -> list[str]:
        """用文件名生成最小受影响函数占位"""

        return [Path(path).stem for path in affected_files[:3]]
