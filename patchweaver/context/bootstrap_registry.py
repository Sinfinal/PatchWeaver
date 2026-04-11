"""Bootstrap 片段索引。"""

from __future__ import annotations

from pathlib import Path

from patchweaver.context.truncation_marker import build_truncation_mark
from patchweaver.models.context import BootstrapManifest


class BootstrapRegistry:
    """维护 bootstrap 片段列表和注入顺序。"""

    def build_manifest(self, fragment_paths: list[Path]) -> BootstrapManifest:
        """把片段路径整理为结构化 manifest。"""

        # 先把目录展开成稳定顺序的文件列表，后面 token 统计和渲染顺序都基于这份结果。
        resolved = self._collect_fragments(fragment_paths)
        truncation_marks: list[str] = []
        total_token_cost = 0
        render_order: list[str] = []
        fragment_ids: list[str] = []
        fragment_paths_text: list[str] = []
        for path in resolved:
            text = path.read_text(encoding="utf-8")
            token_cost = max(1, len(text) // 4)
            total_token_cost += token_cost
            fragment_id = f"{path.parent.name}/{path.stem}"
            fragment_ids.append(fragment_id)
            fragment_paths_text.append(str(path))
            render_order.append(fragment_id)
            # 这里先只打截断标记，不真的裁文本；真正裁剪放到 prompt/context 层再做。
            if len(text) > 1200:
                truncation_marks.append(build_truncation_mark(fragment_id, len(text), 1200))
        return BootstrapManifest(
            fragment_ids=fragment_ids,
            fragment_paths=fragment_paths_text,
            truncation_marks=truncation_marks,
            render_order=render_order,
            total_token_cost=total_token_cost,
        )

    def _collect_fragments(self, fragment_paths: list[Path]) -> list[Path]:
        """把目录和文件统一展开为稳定顺序的片段列表。"""

        resolved: list[Path] = []
        allowed_suffixes = {".md", ".txt", ".json", ".yaml", ".yml"}
        for path in fragment_paths:
            if not path.exists():
                continue
            if path.is_file():
                if path.suffix.lower() in allowed_suffixes:
                    resolved.append(path.resolve())
                continue
            # 目录模式下递归收集，避免后面扩 bootstrap 子目录时还得改扫描逻辑。
            for candidate in sorted(path.rglob("*")):
                if candidate.is_file() and candidate.suffix.lower() in allowed_suffixes:
                    resolved.append(candidate.resolve())
        return resolved
