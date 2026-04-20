"""工作区产物读取服务。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext


class ArtifactService:
    """负责把任务工作区中的产物整理成可视化结构。"""

    def __init__(self, context: ApiContext) -> None:
        """记录 API 共享上下文。"""

        self.context = context

    def list_tree(self, task_id: str) -> dict[str, Any]:
        """返回任务工作区的目录树和扁平索引。"""

        task = self._require_task(task_id)
        root = task.workspace_dir.resolve()
        items: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            relative_path = path.relative_to(root).as_posix()
            items.append(
                {
                    "name": path.name,
                    "relative_path": relative_path,
                    "kind": "directory" if path.is_dir() else "file",
                    "size": None if path.is_dir() else path.stat().st_size,
                    "suffix": path.suffix.lower(),
                }
            )
        return {
            "task_id": task_id,
            "root": str(root),
            "tree": self._build_tree(items),
            "items": items,
            "key_artifacts": self._collect_key_artifacts(root),
        }

    def read_content(self, task_id: str, relative_path: str, *, max_chars: int = 24000) -> dict[str, Any]:
        """读取单个产物文件内容，并做长度保护。"""

        task = self._require_task(task_id)
        target_path = self._safe_join(task.workspace_dir.resolve(), relative_path)
        if not target_path.exists():
            raise FileNotFoundError(f"找不到产物文件：{relative_path}")
        if target_path.is_dir():
            raise IsADirectoryError(f"目标不是文件：{relative_path}")

        raw_text = target_path.read_text(encoding="utf-8", errors="replace")
        content_type = self._detect_content_type(target_path)
        if content_type == "json":
            try:
                raw_text = json.dumps(json.loads(raw_text), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                content_type = "text"

        truncated = len(raw_text) > max_chars
        content = raw_text[:max_chars]
        if truncated:
            content += "\n\n[内容已截断，页面仅展示前部片段]"

        return {
            "task_id": task_id,
            "relative_path": relative_path.replace("\\", "/"),
            "absolute_path": str(target_path),
            "content": content,
            "content_type": content_type,
            "truncated": truncated,
            "size": target_path.stat().st_size,
        }

    def _require_task(self, task_id: str):
        """读取任务对象，不存在时直接报错。"""

        task = self.context.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"未找到任务：{task_id}")
        return task

    def _safe_join(self, root: Path, relative_path: str) -> Path:
        """把相对路径安全地展开到工作区内。"""

        normalized = relative_path.replace("\\", "/").lstrip("/")
        candidate = (root / normalized).resolve()
        if root != candidate and root not in candidate.parents:
            raise ValueError(f"非法产物路径：{relative_path}")
        return candidate

    def _build_tree(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """把扁平列表整理成前端更容易渲染的目录树。"""

        root: dict[str, Any] = {"children": {}}
        for item in items:
            parts = item["relative_path"].split("/")
            current = root
            for index, part in enumerate(parts):
                children = current.setdefault("children", {})
                node = children.setdefault(
                    part,
                    {
                        "name": part,
                        "relative_path": "/".join(parts[: index + 1]),
                        "kind": "directory",
                        "children": {},
                    },
                )
                if index == len(parts) - 1:
                    node.update(item)
                current = node

        return self._serialize_children(root.get("children", {}))

    def _serialize_children(self, children: dict[str, Any]) -> list[dict[str, Any]]:
        """递归把内部树节点转成列表结构。"""

        result: list[dict[str, Any]] = []
        for name in sorted(children):
            node = children[name]
            payload = {
                "name": node["name"],
                "relative_path": node["relative_path"],
                "kind": node["kind"],
                "size": node.get("size"),
                "suffix": node.get("suffix"),
            }
            if node["kind"] == "directory":
                payload["children"] = self._serialize_children(node.get("children", {}))
            result.append(payload)
        return result

    def _detect_content_type(self, path: Path) -> str:
        """根据扩展名给前端一个简单的渲染提示。"""

        suffix = path.suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix in {".md", ".markdown"}:
            return "markdown"
        if suffix in {".patch", ".diff"}:
            return "patch"
        if suffix in {".log", ".txt", ".yaml", ".yml"}:
            return "text"
        return "text"

    def _collect_key_artifacts(self, root: Path) -> dict[str, str | None]:
        """提取第四阶段常用的关键产物路径。"""

        report_json = root / "reports" / "report.json"
        report_md = root / "reports" / "report.md"
        latest_attempt_dir = self._latest_attempt_dir(root)
        build_log = latest_attempt_dir / "logs" / "build.log" if latest_attempt_dir else None
        validation_report = latest_attempt_dir / "artifacts" / "validation_report.json" if latest_attempt_dir else None
        trace_path = latest_attempt_dir / "trace" / "harness_trace.json" if latest_attempt_dir else None
        return {
            "report_json": str(report_json) if report_json.exists() else None,
            "report_md": str(report_md) if report_md.exists() else None,
            "build_log": str(build_log) if build_log is not None and build_log.exists() else None,
            "validation_report": str(validation_report) if validation_report is not None and validation_report.exists() else None,
            "trace_path": str(trace_path) if trace_path is not None and trace_path.exists() else None,
        }

    def _latest_attempt_dir(self, root: Path) -> Path | None:
        """定位任务目录下最近一轮尝试目录。"""

        attempts_root = root / "attempts"
        if not attempts_root.exists():
            return None
        candidates = [path for path in attempts_root.iterdir() if path.is_dir()]
        if not candidates:
            return None
        return sorted(candidates)[-1]
