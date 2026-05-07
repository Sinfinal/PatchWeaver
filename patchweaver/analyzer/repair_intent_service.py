"""RepairIntent 生成逻辑"""

from __future__ import annotations

import re

from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import RepairIntent, SemanticCard


class RepairIntentBuilder:
    """从语义卡片和补丁文本生成可执行修复意图"""

    def build(
        self,
        *,
        patch_bundle: PatchBundle,
        semantic_card: SemanticCard,
        patch_text: str,
    ) -> RepairIntent:
        """生成 RepairIntent 产物"""

        guard_conditions = self._ordered_unique(
            [
                *semantic_card.must_keep_conditions,
                *self._extract_added_conditions(patch_text),
            ]
        )
        safe_exits = self._ordered_unique(self._extract_safe_exits(patch_text))
        touched_state = self._ordered_unique(self._extract_touched_state(patch_text))
        preserved_side_effects = self._ordered_unique(
            [
                *semantic_card.must_keep_side_effects,
                *self._extract_guarded_side_effects(patch_text),
            ]
        )
        strategy = self._strategy(
            guard_conditions=guard_conditions,
            safe_exits=safe_exits,
            preserved_side_effects=preserved_side_effects,
            touched_state=touched_state,
        )
        evidence = self._evidence(
            guard_conditions=guard_conditions,
            safe_exits=safe_exits,
            preserved_side_effects=preserved_side_effects,
            touched_state=touched_state,
            strategy=strategy,
        )

        return RepairIntent(
            cve_id=patch_bundle.cve_id,
            bug_class=semantic_card.bug_class,
            root_cause=semantic_card.root_cause,
            vulnerability_conditions=list(semantic_card.must_keep_conditions),
            guard_conditions=guard_conditions,
            guard_sites=list(semantic_card.touched_functions),
            safe_exits=safe_exits,
            preserved_side_effects=preserved_side_effects,
            touched_files=list(semantic_card.touched_files or patch_bundle.affected_files),
            touched_functions=list(semantic_card.touched_functions),
            touched_state=touched_state,
            recommended_strategy=strategy,
            confidence=self._confidence(
                guard_conditions=guard_conditions,
                safe_exits=safe_exits,
                preserved_side_effects=preserved_side_effects,
                touched_state=touched_state,
            ),
            evidence=evidence,
        )

    def _extract_added_conditions(self, patch_text: str) -> list[str]:
        """抽取新增 guard 条件"""

        conditions: list[str] = []
        for raw_line in patch_text.splitlines():
            if not raw_line.startswith("+") or raw_line.startswith("+++"):
                continue
            line = raw_line[1:].strip()
            match = re.search(r"\bif\s*\((?P<condition>.+)\)", line)
            if not match:
                continue
            condition = match.group("condition").strip()
            if condition:
                conditions.append(condition)
        return conditions

    def _extract_safe_exits(self, patch_text: str) -> list[str]:
        """抽取新增安全退出路径"""

        exits: list[str] = []
        for raw_line in patch_text.splitlines():
            if not raw_line.startswith("+") or raw_line.startswith("+++"):
                continue
            line = raw_line[1:].strip()
            if re.search(r"\breturn\b", line) or re.search(r"\bgoto\b", line):
                exits.append(line)
            elif line in {"break;", "continue;"}:
                exits.append(line)
        return exits

    def _extract_guarded_side_effects(self, patch_text: str) -> list[str]:
        """抽取 guard 分支内必须保留的副作用"""

        side_effects: list[str] = []
        in_added_guard = False
        brace_depth = 0
        for raw_line in patch_text.splitlines():
            if not raw_line.startswith("+") or raw_line.startswith("+++"):
                continue
            line = raw_line[1:].strip()
            if re.search(r"\bif\s*\(", line):
                in_added_guard = True
                brace_depth = line.count("{") - line.count("}")
                continue
            if not in_added_guard:
                continue
            if self._looks_side_effect(line):
                side_effects.append(line)
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0 and line.endswith("}"):
                in_added_guard = False
        return side_effects

    def _looks_side_effect(self, line: str) -> bool:
        """识别函数调用或赋值这类需要保留的副作用"""

        if not line or line.startswith(("/*", "*", "//")):
            return False
        if re.search(r"\breturn\b|\bgoto\b", line) or line in {"break;", "continue;"}:
            return False
        return bool(re.search(r"\w+\s*\(", line) or re.search(r"(?<![=!<>])=(?!=)", line))

    def _extract_touched_state(self, patch_text: str) -> list[str]:
        """识别可能需要 callback/shadow 的状态改动"""

        markers: list[str] = []
        for raw_line in patch_text.splitlines():
            if not raw_line.startswith(("+", "-")) or raw_line.startswith(("+++", "---")):
                continue
            line = raw_line[1:].strip()
            lowered = line.lower()
            if re.match(r"^(typedef\s+)?(struct|enum|union)\s+\w+", line):
                markers.append("type_definition_change")
            if re.match(r"^static\s+(?!inline\b).*(=|;|\[)", line):
                markers.append("static_or_global_data_change")
            if any(token in lowered for token in ["__init", "__exit", "module_", "export_symbol"]):
                markers.append("section_or_module_lifecycle_change")
        return markers

    def _strategy(
        self,
        *,
        guard_conditions: list[str],
        safe_exits: list[str],
        preserved_side_effects: list[str],
        touched_state: list[str],
    ) -> str:
        """根据意图信号选择默认 livepatch 策略"""

        if guard_conditions and (safe_exits or preserved_side_effects) and not touched_state:
            return "semantic_guard"
        if touched_state:
            return "callback_shadow"
        return "direct_apply"

    def _confidence(
        self,
        *,
        guard_conditions: list[str],
        safe_exits: list[str],
        preserved_side_effects: list[str],
        touched_state: list[str],
    ) -> float:
        """给当前意图抽取一个保守置信度"""

        score = 0.35
        if guard_conditions:
            score += 0.25
        if safe_exits:
            score += 0.2
        if preserved_side_effects:
            score += 0.12
        if touched_state:
            score -= 0.15
        return max(0.0, min(1.0, round(score, 2)))

    def _evidence(
        self,
        *,
        guard_conditions: list[str],
        safe_exits: list[str],
        preserved_side_effects: list[str],
        touched_state: list[str],
        strategy: str,
    ) -> list[str]:
        """整理 RepairIntent 的证据摘要"""

        evidence: list[str] = []
        if guard_conditions:
            evidence.append("guard 条件: " + " | ".join(guard_conditions[:3]))
        if safe_exits:
            evidence.append("安全退出: " + " | ".join(safe_exits[:3]))
        if preserved_side_effects:
            evidence.append("保留副作用: " + " | ".join(preserved_side_effects[:3]))
        if touched_state:
            evidence.append("状态改动: " + ", ".join(touched_state[:3]))
        evidence.append(f"推荐策略: {strategy}")
        return evidence

    def _ordered_unique(self, items: list[str]) -> list[str]:
        """保持原顺序去重"""

        return [item for item in dict.fromkeys(str(item).strip() for item in items) if item]
