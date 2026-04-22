"""风险规则注册表"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from patchweaver.config.loader import discover_project_root, load_rules_config, read_yaml_file
from patchweaver.models.constraint import RiskItem
from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard


@dataclass(slots=True)
class _ChangedLine:
    """表示补丁中的单条变更行"""

    file_path: str
    hunk_header: str
    marker: str
    text: str


class RiskRuleRegistry:
    """负责加载并执行热补丁约束规则"""

    def __init__(self, project_root: Path | None = None) -> None:
        """初始化规则目录"""

        self.project_root = discover_project_root(project_root)
        self.rules_config = load_rules_config(self.project_root)
        self.risk_rules_dir = (self.project_root / self.rules_config.risk_rules_dir).resolve()

    def evaluate(
        self,
        patch_bundle: PatchBundle,
        *,
        semantic_card: SemanticCard | None = None,
    ) -> list[RiskItem]:
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
            risk_item = RiskItem(
                risk_type=risk_type,
                severity=str(raw.get("severity", "medium")),
                summary=str(raw.get("description") or ""),
                source_rule=rule_path.stem,
                evidence=self._build_evidence(
                    risk_type=risk_type,
                    affected_files=affected_files,
                    patch_text=patch_text,
                    semantic_card=semantic_card,
                ),
                affected_files=affected_files[:3],
                affected_functions=self._affected_functions(semantic_card),
                affected_conditions=self._affected_conditions(semantic_card),
                critical_calls=self._critical_calls(semantic_card),
                required_primitives=[str(item) for item in raw.get("primitive") or []],
                forbidden_actions=[str(item) for item in raw.get("forbidden_actions") or []],
            )
            if risk_type == "direct_apply_ready":
                continue
            items.append(risk_item)

        if items:
            return items
        if self.direct_apply_ready(patch_bundle):
            return []
        if affected_files:
            return [
                RiskItem(
                    risk_type="unknown_patchability",
                    severity="low",
                    summary="当前规则库未命中明确约束，需要继续结合 apply 预检查、构建日志和验证结果判断",
                    source_rule="fallback",
                    evidence=self._build_evidence(
                        risk_type="unknown_patchability",
                        affected_files=affected_files,
                        patch_text=patch_text,
                        semantic_card=semantic_card,
                    ),
                    affected_files=affected_files[:3],
                    affected_functions=self._affected_functions(semantic_card),
                    affected_conditions=self._affected_conditions(semantic_card),
                    critical_calls=self._critical_calls(semantic_card),
                    required_primitives=["wrapper"],
                    forbidden_actions=[],
                )
            ]
        return []

    def direct_apply_ready(self, patch_bundle: PatchBundle) -> bool:
        """判断补丁是否满足 direct apply 预检查的基本形态"""

        patch_text = self._read_patch_text(patch_bundle)
        if not patch_text:
            return False

        rule_path = self.risk_rules_dir / "direct_apply_ready.yaml"
        raw = read_yaml_file(rule_path)
        if not raw:
            return False
        return self._matches(raw.get("detection") or {}, patch_text, patch_bundle.affected_files or [])

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

    def _build_evidence(
        self,
        *,
        risk_type: str,
        affected_files: list[str],
        patch_text: str,
        semantic_card: SemanticCard | None,
    ) -> list[str]:
        """生成风险证据摘要"""

        evidence = [f"规则命中: {risk_type}"]
        evidence.extend(f"涉及文件: {path}" for path in affected_files[:3])
        if semantic_card is not None and semantic_card.touched_functions:
            evidence.append("涉及函数: " + ", ".join(semantic_card.touched_functions[:3]))
        if semantic_card is not None and semantic_card.must_keep_conditions:
            evidence.append("关键条件: " + " | ".join(semantic_card.must_keep_conditions[:2]))
        if semantic_card is not None and semantic_card.critical_calls:
            evidence.append("关键调用: " + ", ".join(semantic_card.critical_calls[:3]))
        snippets = self._trigger_snippets(risk_type=risk_type, patch_text=patch_text, affected_files=affected_files)
        evidence.extend(snippets)
        if patch_text:
            excerpt = patch_text.replace("\r\n", "\n").splitlines()[:6]
            evidence.append("patch 摘要: " + " | ".join(excerpt[:3]))
        return evidence

    def _affected_functions(self, semantic_card: SemanticCard | None) -> list[str]:
        """优先使用语义阶段已经抽到的真实函数名"""

        if semantic_card is None:
            return []
        return [item for item in semantic_card.touched_functions if item][:3]

    def _affected_conditions(self, semantic_card: SemanticCard | None) -> list[str]:
        """回填与当前约束关联的关键条件"""

        if semantic_card is None:
            return []
        return [item for item in semantic_card.must_keep_conditions if item][:3]

    def _critical_calls(self, semantic_card: SemanticCard | None) -> list[str]:
        """回填与当前约束关联的关键调用"""

        if semantic_card is None:
            return []
        return [item for item in semantic_card.critical_calls if item][:3]

    def _trigger_snippets(self, *, risk_type: str, patch_text: str, affected_files: list[str]) -> list[str]:
        """抽取命中规则的 hunk 级证据片段"""

        if not patch_text:
            return []

        if risk_type == "header_abi_change":
            return [f"命中路径: {path}" for path in affected_files[:2] if path.endswith(".h")]

        changed_lines = self._collect_changed_lines(patch_text)
        patterns = self._risk_patterns(risk_type)
        snippets: list[str] = []

        for item in changed_lines:
            if risk_type == "global_data_change" and item.marker == "+":
                if any(re.search(pattern, item.text, flags=re.IGNORECASE) for pattern in patterns):
                    snippets.append(f"命中语句: {item.file_path} | {item.hunk_header} | + {item.text.strip()}")
            elif risk_type == "static_local_change" and item.marker == "+":
                if any(re.search(pattern, item.text, flags=re.IGNORECASE) for pattern in patterns):
                    snippets.append(f"命中语句: {item.file_path} | {item.hunk_header} | + {item.text.strip()}")
            elif risk_type in {"no_fentry_target", "init_code_change", "unsupported_section_change", "inline_side_effect"}:
                if any(re.search(pattern, item.text, flags=re.IGNORECASE) for pattern in patterns):
                    snippets.append(f"命中语句: {item.file_path} | {item.hunk_header} | {item.marker} {item.text.strip()}")
            elif risk_type == "struct_layout_change":
                if any(re.search(pattern, item.text, flags=re.IGNORECASE) for pattern in patterns):
                    snippets.append(f"命中语句: {item.file_path} | {item.hunk_header} | {item.marker} {item.text.strip()}")

            if len(snippets) >= 2:
                break

        return snippets

    def _collect_changed_lines(self, patch_text: str) -> list[_ChangedLine]:
        """按文件和 hunk 收集变更行，供规则证据复用"""

        current_file = ""
        current_hunk = ""
        changed_lines: list[_ChangedLine] = []

        for raw_line in patch_text.splitlines():
            if raw_line.startswith("diff --git "):
                parts = raw_line.split()
                if len(parts) >= 4:
                    current_file = self._normalize_patch_path(parts[3])
                current_hunk = ""
                continue
            if raw_line.startswith("+++ "):
                path = self._normalize_patch_path(raw_line[4:].strip())
                if path != "/dev/null":
                    current_file = path
                continue
            if raw_line.startswith("@@ "):
                current_hunk = raw_line.strip()
                continue
            if not raw_line or raw_line.startswith(("--- ", "+++ ")):
                continue
            marker = raw_line[0]
            if marker not in {"+", "-"}:
                continue
            changed_lines.append(
                _ChangedLine(
                    file_path=current_file,
                    hunk_header=current_hunk,
                    marker=marker,
                    text=raw_line[1:],
                )
            )

        return changed_lines

    def _normalize_patch_path(self, value: str) -> str:
        """统一 diff 头里的路径前缀"""

        if value.startswith(("a/", "b/")):
            return value[2:]
        return value

    def _risk_patterns(self, risk_type: str) -> list[str]:
        """返回每类风险用于抽证据的模式集合"""

        return {
            "global_data_change": [
                r"\bconst struct\b",
                r"\bDEFINE_",
                r"^\s*static\s+[A-Za-z_][\w\s\*]*\s+[A-Za-z_]\w*\s*(=|;)",
            ],
            "static_local_change": [
                r"^\s*static\s+(?!inline)(?!const\s+struct)[A-Za-z_][\w\s\*]*\s+[A-Za-z_]\w*\s*(=|;)",
            ],
            "struct_layout_change": [
                r"\bstruct\b.*\{",
                r"\bstruct\s+[A-Za-z_]\w*",
            ],
            "no_fentry_target": [r"__fentry__", r"\bfentry\b", r"ftrace"],
            "init_code_change": [r"__init", r"__exit", r"\.init\.text", r"\.exit\.text"],
            "unsupported_section_change": [r"\.altinstr_replacement", r"\.parainstructions", r"__patchable_function_entries", r"__jump_table"],
            "inline_side_effect": [r"\bstatic\s+inline\b", r"__always_inline", r"\binline\b"],
        }.get(risk_type, [])
