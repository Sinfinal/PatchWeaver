"""工作区创建与写入边界。"""

from __future__ import annotations

import json
from pathlib import Path

from patchweaver.models.task import TaskContext


class WorkspaceGuard:
    """负责创建任务工作区并固定目录布局。"""

    def __init__(self, workspace_root: Path) -> None:
        """记录工作区根目录。"""

        self.workspace_root = workspace_root

    def create_task_workspace(self, task: TaskContext) -> Path:
        """创建任务级目录骨架。"""

        task_dir = (self.workspace_root / task.task_id).resolve()
        required_dirs = [
            task_dir / "input",
            task_dir / "normalized",
            task_dir / "analysis" / "context",
            task_dir / "analysis" / "prompt",
            task_dir / "analysis" / "route",
            task_dir / "analysis" / "bootstrap",
            task_dir / "analysis" / "trace",
            task_dir / "attempts",
            task_dir / "doctor",
            task_dir / "reports" / "context",
            task_dir / "reports" / "prompt",
            task_dir / "reports" / "route",
            task_dir / "reports",
            task_dir / "artifacts",
        ]
        for path in required_dirs:
            path.mkdir(parents=True, exist_ok=True)

        # 任务创建时先把主上下文快照落盘，便于后续排错和回放。
        snapshot_path = task_dir / "task_context.json"
        snapshot_path.write_text(task.model_dump_json(indent=2), encoding="utf-8")
        return task_dir

    def create_attempt_workspace(self, task_dir: Path, attempt_no: int) -> Path:
        """创建单轮尝试的目录骨架。"""

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

        bootstrap_stub = attempt_dir / "prompt" / "bootstrap_manifest.json"
        skill_route_stub = attempt_dir / "route" / "skill_route.json"
        failover_stub = attempt_dir / "trace" / "failover.jsonl"
        if not bootstrap_stub.exists():
            bootstrap_stub.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not skill_route_stub.exists():
            skill_route_stub.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not failover_stub.exists():
            failover_stub.write_text("", encoding="utf-8")
        return attempt_dir
