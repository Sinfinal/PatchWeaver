"""语义卡片生成逻辑"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.task import TaskContext

_CONTROL_KEYWORDS = ("if", "while", "for", "switch")
_CALL_EXCLUDE = {
    "if",
    "while",
    "for",
    "switch",
    "return",
    "sizeof",
    "typeof",
    "likely",
    "unlikely",
}
_ROOT_CAUSE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("underflow", "unsigned", "wraparound"), "无符号算术导致的边界判断错误"),
    (("overflow", "out-of-bounds", "out of bounds", "bounds", "buffer"), "边界长度校验缺陷"),
    (("length", "size", "page_size"), "长度与容量校验缺陷"),
    (("null", "nullptr", "pointer"), "空指针或对象有效性检查缺陷"),
    (("use-after-free", "uaf", "refcount"), "对象生命周期处理缺陷"),
    (("race", "lock", "deadlock", "concurrent"), "并发同步缺陷"),
    (("permission", "capable", "privilege"), "权限校验缺陷"),
]


@dataclass(slots=True)
class PatchLine:
    """表示 hunk 中的一行补丁文本"""

    kind: str
    text: str


@dataclass(slots=True)
class ParsedHunk:
    """表示补丁中的单个 hunk"""

    file_path: str
    section_header: str
    lines: list[PatchLine]


@dataclass(slots=True)
class HunkSemantic:
    """表示单个 hunk 的语义摘要"""

    file_path: str
    function_name: str | None
    added_conditions: list[str]
    removed_conditions: list[str]
    critical_calls: list[str]
    side_effects: list[str]


class SemanticAnalyzer:
    """负责从 patch hunk 中提取最小可用语义卡片"""

    def analyze(self, task: TaskContext, patch_bundle: PatchBundle) -> SemanticCard:
        """根据任务与补丁输入生成可直接消费的语义卡片"""

        patch_text = self._load_patch_text(task, patch_bundle)
        if not patch_text:
            return SemanticCard(
                bug_class="cve_fix",
                root_cause=self._fallback_root_cause(task, patch_bundle),
                touched_files=self._ordered_unique(patch_bundle.affected_files),
                touched_functions=patch_bundle.affected_files,
            )

        hunk_semantics = [self._analyze_hunk(hunk) for hunk in self._parse_hunks(patch_text)]
        touched_functions = self._ordered_unique(
            item.function_name for item in hunk_semantics if item.function_name
        ) or list(patch_bundle.affected_files)
        must_keep_conditions = self._collect_conditions(hunk_semantics)
        must_keep_side_effects = self._ordered_unique(
            side_effect for item in hunk_semantics for side_effect in item.side_effects
        )
        critical_calls = self._ordered_unique(
            call for item in hunk_semantics for call in item.critical_calls
        )

        return SemanticCard(
            bug_class="cve_fix",
            root_cause=self._summarize_root_cause(task, patch_bundle, hunk_semantics, patch_text),
            must_keep_conditions=must_keep_conditions,
            must_keep_side_effects=must_keep_side_effects,
            critical_calls=critical_calls,
            touched_files=self._ordered_unique(patch_bundle.affected_files),
            touched_functions=touched_functions,
        )

    def _load_patch_text(self, task: TaskContext, patch_bundle: PatchBundle) -> str:
        """优先读取规范化补丁，缺失时回退到原始补丁"""

        candidates = [
            patch_bundle.normalized_patch_path,
            patch_bundle.raw_patch_path,
            task.workspace_dir / "normalized" / "normalized.patch",
            task.workspace_dir / "input" / "raw_patch.patch",
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            path = Path(candidate)
            if path.exists():
                return path.read_text(encoding="utf-8")
        return ""

    def _parse_hunks(self, patch_text: str) -> list[ParsedHunk]:
        """按文件和 hunk 级别解析 unified diff"""

        hunks: list[ParsedHunk] = []
        current_file: str | None = None
        current_hunk: ParsedHunk | None = None

        for raw_line in patch_text.splitlines():
            if raw_line.startswith("diff --git "):
                if current_hunk is not None:
                    hunks.append(current_hunk)
                    current_hunk = None
                parts = raw_line.split()
                if len(parts) >= 4:
                    current_file = self._normalize_patch_path(parts[3])
                continue
            if raw_line.startswith("+++ "):
                path = self._normalize_patch_path(raw_line[4:].strip())
                if path != "/dev/null":
                    current_file = path
                continue
            if raw_line.startswith("@@ "):
                if current_hunk is not None:
                    hunks.append(current_hunk)
                section_header = raw_line.split("@@")[-1].strip()
                current_hunk = ParsedHunk(
                    file_path=current_file or "",
                    section_header=section_header,
                    lines=[],
                )
                continue
            if current_hunk is None or not raw_line:
                continue
            if raw_line.startswith(("--- ", "+++ ")):
                continue
            marker = raw_line[0]
            if marker not in {"+", "-", " "}:
                continue
            current_hunk.lines.append(
                PatchLine(
                    kind={"+": "add", "-": "remove", " ": "context"}[marker],
                    text=raw_line[1:],
                )
            )

        if current_hunk is not None:
            hunks.append(current_hunk)
        return hunks

    def _analyze_hunk(self, hunk: ParsedHunk) -> HunkSemantic:
        """从单个 hunk 中提取函数、条件、调用和副作用"""

        function_name = self._extract_function_name(hunk.section_header)
        added_conditions: list[str] = []
        removed_conditions: list[str] = []
        critical_calls: list[str] = []
        side_effects: list[str] = []

        index = 0
        while index < len(hunk.lines):
            line = hunk.lines[index]
            stripped = line.text.strip()
            if self._is_control_start(stripped):
                expression, next_index = self._consume_control_expression(hunk.lines, index)
                if expression:
                    critical_calls.extend(self._extract_calls(expression))
                    if line.kind == "add":
                        added_conditions.append(expression)
                        side_effect = self._describe_guard_action(
                            hunk.lines,
                            next_index,
                            function_name,
                            expression,
                        )
                        if side_effect is not None:
                            side_effects.append(side_effect)
                    elif line.kind == "remove":
                        removed_conditions.append(expression)
                index = next_index
                continue

            critical_calls.extend(self._extract_calls(stripped))
            if line.kind != "context":
                direct_side_effect = self._summarize_statement(stripped, function_name)
                if direct_side_effect is not None:
                    side_effects.append(direct_side_effect)
            index += 1

        return HunkSemantic(
            file_path=hunk.file_path,
            function_name=function_name,
            added_conditions=self._ordered_unique(added_conditions),
            removed_conditions=self._ordered_unique(removed_conditions),
            critical_calls=self._ordered_unique(critical_calls),
            side_effects=self._ordered_unique(side_effects),
        )

    def _collect_conditions(self, hunk_semantics: list[HunkSemantic]) -> list[str]:
        """优先输出新增条件，没有新增条件时再回退到旧条件"""

        added = self._ordered_unique(
            self._label_condition(item.function_name, condition)
            for item in hunk_semantics
            for condition in item.added_conditions
        )
        if added:
            return added
        return self._ordered_unique(
            self._label_condition(item.function_name, condition)
            for item in hunk_semantics
            for condition in item.removed_conditions
        )

    def _label_condition(self, function_name: str | None, condition: str) -> str:
        """为条件表达式补一层函数标签，方便下游展示"""

        if function_name is None:
            return condition
        return f"{function_name}: {condition}"

    def _summarize_root_cause(
        self,
        task: TaskContext,
        patch_bundle: PatchBundle,
        hunk_semantics: list[HunkSemantic],
        patch_text: str,
    ) -> str:
        """组合 patch 解释、漏洞摘要和条件变化，生成根因说明"""

        focus_function = next(
            (item.function_name for item in hunk_semantics if item.function_name),
            None,
        ) or (patch_bundle.affected_files[0] if patch_bundle.affected_files else task.cve_id)
        removed_condition = next(
            (item.removed_conditions[0] for item in hunk_semantics if item.removed_conditions),
            None,
        )
        added_condition = next(
            (item.added_conditions[0] for item in hunk_semantics if item.added_conditions),
            None,
        )
        commit_explanation = self._extract_commit_explanation(patch_text)
        advisory_summary = self._extract_advisory_summary(patch_bundle)
        corpus = " ".join(
            filter(
                None,
                [
                    patch_bundle.commit_message,
                    commit_explanation,
                    advisory_summary,
                    removed_condition,
                    added_condition,
                ],
            )
        )
        theme = self._infer_root_cause_theme(corpus)
        if removed_condition and added_condition:
            summary = (
                f"{focus_function} 中存在{theme}，补丁将条件 `{removed_condition}` "
                f"调整为 `{added_condition}`。"
            )
        elif added_condition:
            summary = f"{focus_function} 中存在{theme}，修复围绕条件 `{added_condition}` 展开。"
        elif patch_bundle.commit_message:
            summary = f"{focus_function} 中存在{theme}，修复主题为 `{patch_bundle.commit_message}`。"
        else:
            summary = f"{focus_function} 中存在{theme}。"

        clue = commit_explanation or advisory_summary
        if clue:
            summary = f"{summary} 依据：{self._clip_text(clue, limit=140)}"
        return summary

    def _fallback_root_cause(self, task: TaskContext, patch_bundle: PatchBundle) -> str:
        """补丁文件不可读时的保底根因摘要"""

        advisory_summary = self._extract_advisory_summary(patch_bundle)
        if advisory_summary:
            return self._clip_text(advisory_summary, limit=160)
        if patch_bundle.commit_message:
            return f"{task.cve_id} 的修复主题为 `{patch_bundle.commit_message}`。"
        return f"{task.cve_id} 的修复意图待补充。"

    def _extract_commit_explanation(self, patch_text: str) -> str | None:
        """从邮件格式 patch 头部提取说明段落"""

        if not patch_text:
            return None

        lines = patch_text.splitlines()
        try:
            subject_index = next(index for index, line in enumerate(lines) if line.startswith("Subject: "))
        except StopIteration:
            return None

        body_lines: list[str] = []
        for line in lines[subject_index + 1 :]:
            stripped = line.strip()
            if stripped == "---":
                break
            if not stripped:
                body_lines.append("")
                continue
            if re.match(r"^[A-Za-z-]+-by: ", stripped):
                continue
            if re.match(r"^(Fixes|Cc|Link): ", stripped):
                continue
            body_lines.append(stripped)

        paragraphs = [paragraph.strip() for paragraph in "\n".join(body_lines).split("\n\n") if paragraph.strip()]
        if not paragraphs:
            return None
        return re.sub(r"\s+", " ", paragraphs[0])

    def _extract_advisory_summary(self, patch_bundle: PatchBundle) -> str | None:
        """优先使用元数据来源里的漏洞摘要"""

        preferred_stage_order = {"metadata": 0, "announce": 1, "patch": 2}
        ranked_items = sorted(
            patch_bundle.source_evidence,
            key=lambda item: (preferred_stage_order.get(item.stage or "", 99), 0 if item.preferred else 1),
        )
        for item in ranked_items:
            summary = self._clean_summary(item.summary)
            if summary:
                return summary
        return None

    def _clean_summary(self, summary: str | None) -> str | None:
        """统一清洗来源摘要里的多余空白和截断符号"""

        if summary is None:
            return None
        cleaned = re.sub(r"\s+", " ", summary).strip()
        cleaned = cleaned.rstrip("…").rstrip(".")
        if not cleaned:
            return None
        return cleaned

    def _infer_root_cause_theme(self, text: str) -> str:
        """根据说明文本猜一个足够稳的根因主题"""

        lowered = text.lower()
        for keywords, theme in _ROOT_CAUSE_HINTS:
            if any(keyword in lowered for keyword in keywords):
                return theme
        return "条件判断或状态转换缺陷"

    def _normalize_patch_path(self, path: str) -> str:
        """统一去掉 diff 头里的 a/ b/ 前缀"""

        if path.startswith(("a/", "b/")):
            return path[2:]
        return path

    def _extract_function_name(self, section_header: str) -> str | None:
        """从 hunk section header 中提取函数名"""

        candidates = re.findall(r"\b([A-Za-z_]\w*)\s*\(", section_header)
        for name in reversed(candidates):
            if name not in _CALL_EXCLUDE:
                return name
        return None

    def _is_control_start(self, stripped_text: str) -> bool:
        """判断一行是否以控制流表达式开头"""

        return stripped_text.startswith(tuple(f"{keyword} " for keyword in _CONTROL_KEYWORDS)) or stripped_text.startswith(
            tuple(f"{keyword}(" for keyword in _CONTROL_KEYWORDS)
        )

    def _consume_control_expression(self, lines: list[PatchLine], start_index: int) -> tuple[str | None, int]:
        """收集单条控制表达式，兼容跨多行的条件拼接"""

        collected: list[str] = []
        balance = 0
        index = start_index
        while index < len(lines):
            stripped = lines[index].text.strip()
            if not stripped:
                break
            collected.append(stripped.rstrip("{").strip())
            balance += stripped.count("(") - stripped.count(")")
            index += 1
            if balance <= 0:
                break
            if len(collected) >= 6:
                break

        merged = re.sub(r"\s+", " ", " ".join(collected)).strip()
        match = re.match(r"^(if|while|for|switch)\s*\((.+)\)$", merged)
        if match is not None:
            return match.group(2).strip(), index
        return merged or None, index

    def _describe_guard_action(
        self,
        lines: list[PatchLine],
        start_index: int,
        function_name: str | None,
        expression: str,
    ) -> str | None:
        """从条件后面的第一条语句里提炼关键副作用"""

        statement, _ = self._collect_statement(lines, start_index)
        if statement is None:
            return None
        return self._summarize_statement(statement, function_name, expression)

    def _collect_statement(self, lines: list[PatchLine], start_index: int) -> tuple[str | None, int]:
        """读取条件之后的第一条有效语句"""

        index = start_index
        fragments: list[str] = []
        while index < len(lines):
            stripped = lines[index].text.strip()
            index += 1
            if not stripped or stripped in {"{", "}"}:
                continue
            fragments.append(stripped)
            if stripped.endswith(";") or len(fragments) >= 3:
                break
        if not fragments:
            return None, index
        return re.sub(r"\s+", " ", " ".join(fragments)).strip(), index

    def _summarize_statement(
        self,
        statement: str,
        function_name: str | None,
        expression: str | None = None,
    ) -> str | None:
        """把 return、goto、赋值和调用语句转换成可展示的摘要"""

        text = re.sub(r"\s+", " ", statement).strip().rstrip(";")
        prefix = f"{function_name}: " if function_name else ""

        if text.startswith("return "):
            returned = text[len("return ") :].strip()
            calls = self._extract_calls(returned)
            action = f"返回 {calls[0]}(...)" if calls else f"返回 `{returned}`"
        elif text.startswith("goto "):
            action = f"跳转到 `{text[len('goto ') :].strip()}`"
        else:
            assignment = re.match(r"^([A-Za-z_][\w>\-\.\[\]]*)\s*([+\-*/%&|^]?=)", text)
            if assignment is not None:
                action = f"更新 `{assignment.group(1)}`"
            else:
                calls = self._extract_calls(text)
                if not calls:
                    return None
                action = f"调用 {calls[0]}(...)"

        if expression is not None:
            return f"{prefix}条件 `{expression}` 命中时{action}"
        return f"{prefix}{action}"

    def _extract_calls(self, text: str) -> list[str]:
        """从单行文本中提取函数调用名"""

        calls: list[str] = []
        for name in re.findall(r"\b([A-Za-z_]\w*)\s*\(", text):
            if name in _CALL_EXCLUDE:
                continue
            if re.fullmatch(r"[A-Z0-9_]+", name):
                continue
            calls.append(name)
        return self._ordered_unique(calls)

    def _clip_text(self, text: str, *, limit: int) -> str:
        """把说明文本裁剪到适合展示的长度"""

        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    def _ordered_unique(self, values) -> list[str]:
        """按出现顺序去重，同时丢掉空值"""

        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not value:
                continue
            normalized = str(value).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result
