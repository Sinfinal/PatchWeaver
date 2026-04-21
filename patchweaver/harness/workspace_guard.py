"""工作区创建与写入边界"""

from __future__ import annotations

import json
from pathlib import Path

from patchweaver.models.task import TaskContext
from patchweaver.utils.path_policy import ensure_within_root, relativize_payload, to_project_relative


class WorkspaceGuard:
    """负责创建任务工作区并固定目录布局"""

    def __init__(self, workspace_root: Path, project_root: Path | None = None) -> None:
        """记录工作区根目录"""

        self.workspace_root = workspace_root.resolve()
        self.project_root = project_root.resolve() if project_root is not None else None

    def create_task_workspace(self, task: TaskContext) -> Path:
        """创建任务根目录并刷新任务快照"""

        task_dir = self._resolve_task_dir(task.workspace_dir)
        task_dir.mkdir(parents=True, exist_ok=True)

        # 任务创建时先把主上下文快照落盘，便于后续排错和回放
        snapshot_path = task_dir / "task_context.json"
        snapshot_payload = relativize_payload(task, self.project_root)
        snapshot_path.write_text(json.dumps(snapshot_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return task_dir

    def ensure_task_input_workspace(self, task_dir: Path) -> None:
        """在需要写入任务输入产物时再创建输入目录"""

        self._ensure_dirs(task_dir, ["input"])

    def ensure_analysis_workspace(self, task_dir: Path) -> None:
        """在进入分析阶段时再创建分析目录"""

        self._ensure_dirs(
            task_dir,
            [
                "input",
                "normalized",
                "analysis/context",
                "analysis/prompt",
                "analysis/route",
                "analysis/bootstrap",
                "analysis/trace",
            ],
        )

    def ensure_report_workspace(self, task_dir: Path) -> None:
        """在进入报告阶段时再创建报告目录"""

        self._ensure_dirs(
            task_dir,
            [
                "reports/context",
                "reports/prompt",
                "reports/route",
                "reports",
            ],
        )

    def create_attempt_workspace(self, task_dir: Path, attempt_no: int) -> Path:
        """创建单轮尝试的目录骨架"""

        attempt_dir = task_dir / "attempts" / f"{attempt_no:03d}"
        required_dirs = [
            attempt_dir / "prompt",
            attempt_dir / "context",
            attempt_dir / "route",
            attempt_dir / "logs",
            attempt_dir / "rewrite",
            attempt_dir / "trace",
            attempt_dir / "artifacts",
        ]
        for path in required_dirs:
            path.mkdir(parents=True, exist_ok=True)
        return attempt_dir

    def _resolve_task_dir(self, workspace_dir: Path) -> Path:
        """把任务目录稳定解析到当前项目工作区内"""

        candidate = Path(workspace_dir)
        if candidate.is_absolute():
            return ensure_within_root(self.workspace_root, candidate, label="task.workspace_dir")

        workspace_relative = (
            to_project_relative(self.project_root, self.workspace_root) if self.project_root is not None else None
        )
        normalized = candidate.as_posix()
        if workspace_relative and workspace_relative not in {"", "."}:
            if normalized == workspace_relative or normalized.startswith(f"{workspace_relative}/"):
                return ensure_within_root(self.workspace_root, self.project_root / candidate, label="task.workspace_dir")

        return ensure_within_root(self.workspace_root, self.workspace_root / candidate, label="task.workspace_dir")

    def _ensure_dirs(self, task_dir: Path, relative_dirs: list[str]) -> None:
        """按需创建阶段目录，避免任务创建时一次性铺满整棵树"""

        for raw_dir in relative_dirs:
            (task_dir / raw_dir).mkdir(parents=True, exist_ok=True)
